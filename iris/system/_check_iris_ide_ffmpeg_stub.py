"""Assert @theia/ffmpeg stub / native bypass helpers exist (no VS C++ required)."""

from __future__ import annotations

import json
from pathlib import Path

from iris.system.iris_ide_runtime import (
    _command_failure_text,
    _yarn_needs_native_bypass,
    _yarn_registry_flake,
    _yarn_user_message,
    runtime_source_dir,
)


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

    lock_path = src / "yarn.lock"
    if lock_path.is_file():
        lock = lock_path.read_text(encoding="utf-8")
        assert "file:./vendor/theia-ffmpeg-stub" in lock or "file:vendor/theia-ffmpeg-stub" in lock
        assert "1.74.0-iris-stub" in lock
        assert "drivelist-stub" in lock
        assert "12.0.2-iris-stub" in lock

    assert resolutions.get("drivelist", "").endswith("drivelist-stub"), resolutions
    drive_pkg = src / "vendor" / "drivelist-stub" / "package.json"
    drive_js = src / "vendor" / "drivelist-stub" / "js" / "index.js"
    assert drive_pkg.is_file() and drive_js.is_file()
    drive_meta = json.loads(drive_pkg.read_text(encoding="utf-8"))
    assert drive_meta["name"] == "drivelist"
    assert drive_meta["version"] == "12.0.2-iris-stub"
    assert "install" not in (drive_meta.get("scripts") or {})
    assert "bindings" not in drive_js.read_text(encoding="utf-8")

    assert _yarn_needs_native_bypass("Could not find any Visual Studio installation to use")
    assert _yarn_needs_native_bypass("error ... @theia/ffmpeg: Command failed")
    assert _yarn_needs_native_bypass(r"error C:\app\node_modules\drivelist: Command failed.")
    assert _yarn_needs_native_bypass("prebuild-install warn install No prebuilt binaries found")
    assert not _yarn_needs_native_bypass("network timeout")
    assert not _yarn_needs_native_bypass(
        'error Received malformed response from registry for "@theia/variable-resolver"'
    )

    native = (
        "info No lockfile found.\n"
        + ("warn padding\n" * 400)
        + "error C:\\Users\\x\\node_modules\\drivelist: Command failed.\n"
        + "prebuild-install warn install No prebuilt binaries found (target=8 runtime=napi)\n"
        + "gyp ERR! find VS could not find any Visual Studio installation to use\n"
        + ("at NpmResolver.findVersionInRegistryResponse (yarn\\lib\\cli.js:50357:19)\n" * 8)
    )
    assert "visual studio" not in native[-240:].lower()
    diag = _command_failure_text(native)
    assert _yarn_needs_native_bypass(diag)
    assert _yarn_user_message(diag).lower().startswith("error ") or "visual studio" in _yarn_user_message(diag).lower()
    registry = (
        'error Received malformed response from registry for "@theia/variable-resolver". '
        "The registry may be down.\n"
        + ("at NpmResolver.findVersionInRegistryResponse (yarn\\lib\\cli.js:50357:19)\n" * 6)
    )
    assert _yarn_needs_native_bypass(diag + "\n" + registry)
    assert not _yarn_needs_native_bypass(registry)
    assert _yarn_registry_flake(registry)
    assert "malformed response" in _yarn_user_message(registry).lower()
    assert len(_yarn_user_message(registry)) <= 240

    import subprocess

    from iris.system.node_runtime import node_executable

    listed = subprocess.run(
        [
            node_executable(),
            "-e",
            "const d=require(process.argv[1]); d.list().then(xs=>{"
            "if(!xs.length||!xs[0].mountpoints||!xs[0].mountpoints[0].path) process.exit(2);"
            "process.stdout.write(xs[0].mountpoints[0].path);"
            "}).catch(e=>{console.error(e); process.exit(1);})",
            str(drive_js),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.strip()

    print("iris_ide_ffmpeg_stub check ok", stub_pkg, listed.stdout.strip())


if __name__ == "__main__":
    main()
