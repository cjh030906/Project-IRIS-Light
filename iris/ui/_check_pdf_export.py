"""ponytail: PDF 저장 self-check. 자식 크래시·슬롯 TypeError가 이 프로세스를 죽이면 실패.

  py -3 -m iris.ui._check_pdf_export
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader

from iris.knowledge.pdf_export import is_pdf_save_intent, output_path_for, save_pdf


def _text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def main() -> None:
    assert is_pdf_save_intent("PDF로 저장해줘")
    assert is_pdf_save_intent("이 내용을 PDF로 만들어줘")
    assert not is_pdf_save_intent("이 pdf 위키에 저장해줘")
    assert output_path_for("네트워크보안.pdf 로 저장해줘").name == "네트워크보안.pdf"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        en = root / "hello.pdf"
        got = save_pdf("Hello PDF export.", en)
        assert got["ok"] and en.is_file(), got
        assert "Hello" in _text(en)

        ko = root / "한글 문서.pdf"
        got = save_pdf("한글 PDF 저장 테스트 — 네트워크 보안", ko)
        assert got["ok"] and ko.is_file(), got
        assert "한글" in _text(ko) or "네트워크" in _text(ko)

        long_path = root / "long.pdf"
        got = save_pdf("\n".join(f"문단 {i} 네트워크 보안 문서" for i in range(80)), long_path)
        assert got["ok"], got
        assert len(PdfReader(str(long_path)).pages) >= 2

        again = save_pdf("overwrite", en)
        assert again["ok"] and "overwrite" in _text(en).lower() or "overwrite" in _text(en)

        blocked = root / "not-a-dir"
        blocked.write_text("x", encoding="utf-8")
        bad = save_pdf("nope", blocked / "out.pdf")
        assert bad["ok"] is False, bad
        assert "PDF 저장에 실패했습니다" in str(bad["error"])

        illegal = save_pdf("nope", root / "bad|name.pdf")
        assert illegal["ok"] is False

        code = root / "code.pdf"
        got = save_pdf("```python\ndef ping():\n    return '한글'\n```", code)
        assert got["ok"], got
        assert "ping" in _text(code)

        table = root / "table.pdf"
        got = save_pdf("| 항목 | 값 |\n| --- | --- |\n| 보안 | 네트워크 |", table)
        assert got["ok"], got
        assert "네트워크" in _text(table)

        ko_dir = root / "한글폴더"
        ko_file = ko_dir / "메모.pdf"
        got = save_pdf("경로에 한글이 있는 PDF", ko_file)
        assert got["ok"] and ko_file.is_file(), got

        for i in range(3):
            got = save_pdf(f"연속 저장 {i}", en)
            assert got["ok"], got
        assert "연속 저장 2" in _text(en)

        empty = save_pdf("   ", en)
        assert empty["ok"] is False

    proc = subprocess.run(
        [sys.executable, "-m", "iris.knowledge.pdf_export", "--abort"],
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    _check_ui_survives()
    print("pdf_export self-check ok")


def _check_ui_survives() -> None:
    """완료 콜백·다이얼로그 닫기·워커 종료가 이 프로세스를 끝내면 실패."""
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QDialog, QWidget

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from iris.ui.window.main_window import MainWindow
    from iris.ui.workers.pdf_export_worker import PdfExportWorker

    class Fake:
        def __init__(self) -> None:
            self.msgs: list[tuple[str, str]] = []
            self.generating = True
            self.history: list[tuple[str, str]] = []
            self.finished: list[str | None] = []
            self._chat = self
            self._turn_gate = self
            self._turn_dispatcher = self
            self.active_turn = None

        def set_generating(self, active: bool) -> None:
            self.generating = active

        def append_message_instant(self, who: str, text: str) -> None:
            self.msgs.append((who, text))

        def _record_history(self, role: str, text: str) -> None:
            self.history.append((role, text))

        def _refresh_context_gauge(self) -> None:
            return None

        def finish(self, turn_id: str | None) -> str | None:
            self.finished.append(turn_id)
            return turn_id

        def _sync_voice_conversation_state(self) -> None:
            return None

        def _finish_current_turn(self, turn_id: str | None = None, *, open_followup: bool = False) -> None:
            MainWindow._finish_current_turn(self, turn_id, open_followup=open_followup)

    class Host(QObject):
        ping = pyqtSignal(str)

    fake = Fake()
    host = Host()
    host.ping.connect(lambda path: MainWindow._on_pdf_export_ok(fake, "t1", path))
    host.ping.emit(r"C:\Users\iris\Documents\IRIS\iris-note.pdf")
    app.processEvents()
    assert fake.finished == ["t1"], fake.finished
    assert fake.generating is False
    assert fake.history and "PDF로 저장했습니다" in fake.history[-1][1]

    host2 = Host()
    host2.ping.connect(lambda _path: MainWindow._finish_current_turn(fake, "t2"))
    host2.ping.emit("x")
    app.processEvents()
    assert "t2" in fake.finished

    host3 = Host()
    host3.ping.connect(lambda err: MainWindow._on_pdf_export_err(fake, "t3", err))
    host3.ping.emit("PDF 저장에 실패했습니다: 테스트")
    app.processEvents()
    assert "t3" in fake.finished
    assert any("실패" in text for _role, text in fake.history)

    main = QWidget()
    main.setWindowTitle("iris-pdf-check")
    main.resize(320, 120)
    main.show()
    dialog = QDialog(main)
    dialog.setWindowTitle("save-cancel")
    dialog.show()
    app.processEvents()
    dialog.close()
    dialog.deleteLater()
    app.processEvents()
    assert main.isVisible()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        class Sink(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.box: dict[str, str] = {}

            def on_ok(self, path: str) -> None:
                self.box["ok"] = path

            def on_err(self, err: str) -> None:
                self.box["err"] = err

        def run_worker(text: str, dest: Path) -> dict[str, str]:
            sink = Sink()
            worker = PdfExportWorker(text, dest)
            worker.finished_ok.connect(sink.on_ok)
            worker.finished_err.connect(sink.on_err)
            worker.start()
            deadline = time.monotonic() + 45
            while "ok" not in sink.box and "err" not in sink.box and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.02)
            worker.wait(3000)
            return sink.box

        first = run_worker("일반 텍스트 답변", root / "plain.pdf")
        assert "ok" in first, first
        second = run_worker("두 번째 질문 이후에도 살아 있다", root / "next.pdf")
        assert "ok" in second, second
        bad = run_worker("nope", root / "bad|name.pdf")
        assert "err" in bad, bad
        third = run_worker("연속 세 번째", root / "third.pdf")
        assert "ok" in third, third

    main.close()
    app.processEvents()
    print("pdf ui still alive", flush=True)


if __name__ == "__main__":
    main()
