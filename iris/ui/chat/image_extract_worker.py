"""사진에서 코드만 뽑는 백그라운드 호출. 키는 시그널에 실지 않는다."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from iris.ui.chat.file_write_claim import extract_image_code


class ImageExtractWorker(QThread):
    done = pyqtSignal(str)

    def __init__(self, image: str, options: dict, parent=None) -> None:
        super().__init__(parent)
        self._image = image
        self._options = dict(options)

    def run(self) -> None:
        try:
            text = extract_image_code(self._image, **self._options)
        except Exception:
            text = ""
        self.done.emit(text or "")
