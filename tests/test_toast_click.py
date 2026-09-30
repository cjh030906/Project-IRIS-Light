"""토스트 클릭 — URI 스킴 등록과 클릭 처리.

클릭 활성화는 눌러보기 전엔 틀린 걸 알기 어렵다(Windows 가 조용히 무시한다).
그래서 "무엇을 보냈나"와 "눌리면 무엇을 하나"를 코드 수준에서 못박는다.
"""

from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from iris.system import uri_handler
from iris.system.desktop_toast import build_toast_xml
from iris.system.uri_handler import build_command, open_uri, parse_uri, routine_uri


class UriParsingTests(TestCase):
    def test_routine_uri_round_trip(self) -> None:
        self.assertEqual(routine_uri(12), "iris-light://routine/12")
        self.assertEqual(parse_uri(routine_uri(12)), ("routine", "12"))

    def test_tolerates_what_windows_actually_hands_over(self) -> None:
        """`%1` 로 들어오는 값은 따옴표·대소문자·꼬리 슬래시가 섞인다."""
        for raw in (
            "iris-light://routine/7",
            "iris-light://routine/7/",
            '"iris-light://routine/7"',
            "IRIS-LIGHT://routine/7",
        ):
            self.assertEqual(parse_uri(raw), ("routine", "7"), raw)

    def test_unknown_input_falls_back_to_plain_open(self) -> None:
        """남의 스킴이나 쓰레기가 와도 앱만 열지, 엉뚱한 짓을 하면 안 된다."""
        for raw in ("", "https://evil.example/x", "iris-light://", "iris-light://뭔가/1"):
            self.assertEqual(parse_uri(raw), ("open", ""), raw)
        self.assertEqual(parse_uri(open_uri()), ("open", ""))

    def test_handler_command_quotes_paths_and_takes_the_uri(self) -> None:
        from pathlib import Path

        cmd = build_command(Path(r"C:\py w\pythonw.exe"), Path(r"C:\my proj\routine_cli.py"))
        self.assertTrue(cmd.endswith('open --uri "%1"'))
        self.assertEqual(cmd.count('"'), 6)


class ToastMarkupTests(TestCase):
    def test_clickable_toast_declares_protocol_activation(self) -> None:
        xml = build_toast_xml("제목", "본문", launch=routine_uri(3))
        self.assertIn("activationType='protocol'", xml)
        self.assertIn("launch='iris-light://routine/3'", xml)

    def test_plain_toast_has_no_activation(self) -> None:
        self.assertNotIn("activationType", build_toast_xml("제목", "본문"))
        self.assertNotIn("activationType", build_toast_xml("제목", "본문", launch="  "))

    def test_launch_value_is_escaped(self) -> None:
        xml = build_toast_xml("t", "b", launch="x://a?b=1&c=2")
        self.assertIn("&amp;", xml)
        self.assertNotIn("?b=1&c=2", xml)


class ClickHandlingTests(TestCase):
    def _open(self, uri: str, *, running: bool):
        from iris import routine_cli

        calls: list[tuple] = []
        launched: list[int] = []
        with (
            patch.object(routine_cli, "iris_is_running", return_value=running),
            patch.object(
                routine_cli,
                "_invoke",
                side_effect=lambda a, args=None, **k: calls.append((a, args)) or {"ok": True},
            ),
            patch.object(
                routine_cli,
                "_launch_iris",
                side_effect=lambda: launched.append(1) or True,
            ),
            patch.object(
                routine_cli,
                "_open_routine_note",
                side_effect=lambda rid: calls.append(("note", rid)),
            ),
        ):
            code = routine_cli.open_target(uri)
        return code, calls, launched

    def test_closed_iris_gets_launched(self) -> None:
        code, calls, launched = self._open(routine_uri(12), running=False)
        self.assertEqual(code, 0)
        self.assertEqual(launched, [1])
        self.assertEqual(calls, [])

    def test_running_iris_is_brought_forward_and_opens_the_routine(self) -> None:
        code, calls, launched = self._open(routine_uri(12), running=True)
        self.assertEqual(code, 0)
        self.assertEqual(launched, [])
        self.assertEqual(calls, [("window.show", None), ("note", 12)])

    def test_plain_open_just_shows_the_window(self) -> None:
        _, calls, _ = self._open(open_uri(), running=True)
        self.assertEqual(calls, [("window.show", None)])

    def test_non_numeric_routine_id_does_not_reach_the_database(self) -> None:
        _, calls, _ = self._open("iris-light://routine/;DROP", running=True)
        self.assertEqual(calls, [("window.show", None)])

    def test_dead_surface_with_stale_files_relaunches(self) -> None:
        """포트 파일만 남고 프로세스가 죽었으면 앞으로 부를 창이 없다."""
        from iris import routine_cli

        launched: list[int] = []
        with (
            patch.object(routine_cli, "iris_is_running", return_value=True),
            patch.object(routine_cli, "_invoke", return_value=None),
            patch.object(
                routine_cli, "_launch_iris", side_effect=lambda: launched.append(1) or True
            ),
        ):
            code = routine_cli.open_target(routine_uri(1))
        self.assertEqual(code, 0)
        self.assertEqual(launched, [1])


class SchemeRegistrationTests(TestCase):
    def test_unsupported_platform_degrades_quietly(self) -> None:
        with patch.object(uri_handler, "is_supported", return_value=False):
            self.assertFalse(uri_handler.register().registered)
            self.assertFalse(uri_handler.query().registered)
            self.assertFalse(uri_handler.unregister().registered)

    def test_registering_twice_is_a_no_op(self) -> None:
        """이미 맞게 돼 있으면 레지스트리를 다시 쓰지 않는다."""
        command = uri_handler.build_command()
        current = uri_handler.SchemeStatus(True, command=command, detail="등록됨")
        with (
            patch.object(uri_handler, "is_supported", return_value=True),
            patch.object(uri_handler, "query", return_value=current),
        ):
            status = uri_handler.register()
        self.assertTrue(status.registered)
        self.assertEqual(status.command, command)

    def test_toast_skips_launch_when_the_scheme_cannot_be_registered(self) -> None:
        """스킴을 못 걸면 누를 수 없는 토스트다 — 알림 자체는 그래도 띄운다."""
        from iris.system import desktop_toast

        sent: list[tuple] = []
        with (
            patch.object(desktop_toast, "is_supported", return_value=True),
            patch.object(desktop_toast, "ensure_click_handler", return_value=False),
            patch.object(desktop_toast, "resolve_app_id", return_value="Iris.Light"),
            patch.object(
                desktop_toast,
                "_send",
                side_effect=lambda h, t, a, launch="": sent.append((h, t, a, launch)) or True,
            ),
        ):
            ok = desktop_toast.show_toast("제목", "본문", launch=routine_uri(5))
        self.assertTrue(ok)
        self.assertEqual(sent[0][3], "")  # launch 를 비워서 보냈다
