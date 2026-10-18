"""Patch the Foundation logo assets and the launch footer, preserving originals."""
import gzip
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

NAMES = ("open-home-foundation-on-dark.svg", "open-home-foundation-on-light.svg")
LEGACY_NAME = "ohf-badge.svg"
BLANK = b'<svg xmlns="http://www.w3.org/2000/svg" width="237" height="24" viewBox="0 0 237 24"/>\n'
MARKER = "<!-- hide-ohf-badge: launch footer removed -->"
VOID_TAGS = frozenset("area base br col embed hr img input link meta param source track wbr".split())


def launch_template(data):
    """Remove exactly one Foundation footer, preserving all other HTML verbatim."""
    text = data.decode("utf-8")
    offsets, offset = [], 0
    for line in text.splitlines(keepends=True):
        offsets.append(offset)
        offset += len(line)

    class FooterParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack, self.matches = [], []
            self.start = None
            self.saw_launch = False

        def position(self):
            row, column = self.getpos()
            return offsets[row - 1] + column

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("id") == "ha-launch-screen":
                self.saw_launch = True
            if "ohf-logo" in (attrs.get("class") or "").split():
                if tag != "div" or self.start is not None or not any(
                        item[1].get("id") == "ha-launch-screen" for item in self.stack):
                    raise RuntimeError("Unexpected Foundation footer structure; no files changed")
                self.start = (self.position(), len(self.stack))
            if tag not in VOID_TAGS:
                self.stack.append((tag, attrs))

        def handle_startendtag(self, tag, attrs):
            pass

        def handle_endtag(self, tag):
            if tag in VOID_TAGS:
                return
            if not self.stack or self.stack[-1][0] != tag:
                raise RuntimeError("Unexpected HTML nesting; no files changed")
            self.stack.pop()
            if self.start is not None and len(self.stack) == self.start[1]:
                begin = self.start[0]
                end = text.index(">", self.position()) + 1
                block = text[begin:end]
                if not any(name in block for name in (*NAMES, LEGACY_NAME)):
                    raise RuntimeError("Unknown launch footer content; no files changed")
                self.matches.append((begin, end))
                self.start = None

    parser = FooterParser()
    parser.feed(text)
    parser.close()
    if parser.stack or parser.start is not None or not parser.saw_launch:
        raise RuntimeError("Incomplete or unknown launch template; no files changed")
    if not parser.matches and text.count(MARKER) == 1:
        return data
    if len(parser.matches) != 1 or MARKER in text:
        raise RuntimeError("Expected exactly one launch footer; no files changed")
    begin, end = parser.matches[0]
    return (text[:begin] + MARKER + text[end:]).encode("utf-8")


def checked_file(path, parent):
    if path.is_symlink() or not path.is_file() or path.resolve().parent != parent.resolve():
        raise RuntimeError("Expected frontend file missing or symlink: " + path.name)
    return path.read_bytes(), path.stat()


def validate_svg(data, name):
    if ET.fromstring(data).tag != "{http://www.w3.org/2000/svg}svg":
        raise RuntimeError("Unexpected document type: " + name)


def brotli_codec():
    try:
        import brotli
    except ImportError:
        try:
            import brotlicffi as brotli
        except ImportError as error:
            raise RuntimeError("Core has no Brotli decoder; no files changed") from error
    return brotli


def cached_launch_footer():
    """One startup-only probe; never restart Core or poll its HTTP endpoint."""
    try:
        request = urllib.request.Request("http://127.0.0.1:8123/", headers={
            "Accept-Encoding": "identity", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=1) as response:
            text = response.read(2_000_000).decode("utf-8")
        if MARKER in text:
            return False
        return 'class="ohf-logo"' in text or "class='ohf-logo'" in text
    except Exception:
        return None  # Core may not be serving HTTP yet during its startup.


def patch(frontend_root=None, backup_directory=None):
    live_core = frontend_root is None
    if live_core:
        spec = importlib.util.find_spec("hass_frontend")
        if spec is None or not spec.submodule_search_locations:
            raise RuntimeError("Cannot locate hass_frontend; no files changed")
        frontend_root = next(iter(spec.submodule_search_locations))
    frontend_root = Path(frontend_root)
    base = frontend_root / "static" / "images"
    if base.is_symlink() or not base.is_dir():
        raise RuntimeError("Unexpected frontend images directory; no files changed")
    planned = []
    names = list(NAMES) if any((base / name).exists() or (base / name).is_symlink() for name in NAMES) else []
    if (base / LEGACY_NAME).exists() or (base / LEGACY_NAME).is_symlink():
        names.append(LEGACY_NAME)
    if not names:
        raise RuntimeError("No known Foundation SVG assets found; no files changed")
    for name in names:
        path = base / name
        original, metadata = checked_file(path, base)
        validate_svg(original, name)
        if original != BLANK:
            planned.append((path, original, metadata, BLANK))
        for suffix in (".gz", ".br"):
            sibling = base / (name + suffix)
            if not sibling.exists() and not sibling.is_symlink():
                continue
            packed, packed_metadata = checked_file(sibling, base)
            codec = None if suffix == ".gz" else brotli_codec()
            decoded = gzip.decompress(packed) if codec is None else codec.decompress(packed)
            validate_svg(decoded, sibling.name)
            if decoded != BLANK:
                replacement = gzip.compress(BLANK, mtime=0) if codec is None else codec.compress(BLANK)
                planned.append((sibling, packed, packed_metadata, replacement))
    template = frontend_root / "index.html"
    original, metadata = checked_file(template, frontend_root)
    replacement = launch_template(original)
    if replacement != original:
        planned.append((template, original, metadata, replacement))

    backups = []
    backup_root = Path(backup_directory or "/config/branding-backups/automatic")
    # Validate every target above and back up every original before the first write.
    for path, original, metadata, replacement in planned:
        folder = backup_root / hashlib.sha256(original).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / path.name
        try:
            with target.open("xb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if target.read_bytes() != original:
                raise RuntimeError("Existing backup does not match: " + str(target))
        backups.append(str(target))
    for path, original, metadata, replacement in planned:
        descriptor, temporary_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(replacement)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(stat.S_IMODE(metadata.st_mode))
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
            os.replace(temporary, path)
            if path.read_bytes() != replacement:
                raise RuntimeError("Verification failed: " + str(path))
        finally:
            if temporary.exists():
                temporary.unlink()
    return {"changed": len(planned), "directory": str(base), "backups": backups,
            "launch_footer_patched": True,
            "core_restart_required": cached_launch_footer() if live_core else None}


if __name__ == "__main__":
    print(json.dumps(patch()))
