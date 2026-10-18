import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import xml.etree.ElementTree as ET

NAMES = ("open-home-foundation-on-dark.svg", "open-home-foundation-on-light.svg")
BLANK = b'<svg xmlns="http://www.w3.org/2000/svg" width="237" height="24" viewBox="0 0 237 24"/>\n'

def patch(frontend_root=None, backup_directory=None):
    if frontend_root is None:
        spec = importlib.util.find_spec("hass_frontend")
        if spec is None or not spec.submodule_search_locations:
            raise RuntimeError("Cannot locate hass_frontend; no files changed")
        frontend_root = next(iter(spec.submodule_search_locations))
    base = Path(frontend_root) / "static" / "images"
    if base.is_symlink() or not base.is_dir():
        raise RuntimeError("Unexpected frontend images directory; no files changed")
    planned = []
    for name in NAMES:
        path = base / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != base.resolve():
            raise RuntimeError("Expected SVG missing or symlink: " + name)
        original = path.read_bytes()
        root = ET.fromstring(original)
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise RuntimeError("Unexpected document type: " + name)
        if original != BLANK:
            planned.append((path, original, path.stat()))
    backups = []
    backup_root = Path(backup_directory or "/config/branding-backups/automatic")
    # Back up every original before touching either file. Content hashes avoid
    # duplicate backups on retries or repeated updates to the same frontend.
    for path, original, metadata in planned:
        digest = hashlib.sha256(original).hexdigest()
        folder = backup_root / digest
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
    for path, original, metadata in planned:
        descriptor, temporary_name = tempfile.mkstemp(prefix="." + path.name + ".", dir=base)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(BLANK)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(stat.S_IMODE(metadata.st_mode))
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
            os.replace(temporary, path)
            if path.read_bytes() != BLANK:
                raise RuntimeError("Verification failed: " + str(path))
        finally:
            if temporary.exists():
                temporary.unlink()
    return {"changed": len(planned), "directory": str(base), "backups": backups}

if __name__ == "__main__":
    print(json.dumps(patch()))
