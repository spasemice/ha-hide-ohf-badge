"""Home Assistant app: event-triggered, idempotent frontend logo patch."""
import argparse
from datetime import datetime, timezone
import http.client
import json
import logging
import os
from pathlib import Path
import signal
import socket
import struct
import threading
from urllib.parse import quote, urlencode

from status import StatusServer

LOG = logging.getLogger("blank-foundation-logo")
TARGET = "homeassistant"
SOCKET_PATH = "/var/run/docker.sock"
PATCH_SOURCE = Path(__file__).with_name("patcher.py").read_text(encoding="utf-8")


class DockerError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__("Docker HTTP %s: %s" % (status, message))


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, timeout=30):
        super().__init__("localhost", timeout=timeout)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET_PATH)


def decode_frames(data):
    output, errors = bytearray(), bytearray()
    while data:
        if len(data) < 8:
            raise RuntimeError("Truncated Docker output header")
        stream, size = data[0], struct.unpack(">I", data[4:8])[0]
        if stream not in (0, 1, 2) or len(data) < 8 + size:
            raise RuntimeError("Invalid or incomplete Docker output")
        (errors if stream == 2 else output).extend(data[8:8 + size])
        data = data[8 + size:]
    return output.decode("utf-8"), errors.decode("utf-8")


