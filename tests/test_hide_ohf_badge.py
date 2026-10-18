import importlib.util
import gzip
import http.client
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "hide_ohf_badge"
sys.path.insert(0, str(SOURCE))


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SOURCE / filename)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


patcher = module("logo_patcher", "patcher.py")
app = module("logo_app", "app.py")
status_page = module("logo_status_page", "status.py")
ORIGINAL = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
TEMPLATE = (b'<!doctype html><html><head><style>.ohf-logo{display:flex}</style></head><body>'
            b'<div id="ha-launch-screen"><img class="ha-logo" src="/home-assistant.svg">'
            b'<div class="ohf-logo"><span>A project from the</span><picture>'
            b'<source srcset="/static/images/open-home-foundation-on-dark.svg">'
            b'<img src="/static/images/open-home-foundation-on-light.svg"></picture></div></div>'
            b'<home-assistant></home-assistant><script>window.example="keep me";</script></body></html>')


class PatcherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.frontend = self.root / "frontend"
        self.images = self.frontend / "static" / "images"
        self.images.mkdir(parents=True)
        (self.frontend / "index.html").write_bytes(TEMPLATE)
        for name in patcher.NAMES:
            (self.images / name).write_bytes(ORIGINAL)
        self.owner = mock.patch.object(patcher.os, "chown", create=True)
        self.owner.start()

    def tearDown(self):
        self.owner.stop()
        self.temporary.cleanup()

    def patch(self):
        return patcher.patch(self.frontend, self.root / "backups")

    def test_update_patch_preserves_originals_and_second_run_is_noop(self):
        first = self.patch()
        self.assertEqual(first["changed"], 3)
        for backup in first["backups"]:
            self.assertEqual(Path(backup).read_bytes(), TEMPLATE if Path(backup).name == "index.html" else ORIGINAL)
        modified = {str(p): p.stat().st_mtime_ns for p in self.frontend.rglob("*") if p.is_file()}
        self.assertEqual(self.patch()["changed"], 0)
        self.assertEqual(modified, {str(p): p.stat().st_mtime_ns for p in self.frontend.rglob("*") if p.is_file()})
        for name in patcher.NAMES:
            self.assertEqual((self.images / name).read_bytes(), patcher.BLANK)
        html = (self.frontend / "index.html").read_text()
        self.assertIn(patcher.MARKER, html)
        self.assertIn('class="ha-logo"', html)
        self.assertIn('window.example="keep me"', html)
        self.assertNotIn("A project from the", html)

    def test_gzip_variants_cannot_serve_the_original_logo(self):
        for name in patcher.NAMES:
            (self.images / (name + ".gz")).write_bytes(gzip.compress(ORIGINAL))
        self.assertEqual(self.patch()["changed"], 5)
        for name in patcher.NAMES:
            self.assertEqual(gzip.decompress((self.images / (name + ".gz")).read_bytes()), patcher.BLANK)
        self.assertEqual(self.patch()["changed"], 0)

    @unittest.skipUnless(importlib.util.find_spec("brotli") or importlib.util.find_spec("brotlicffi"), "Brotli is provided by Home Assistant Core")
    def test_brotli_variants_cannot_serve_the_original_logo(self):
        codec = patcher.brotli_codec()
        for name in patcher.NAMES:
            (self.images / (name + ".br")).write_bytes(codec.compress(ORIGINAL))
        self.assertEqual(self.patch()["changed"], 5)
        for name in patcher.NAMES:
            self.assertEqual(codec.decompress((self.images / (name + ".br")).read_bytes()), patcher.BLANK)
        self.assertEqual(self.patch()["changed"], 0)

    def test_bad_compressed_asset_prevents_all_changes(self):
        (self.images / (patcher.NAMES[0] + ".gz")).write_bytes(b"invalid gzip")
        with self.assertRaises(Exception):
            self.patch()
        self.assertEqual((self.frontend / "index.html").read_bytes(), TEMPLATE)
        self.assertEqual((self.images / patcher.NAMES[0]).read_bytes(), ORIGINAL)
        self.assertFalse((self.root / "backups").exists())

    def test_legacy_badge_is_patched_when_present(self):
        (self.images / patcher.LEGACY_NAME).write_bytes(ORIGINAL)
        self.patch()
        self.assertEqual((self.images / patcher.LEGACY_NAME).read_bytes(), patcher.BLANK)

    def test_unknown_footer_prevents_all_changes(self):
        path = self.frontend / "index.html"
        path.write_bytes(TEMPLATE.replace(b' class="ohf-logo"', b' class="different-logo"'))
        with self.assertRaises(RuntimeError):
            self.patch()
        self.assertEqual((self.images / patcher.NAMES[0]).read_bytes(), ORIGINAL)
        self.assertFalse((self.root / "backups").exists())

    def test_two_footer_blocks_are_rejected(self):
        path = self.frontend / "index.html"
        path.write_bytes(TEMPLATE.replace(b'<div class="ohf-logo">', b'<div class="ohf-logo"><div class="ohf-logo">').replace(b'</picture></div>', b'</picture></div></div>'))
        with self.assertRaises(RuntimeError):
            self.patch()
        self.assertEqual((self.images / patcher.NAMES[0]).read_bytes(), ORIGINAL)

    def test_missing_new_frontend_asset_does_not_partially_patch(self):
        (self.images / patcher.NAMES[1]).unlink()
        with self.assertRaises(RuntimeError):
            self.patch()
        self.assertEqual((self.images / patcher.NAMES[0]).read_bytes(), ORIGINAL)

    def test_backup_failure_leaves_originals_untouched(self):
        with mock.patch.object(patcher.Path, "mkdir", side_effect=PermissionError("Read only")):
            with self.assertRaises(PermissionError):
                self.patch()
        for name in patcher.NAMES:
            self.assertEqual((self.images / name).read_bytes(), ORIGINAL)


