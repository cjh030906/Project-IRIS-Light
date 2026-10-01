"""PDF 저장 — UI 스레드 밖에서 자식 프로세스를 기다린다."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class PdfExportWorker(QThread):
    finished_ok = pyqtSignal(str)
    finished_err = pyqtSignal(str)

    def __init__(self, text: str, dest: Path, parent=None) -> None:
        super().__init__(parent)
        self._text = text
        self._dest = dest

    def run(self) -> None:
        from iris.knowledge.pdf_export import save_pdf, trace

        try:
            result = save_pdf(self._text, self._dest)
        except Exception as exc:  # noqa: BLE001
            trace(f"[PDF] generation failed: {exc}")
            trace("[PDF] worker finished")
            self.finished_err.emit(f"PDF 저장에 실패했습니다: {exc}")
            return
        trace("[PDF] worker finished")
        if result.get("ok"):
            self.finished_ok.emit(str(result.get("path") or ""))
            return
        self.finished_err.emit(str(result.get("error") or "PDF 저장에 실패했습니다."))