class Docker:
    def request(self, method, path, value=None):
        connection = UnixConnection()
        try:
            body = json.dumps(value).encode() if value is not None else None
            connection.request(method, path, body=body,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read()
            if response.status >= 300:
                raise DockerError(response.status, data.decode("utf-8", errors="replace")[:500])
            return data
        finally:
            connection.close()

    def patch(self):
        try:
            container = json.loads(self.request("GET", "/containers/" + TARGET + "/json"))
        except DockerError as error:
            if error.status == 404:
                return {"state": "waiting", "reason": "Home Assistant container is absent"}
            raise
        if not container["State"]["Running"]:
            return {"state": "waiting", "reason": "Home Assistant container is stopped"}
        # A fixed container ID protects against replacement during an update.
        container_id = quote(container["Id"], safe="")
        created = json.loads(self.request("POST", "/containers/" + container_id + "/exec", {
            "AttachStdout": True, "AttachStderr": True, "AttachStdin": False,
            "Tty": False, "User": "0", "Cmd": ["python3", "-c", PATCH_SOURCE],
        }))
        exec_id = quote(created["Id"], safe="")
        raw = self.request("POST", "/exec/" + exec_id + "/start", {"Detach": False, "Tty": False})
        output, errors = decode_frames(raw)
        status = json.loads(self.request("GET", "/exec/" + exec_id + "/json"))
        if status.get("Running") or status.get("ExitCode") != 0:
            raise RuntimeError("SVG check failed: " + (errors.strip() or output.strip())[-1000:])
        result = json.loads(output)
        result.update(state="ok", image=container["Config"]["Image"])
        return result

    def events(self, stop, on_start, on_connected):
        filters = {"type": ["container"], "event": ["start"], "container": [TARGET]}
        connection = UnixConnection(timeout=None)
        try:
            connection.request("GET", "/events?" + urlencode({"filters": json.dumps(filters)}))
            response = connection.getresponse()
            if response.status != 200:
                raise DockerError(response.status, "Cannot subscribe to Docker start events")
            on_connected()
            # Check after the subscription is established, covering startup races.
            on_start("listener_connected")
            while not stop.is_set():
                line = response.readline()
                if not line:
                    raise RuntimeError("Docker event stream disconnected")
                event = json.loads(line)
                if event.get("Action") == "start":
                    on_start("core_start")
        finally:
            connection.close()


class Supervisor:
    """Use only this app's self endpoints; no admin or manager role needed."""
    def request(self, method, value=None):
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            raise RuntimeError("Supervisor token unavailable")
        connection = http.client.HTTPConnection("supervisor", timeout=5)
        try:
            path = "/addons/self/info" if method == "GET" else "/addons/self/options"
            connection.request(method, path, body=json.dumps(value) if value is not None else None,
                               headers={"Authorization": "Bearer " + token,
                                        "Content-Type": "application/json"})
            response = connection.getresponse()
            data = json.loads(response.read())
            if response.status != 200 or data.get("result") != "ok":
                raise RuntimeError("Supervisor request failed (HTTP %s)" % response.status)
            return data.get("data", {})
        finally:
            connection.close()

    def initialize_defaults(self, marker=Path("/data/startup-defaults-v1")):
        if marker.exists():
            return
        # Apply once, then respect changes made by the user in the Info tab.
        self.request("POST", {"boot": "auto", "watchdog": True})
        marker.write_text("Start on boot and Watchdog enabled once.\n", encoding="utf-8")
        LOG.info("Initial settings: Start on boot ON; Watchdog ON. Protection mode must be OFF.")


class App:
    def __init__(self, docker=None, status_path=Path("/data/status.json")):
        self.docker = docker or Docker()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.previous = None
        self.status_path = status_path
        self.state_lock = threading.Lock()
        self.report = {"state": "waiting", "reason": "Waiting for the first startup check"}
        self.listener = "connecting"
        self.listener_error = None
        self.check_count = 0

    def snapshot(self):
        with self.state_lock:
            return {**self.report, "listener": self.listener,
                    "listener_error": self.listener_error, "check_count": self.check_count}

    def set_listener(self, state, error=None):
        with self.state_lock:
            self.listener, self.listener_error = state, error

    def record(self, report, reason):
        report = {**report, "checked_at": datetime.now(timezone.utc).isoformat(), "trigger": reason}
        with self.state_lock:
            self.report = report
            self.check_count += 1
        if self.status_path is not None:
            try:
                temporary = self.status_path.with_suffix(".tmp")
                temporary.write_text(json.dumps(report), encoding="utf-8")
                temporary.replace(self.status_path)
            except OSError as error:
                LOG.warning("Could not save last result: %s", error)
        return report

    def check(self, reason="app_start"):
        with self.lock:
            try:
                report = self.docker.patch()
                signature = (report["state"], report.get("image"))
                if report.get("changed"):
                    LOG.info("Replaced %s logos; original backups: %s", report["changed"],
                             ", ".join(report["backups"]))
                elif signature != self.previous:
                    LOG.info("%s", "Both logos are already blank: " + report.get("image", "")
                             if report["state"] == "ok" else report["reason"])
                self.previous = signature
                return self.record(report, reason)
            except Exception as error:
                signature = ("error", str(error))
                if signature != self.previous:
                    LOG.error("%s", error)
                self.previous = signature
                return self.record({"state": "error", "error": str(error)}, reason)

    def watch(self):
        while not self.stop.is_set():
            try:
                self.docker.events(self.stop, self.check,
                                   lambda: self.set_listener("connected"))
            except Exception as error:
                if not self.stop.is_set():
                    self.set_listener("reconnecting", str(error))
                    LOG.warning("Start-event listener will reconnect: %s", error)
            # Retry only a broken connection, never poll or recheck logo files.
            self.stop.wait(10)

    def run(self):
        worker = threading.Thread(target=self.watch, daemon=True, name="docker-start-events")
        server = StatusServer(self, Supervisor(), worker)
        worker.start()
        LOG.info("Startup-only mode: sleep until Core starts. No timer or periodic SVG checks.")
        try:
            # Blocking accept: wakes only for a status/health request or a signal.
            while not self.stop.is_set():
                server.handle_request()
        finally:
            self.stop.set()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Check once and print the result")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not Path(SOCKET_PATH).exists():
        LOG.error("Docker socket unavailable. Turn Protection mode off on this app's Info page, then Start.")
        return 1
    app = App()
    def shutdown(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    if args.once:
        result = app.check()
        print(json.dumps(result))
        return 1 if result["state"] == "error" else 0
    try:
        Supervisor().initialize_defaults()
    except Exception as error:
        LOG.warning("Set Start on boot and Watchdog ON in Info; defaults could not be applied: %s", error)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