class DockerTests(unittest.TestCase):
    def test_event_subscription_checks_initial_state_and_core_start(self):
        stop = threading.Event()
        lines = iter([b'{"Action":"other"}\n', b'{"Action":"start"}\n'])
        response = mock.Mock(status=200)
        def readline():
            line = next(lines)
            if b'"start"' in line:
                stop.set()
            return line
        response.readline.side_effect = readline
        connection = mock.Mock()
        connection.getresponse.return_value = response
        connected, check = mock.Mock(), mock.Mock()
        with mock.patch.object(app, "UnixConnection", return_value=connection):
            app.Docker().events(stop, check, connected)
        connected.assert_called_once_with()
        self.assertEqual(check.call_args_list, [mock.call("listener_connected"), mock.call("core_start")])
        self.assertIn("homeassistant", connection.request.call_args.args[1])
        connection.close.assert_called_once_with()

    def test_start_events_check_once_then_block_without_timer(self):
        daemon = mock.Mock()
        daemon.patch.return_value = {"state": "ok", "changed": 0, "image": "core:test"}
        entered = threading.Event()
        application = app.App(daemon, status_path=None)
        def stream(stop, on_start, on_connected):
            on_connected()
            on_start("listener_connected")
            entered.set()
            stop.wait()
        daemon.events.side_effect = stream
        worker = threading.Thread(target=application.watch)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(daemon.patch.call_count, 1)
            self.assertEqual(application.snapshot()["listener"], "connected")
            self.assertEqual(application.snapshot()["trigger"], "listener_connected")
            self.assertEqual(application.snapshot()["check_count"], 1)
            self.assertTrue(worker.is_alive())
        finally:
            application.stop.set()
            worker.join(2)

    def test_health_and_status_requests_never_run_svg_checks(self):
        daemon = mock.Mock()
        application = app.App(daemon, status_path=None)
        supervisor = mock.Mock()
        supervisor.request.return_value = {"boot": "auto", "watchdog": True, "protected": False}
        worker = mock.Mock()
        worker.is_alive.return_value = True
        server = status_page.StatusServer(application, supervisor, worker, ("127.0.0.1", 0))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            for path in ("/health", "/status.json", "/"):
                connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                connection.request("GET", path)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                connection.close()
            daemon.patch.assert_not_called()
            self.assertEqual(application.snapshot()["check_count"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_defaults_are_applied_once_and_user_changes_are_respected(self):
        supervisor = app.Supervisor()
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "defaults"
            with mock.patch.object(supervisor, "request") as request:
                supervisor.initialize_defaults(marker)
                supervisor.initialize_defaults(marker)
                request.assert_called_once_with("POST", {"boot": "auto", "watchdog": True})

    def test_status_escapes_errors_and_reports_success_only_after_verification(self):
        html = status_page.render({"state": "error", "error": '<script>alert(1)</script>'}, {})
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("Logos removed", html)
        html = status_page.render({"state": "ok", "listener": "connected", "check_count": 1}, {})
        self.assertIn("Logos removed", html)
        self.assertIn("Sleeping", html)
        html = status_page.render({"state": "ok", "core_restart_required": True}, {})
        self.assertIn("Restart Core to finish", html)
        self.assertNotIn("Logos removed", html)

    def test_multiplexed_stderr_and_stdout_are_separate(self):
        def frame(stream, value):
            return bytes([stream, 0, 0, 0]) + struct.pack(">I", len(value)) + value
        output, error = app.decode_frames(frame(1, b'{"changed":0}') + frame(2, b"warning"))
        self.assertEqual(json.loads(output), {"changed": 0})
        self.assertEqual(error, "warning")
        with self.assertRaises(RuntimeError):
            app.decode_frames(frame(1, b"incomplete")[:-1])

    def test_stopped_or_recreated_core_is_not_executed(self):
        docker = app.Docker()
        with mock.patch.object(docker, "request", return_value=b'{"State":{"Running":false}}') as request:
            self.assertEqual(docker.patch()["state"], "waiting")
            self.assertEqual(request.call_count, 1)
        with mock.patch.object(docker, "request", side_effect=app.DockerError(404, "absent")) as request:
            self.assertEqual(docker.patch()["state"], "waiting")
            self.assertEqual(request.call_count, 1)

    def test_exec_failure_does_not_report_success(self):
        responses = [b'{"Id":"core-id","State":{"Running":true},"Config":{"Image":"test"}}',
                     b'{"Id":"exec-id"}', b"", b'{"Running":false,"ExitCode":1}']
        docker = app.Docker()
        with mock.patch.object(docker, "request", side_effect=responses) as request:
            with self.assertRaises(RuntimeError):
                docker.patch()
            self.assertEqual(request.call_args_list[1].args[1], "/containers/core-id/exec")


if __name__ == "__main__":
    unittest.main()
