"""Hermes uv mount failure detection / wipe helpers / pip 꼬리 메시지.

실행:
  .venv\\Scripts\\python.exe -m unittest tests.test_hermes_install_bypass -v
  .venv\\Scripts\\python.exe -m iris.system.hermes_install
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.system import hermes_install as hi


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

    def test_format_pip_failure_uses_tail_not_head(self) -> None:
        head = "Obtaining file:///C:/Users/x/hermes-agent\nInstalling build dependencies...\n"
        pad = "Collecting something\n" * 40
        err = "ERROR: Could not find a version that satisfies the requirement missing-pkg==9.9.9\n"
        msg = hi.format_pip_failure(
            head + pad + err,
            "",
            log_path=r"C:\Users\x\AppData\Local\hermes\logs\iris-bypass-pip-20260101.log",
        )
        self.assertIn("ERROR:", msg)
        self.assertIn("iris-bypass-pip", msg)
        self.assertIn("missing-pkg", msg)
        # Obtaining만 보이면 실패(회귀) — 사용자 메시지에 실제 ERROR가 있어야 함
        first_content_line = next(
            (ln for ln in msg.splitlines() if ln.strip() and not ln.startswith("pip ")),
            "",
        )
        self.assertFalse(
            first_content_line.startswith("Obtaining "),
            f"head가 사용자 메시지로 노출됨: {first_content_line!r}",
        )

    def test_format_pip_failure_obtaining_only_still_has_log_path(self) -> None:
        """꼬리에 Obtaining만 있어도 로그 경로는 반드시 포함한다."""
        msg = hi.format_pip_failure(
            "Obtaining file:///tmp/hermes-agent\n",
            "",
            log_path="iris-bypass-pip-x.log",
        )
        self.assertIn("로그:", msg)
        self.assertIn("iris-bypass-pip-x.log", msg)

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

    def test_find_bootstrap_python_prefers_311_over_iris_venv(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            iris_python = root / ".venv" / "Scripts" / "python.exe"
            py311 = root / "py311" / "python.exe"
            iris_python.parent.mkdir(parents=True)
            py311.parent.mkdir(parents=True)
            iris_python.touch()
            py311.touch()

            def version(path: Path) -> tuple[int, int]:
                return (3, 11) if "py311" in path.parts else (3, 13)

            def fake_run(cmd, **_kwargs):  # noqa: ANN001
                import subprocess

                # py -3.11 → print executable
                if len(cmd) >= 2 and cmd[1] == "-3.11":
                    return subprocess.CompletedProcess(cmd, 0, str(py311) + "\n", "")
                return subprocess.CompletedProcess(cmd, 1, "", "")

            with (
                patch("iris.system.hermes_iris_control_sync.project_root", return_value=root),
                patch.object(hi, "python_version", side_effect=version),
                patch.object(hi.shutil, "which", side_effect=lambda n: "py.exe" if n == "py" else None),
                patch.object(hi, "_run", side_effect=fake_run),
                patch.object(hi.sys, "platform", "win32"),
                patch.object(hi.sys, "executable", ""),
            ):
                self.assertEqual(hi.find_bootstrap_python(), py311)

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

    def test_force_retire_cleans_staging_keeps_current(self) -> None:
        """R2: 오래된 staging-* 정리, keep_staging 만 보존."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "hermes"
            home.mkdir(parents=True)
            old = home / "hermes-agent.staging-old"
            keep = home / "hermes-agent.staging-keep"
            (old / "x").mkdir(parents=True)
            (keep / "y").mkdir(parents=True)
            (old / "x" / "f").write_text("1", encoding="utf-8")
            (keep / "y" / "f").write_text("2", encoding="utf-8")
            with (
                patch.object(hi.gw, "hermes_home", return_value=home),
                patch.object(hi.gw, "stop_hermes_gateway", return_value=True),
                patch.object(hi, "_kill_hermes_tree_holders"),
            ):
                hi.force_retire_hermes_agent(keep_staging=keep.name)
            self.assertFalse(old.exists())
            self.assertTrue(keep.exists())

    def test_should_skip_official_on_prefer_or_last_error(self) -> None:
        """R1(a): prefer_bypass / last_error.kind=bypass → 공식 생략."""
        self.assertTrue(hi.should_skip_official_installer(prefer_bypass=True))
        self.assertTrue(
            hi.should_skip_official_installer(
                prefer_bypass=False,
                last_error={"kind": "bypass_pip", "tail": "x"},
            )
        )
        self.assertTrue(
            hi.should_skip_official_installer(
                prefer_bypass=False,
                last_error={"kind": "bypass_runtime", "log_path": "a.log"},
            )
        )
        self.assertTrue(
            hi.should_skip_official_installer(
                prefer_bypass=False,
                last_error={
                    "kind": "official",
                    "tail": "cause: untrusted mount (os error 448)",
                },
            )
        )
        self.assertFalse(hi.should_skip_official_installer(prefer_bypass=False))
        self.assertFalse(
            hi.should_skip_official_installer(
                prefer_bypass=False,
                last_error={"kind": "network", "tail": "timeout"},
            )
        )

    def test_format_runtime_failure_includes_log_path(self) -> None:
        """R3: 런타임 실패도 로그 경로 + 꼬리 계약."""
        msg = hi.format_runtime_failure(
            "probe: gateway /health timeout",
            log_path=r"C:\Users\x\AppData\Local\hermes\logs\iris-bypass-pip-rt.log",
        )
        self.assertIn("런타임 실패", msg)
        self.assertIn("iris-bypass-pip-rt", msg)
        self.assertIn("health", msg)

    def test_clip_needs_user_message_limit(self) -> None:
        """R4: NeedsUser message ≤800자(꼬리)."""
        long = "Obtaining file://…\n" + ("pad\n" * 100) + ("ERROR: boom\n" * 5)
        clipped = hi.clip_needs_user_message(long)
        self.assertLessEqual(len(clipped), hi._NEEDS_USER_MSG_LIMIT)
        self.assertIn("ERROR:", clipped)

    def test_install_hermes_skips_official_when_prefer_bypass(self) -> None:
        """R1(a): prefer_bypass면 공식 설치기 미호출."""
        from iris.system.setup_protocol import SetupProtocol

        proto = SetupProtocol(dry_run=False, simulate=False)
        proto._hermes_prefer_bypass = True
        called: list[str] = []

        def fake_bypass() -> object:
            called.append("bypass")
            from iris.system.setup_protocol import SetupStepResult

            return SetupStepResult(
                step_id="hermes_install",
                status="done",
                message="ok",
                label="Hermes",
            )

        with (
            patch.object(proto, "_install_hermes_bypass", side_effect=fake_bypass),
            patch.object(proto, "_run_hermes_official_installer") as official,
            patch(
                "iris.system.setup_protocol.probe_hermes_runtime",
                return_value=(False, "missing"),
            ),
            patch.object(proto, "_wipe_hermes_agent_runtime", return_value=""),
        ):
            result = proto._install_hermes()
        self.assertEqual(result.status, "done")
        self.assertEqual(called, ["bypass"])
        official.assert_not_called()


if __name__ == "__main__":
    unittest.main()
