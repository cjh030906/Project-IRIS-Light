"""Hermes uv mount failure detection / wipe helpers.

실행:
  .venv\\Scripts\\python.exe -m unittest tests.test_hermes_install_bypass -v
  .venv\\Scripts\\python.exe -m iris.system.hermes_install
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import hermes_install as hi
from iris.system.setup_protocol import SetupProtocol


class HermesInstallBypassTests(unittest.TestCase):
    def test_detect_winerror_448(self) -> None:
        sample = (
            "Downloading cpython-3.11.16-windows-x86_64-none\n"
            "error: Failed to create Python minor version link directory\n"
            "  cause: 경로에 신뢰할 수 없는 탑재 지점이 포함되어 있기 때문에 "
            "경로를 통과할 수 없습니다. (os error 448)\n"
            "[X] Failed to install Python 3.11\n"
            "[X] Installation failed: Python 3.11 not available\n"
        )
        self.assertTrue(hi.looks_like_uv_python_mount_failure(sample))

    def test_detect_negative(self) -> None:
        self.assertFalse(hi.looks_like_uv_python_mount_failure("gateway /health timeout"))

    def test_find_bootstrap_python_skips_unsupported_iris_venv(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iris_python = root / ".venv" / "Scripts" / "python.exe"
            fallback_python = root / ".venv" / "bin" / "python"
            iris_python.parent.mkdir(parents=True)
            fallback_python.parent.mkdir(parents=True)
            iris_python.touch()
            fallback_python.touch()

            def version(path: Path) -> tuple[int, int]:
                return (3, 14) if "Scripts" in path.parts else (3, 13)

            with (
                patch("iris.system.hermes_iris_control_sync.project_root", return_value=root),
                patch.object(hi, "python_version", side_effect=version),
                patch.object(hi.shutil, "which", return_value=None),
                patch.object(hi.sys, "executable", ""),
            ):
                self.assertEqual(hi.find_bootstrap_python(), fallback_python)

    def test_force_retire_renames_locked_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "hermes"
            agent = home / "hermes-agent"
            (agent / ".git" / "objects").mkdir(parents=True)
            (agent / ".git" / "objects" / "pack.idx").write_text("x", encoding="utf-8")
            with (
                patch.object(hi.gw, "hermes_home", return_value=home),
                patch.object(hi.gw, "stop_hermes_gateway", return_value=True),
                patch.object(hi, "_kill_hermes_tree_holders"),
            ):
                msg = hi.force_retire_hermes_agent()
            self.assertFalse(agent.exists())
            self.assertTrue("치움" in msg or "삭제" in msg, msg)


class HermesInstallLogAndStagingTests(unittest.TestCase):
    def test_error_tail_keeps_error_not_obtaining_head(self) -> None:
        blob = "Obtaining file:///C:/hermes-agent\nInstalling build dependencies\n" + (
            "noise\n" * 30
        ) + "ERROR: resolution failed for aiohttp\n"
        tail = hi.error_log_tail(blob)
        msg = hi.format_install_failure("pip 설치 실패", blob, Path("C:/logs/iris-install.log"), "exit")
        self.assertIn("ERROR:", tail)
        self.assertIn("ERROR:", msg)
        self.assertNotIn("Obtaining file", tail)
        self.assertIn("iris-install.log", msg)

    def test_bootstrap_prefers_py311_over_iris_313(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iris = root / ".venv" / "Scripts" / "python.exe"
            iris.parent.mkdir(parents=True)
            iris.write_bytes(b"")
            py311 = root / "py311" / "python.exe"
            py311.parent.mkdir()
            py311.write_bytes(b"")

            def which(name: str):
                return "py.exe" if name == "py" else None

            def run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, str(py311) + "\n", "")

            with (
                patch("iris.system.hermes_iris_control_sync.project_root", return_value=root),
                patch.object(hi.shutil, "which", side_effect=which),
                patch.object(hi, "_run", side_effect=run),
                patch.object(hi, "is_supported_hermes_python", return_value=True),
                patch.object(hi.sys, "platform", "win32"),
            ):
                self.assertEqual(hi.find_bootstrap_python(), py311)

    def test_staging_failure_keeps_live_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "hermes"
            live = home / "hermes-agent"
            live.mkdir(parents=True)
            (live / "KEEP").write_text("ok", encoding="utf-8")

            def run(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 1, "Obtaining file:///\n", "ERROR: clone failed\n")

            with (
                patch.object(hi.gw, "hermes_home", return_value=home),
                patch.object(hi.gw, "probe_hermes_runtime", return_value=(False, "missing")),
                patch.object(hi, "ensure_system_python_winget", return_value=Path("python")),
                patch.object(hi, "python_version", return_value=(3, 11)),
                patch.object(hi.shutil, "which", side_effect=lambda n: "git" if n == "git" else None),
                patch.object(hi, "_run", side_effect=run),
            ):
                result = hi.install_hermes_with_system_python()
            self.assertFalse(result.ok)
            self.assertIn("ERROR:", result.message)
            self.assertTrue((live / "KEEP").is_file())
            self.assertFalse(any(p.name.startswith("hermes-agent.staging-") for p in home.iterdir()))
            self.assertTrue(result.log_path)
            self.assertTrue(Path(result.log_path).is_file())

    def test_editable_import_survives_staging_rename(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staging = root / "hermes-agent.staging"
            pkg = staging / "pkg"
            pkg.mkdir(parents=True)
            (pkg / "pyproject.toml").write_text(
                '[project]\nname="tinyrel"\nversion="0.0.1"\n',
                encoding="utf-8",
            )
            (pkg / "tinyrel.py").write_text("X=1\n", encoding="utf-8")
            venv = staging / "venv"
            subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
            py = venv / "Scripts" / "python.exe"
            subprocess.check_call([str(py), "-m", "pip", "install", "-q", "-e", str(pkg)])
            live = root / "hermes-agent"
            old = Path(staging)
            staging.rename(live)
            broken = subprocess.run(
                [str(live / "venv" / "Scripts" / "python.exe"), "-c", "import tinyrel"],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(broken.returncode, 0)
            hi._retarget_moved_tree(live, old, live)
            fixed = subprocess.run(
                [str(live / "venv" / "Scripts" / "python.exe"), "-c", "import tinyrel; print(tinyrel.X)"],
                capture_output=True,
                text=True,
            )
            self.assertEqual(fixed.returncode, 0, fixed.stderr)
            self.assertIn("1", fixed.stdout)

    def test_post_swap_probe_failure_restores_live(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            live = home / "hermes-agent"
            live.mkdir()
            (live / "KEEP").write_text("ok", encoding="utf-8")
            staging = home / "hermes-agent.staging-1"
            staging.mkdir()
            (staging / "NEW").write_text("x", encoding="utf-8")
            with patch.object(hi.gw, "probe_hermes_runtime", return_value=(False, "import failed")):
                ok, detail = hi._activate_staged(home, staging, "1", "hermes")
            self.assertFalse(ok)
            self.assertIn("import failed", detail)
            self.assertTrue((home / "hermes-agent" / "KEEP").is_file())
            self.assertFalse((home / "hermes-agent" / "NEW").exists())

    def test_lock_blocks_live_pid(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            lock = home / "iris-hermes-install.lock"
            lock.write_text(str(os.getpid()), encoding="utf-8")
            with self.assertRaises(hi.InstallBusy):
                with hi.hermes_install_lock(home):
                    pass


class HermesInstallProtocolTests(unittest.TestCase):
    def _proto(self):
        proto = SetupProtocol(dry_run=False, simulate=False)
        proto._save_state = lambda: None  # type: ignore[method-assign]
        return proto

    def test_official_failure_bypasses_once(self) -> None:
        proto = self._proto()
        calls = {"n": 0}

        def bypass():
            calls["n"] += 1
            return proto._hermes_done("bypass ok")

        proc = subprocess.CompletedProcess(["ps"], 1, "ERROR: official\n", "")
        with (
            patch("iris.system.setup_protocol.probe_hermes_runtime", return_value=(False, "no")),
            patch.object(proto, "_run_hermes_official_installer", return_value=proc),
            patch.object(proto, "_install_hermes_bypass", side_effect=bypass),
            patch("iris.system.hermes_install.write_install_log", return_value=Path("C:/t.log")),
        ):
            result = proto._install_hermes()
        self.assertEqual(calls["n"], 1)
        self.assertEqual(result.status, "done")
        self.assertEqual(proto._state.get("last_error_detail"), {})

    def test_official_rc0_probe_fail_bypasses(self) -> None:
        proto = self._proto()
        calls = {"n": 0}

        def bypass():
            calls["n"] += 1
            return proto._hermes_done("bypass ok")

        proc = subprocess.CompletedProcess(["ps"], 0, "script done\n", "")
        with (
            patch("iris.system.setup_protocol.probe_hermes_runtime", return_value=(False, "import fail")),
            patch.object(proto, "_run_hermes_official_installer", return_value=proc),
            patch.object(proto, "_install_hermes_bypass", side_effect=bypass),
            patch("iris.system.hermes_install.write_install_log", return_value=Path("C:/t.log")),
            patch.object(SetupProtocol, "_install_hermes") if False else patch("iris.system.setup_protocol.sys.platform", "win32"),
        ):
            result = proto._install_hermes()
        self.assertEqual(calls["n"], 1)
        self.assertEqual(result.status, "done")

    def test_cancel_does_not_bypass(self) -> None:
        from iris.system.setup_protocol import UserCancelled

        proto = self._proto()
        with (
            patch("iris.system.setup_protocol.probe_hermes_runtime", return_value=(False, "no")),
            patch.object(proto, "_run_hermes_official_installer", side_effect=UserCancelled("사용자가 중단함")),
            patch.object(proto, "_install_hermes_bypass") as bypass,
            patch("iris.system.setup_protocol.sys.platform", "win32"),
        ):
            result = proto._install_hermes()
        bypass.assert_not_called()
        self.assertEqual(result.status, "failed")
        self.assertEqual(proto._state["last_error_detail"]["kind"], "cancel")

    def test_bypass_failure_keeps_error_and_log(self) -> None:
        proto = self._proto()
        blob = "Obtaining file:///hermes-agent\n" + ("x\n" * 20) + "ERROR: wheel build failed\n"
        result_obj = hi.InstallResult(False, hi.format_install_failure("pip 설치 실패", blob, Path("C:/iris-install.log"), "exit"), "exit", "C:/iris-install.log")
        with (
            patch("iris.system.hermes_install.install_hermes_with_system_python", return_value=result_obj),
            patch("iris.system.setup_protocol.refresh_process_path"),
        ):
            result = proto._install_hermes_bypass()
        self.assertIn("ERROR:", result.message)
        self.assertNotIn("Obtaining file", hi.error_log_tail(blob))
        self.assertEqual(result.log_path, "C:/iris-install.log")
        self.assertEqual(proto._state["last_error_detail"]["kind"], "exit")
        self.assertIn("ERROR:", proto._state["last_error_detail"]["tail"])

    def test_stream_idle_hard_and_cancel(self) -> None:
        from iris.system.setup_protocol import InstallStreamTimeout, UserCancelled

        proto = self._proto()
        cmd = [sys.executable, "-c", "import time; time.sleep(5)"]
        with self.assertRaises(InstallStreamTimeout) as idle:
            proto._run_streamed(cmd, timeout=0.3, hard_timeout=30)
        self.assertEqual(idle.exception.kind, "idle")
        with self.assertRaises(InstallStreamTimeout) as hard:
            proto._run_streamed(cmd, timeout=None, hard_timeout=0.4)
        self.assertEqual(hard.exception.kind, "hard")
        proto._abort = True
        with self.assertRaises(UserCancelled):
            proto._run_streamed(cmd, timeout=None, hard_timeout=30)

    def test_redirected_home_does_not_write_user_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            scripts = Path(td) / "Scripts"
            scripts.mkdir()
            before = os.environ.get("PATH", "")
            try:
                with patch("winreg.OpenKey") as open_key:
                    hi._user_path_prepend(scripts)
                open_key.assert_not_called()
                self.assertIn(str(scripts).lower(), os.environ.get("PATH", "").lower())
            finally:
                os.environ["PATH"] = before


if __name__ == "__main__":
    unittest.main()
