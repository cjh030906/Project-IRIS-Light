"""Assert @theia/ffmpeg stub / native bypass helpers exist (no VS C++ required)."""

from __future__ import annotations

import json
from pathlib import Path

from iris.system.iris_ide_runtime import _yarn_needs_native_bypass, runtime_source_dir


def main() -> None:
    src = runtime_source_dir()
    pkg = json.loads((src / "package.json").read_text(encoding="utf-8"))
    resolutions = pkg.get("resolutions") or {}
    assert resolutions.get("@theia/ffmpeg", "").endswith("theia-ffmpeg-stub"), resolutions

    stub_pkg = src / "vendor" / "theia-ffmpeg-stub" / "package.json"
    stub_js = src / "vendor" / "theia-ffmpeg-stub" / "lib" / "index.js"
    assert stub_pkg.is_file() and stub_js.is_file()
    stub_meta = json.loads(stub_pkg.read_text(encoding="utf-8"))
    assert stub_meta["name"] == "@theia/ffmpeg"
    assert "iris-stub" in stub_meta["version"]
    assert "binding.gyp" not in (stub_meta.get("files") or [])

    lock = (src / "yarn.lock").read_text(encoding="utf-8")
    assert "file:./vendor/theia-ffmpeg-stub" in lock or "file:vendor/theia-ffmpeg-stub" in lock
    assert "1.74.0-iris-stub" in lock

    assert _yarn_needs_native_bypass("Could not find any Visual Studio installation to use")
    assert _yarn_needs_native_bypass("error ... @theia/ffmpeg: Command failed")
    assert not _yarn_needs_native_bypass("network timeout")

    print("iris_ide_ffmpeg_stub check ok", stub_pkg)


if __name__ == "__main__":
    main()
