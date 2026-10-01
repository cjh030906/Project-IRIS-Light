"""채팅 턴의 자료 발췌 — UI 스레드 밖에서 읽는다."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class MaterialReadWorker(QThread):
    finished_text = pyqtSignal(str)

    def __init__(
        self,
        text: str,
        attachments: list[str],
        *,
        bases: list[str],
        skip_image_files: bool,
        vision_spec: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._attachments = list(attachments)
        self._bases = list(bases)
        self._skip_image_files = skip_image_files
        self._spec = dict(vision_spec)

    def run(self) -> None:
        from iris.knowledge.material_excerpt import build_material_block
        from iris.knowledge.page_vision import transcribe_images

        spec = self._spec

        def vision(pngs: list[bytes]) -> str:
            if not str(spec.get("model") or "").strip():
                return ""
            return transcribe_images(
                pngs,
                model=str(spec.get("model") or ""),
                ollama_base_url=str(spec.get("ollama_base_url") or ""),
                api_base_url=str(spec.get("api_base_url") or ""),
                api_key=str(spec.get("api_key") or ""),
                auth_style=str(spec.get("auth_style") or "bearer"),
            )

        try:
            block = build_material_block(
                self._text,
                self._attachments,
                bases=self._bases,
                skip_image_files=self._skip_image_files,
                vision_reader=vision if str(spec.get("model") or "").strip() else None,
            )
        except Exception as exc:  # noqa: BLE001
            block = f"[자료 본문]\n(읽지 못함) {exc}"
        self.finished_text.emit(block)
