"""Real MainWindow -> configured worker -> model -> Qt rendering QA.

Uses an isolated conversation DB. Does not mock responses or rendering; disables
voice and automatic IDE file writes to avoid unrelated side effects during QA.
"""
from __future__ import annotations
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from iris.ui.qt_bootstrap import ensure_qt_webengine_ready

ensure_qt_webengine_ready()
from iris.ui.window.main_window import MainWindow

PROMPTS = [
    "TCP 3-way handshake 과정을 초보자도 이해할 수 있게 설명해줘.",
    "Python으로 1부터 100까지 합을 구하는 코드를 작성하고 설명해줘.",
    "TCP 3-way handshake의 SYN, SYN-ACK, ACK를 표로 정리해줘.",
    "다음 내용을 제목, 목록, 인용문, 코드블록을 모두 사용해서 설명해줘.\n주제: HTTP 요청 흐름",
]

def main():
    app = QApplication([])
    win = MainWindow(test_mode=True)
    win._voice_prefs.tts_enabled = False
    win._feed_live_vibe_stream = lambda *args, **kwargs: None
    win._try_reveal_local_vibe_code = lambda *args, **kwargs: None
    win.resize(1280, 1000)
    win.show()
    out = Path(".iris_light_test_tmp/chat-live")
    out.mkdir(parents=True, exist_ok=True)
    start = int(sys.argv[1]) - 1 if len(sys.argv) > 1 else 0
    state = {"index": start, "started": 0.0, "worker_seen": False, "frames": 0}
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))[:start] if start else []
    print("backend:", win._backend_label(), "model:", win._settings.ollama_model, flush=True)

    def submit():
        index = state["index"]
        state.update(started=time.monotonic(), worker_seen=False, frames=0)
        win._last_assistant_text = ""
        win._chat._input.setText(PROMPTS[index])
        win._chat._emit_send()
        timer.start()
        print("submitted", index + 1, flush=True)

    def poll():
        index = state["index"]
        worker = win._chat_worker
        state["worker_seen"] |= worker is not None
        if win._chat._stream_active and state["frames"] < 3:
            state["frames"] += 1
            win.grab().save(str(out / f"test-{index+1}-stream-{state['frames']}.png"))
        elapsed = time.monotonic() - state["started"]
        if elapsed < 1 or worker is not None:
            if elapsed < 240:
                return
            print("timeout", index + 1, flush=True)
            win._on_chat_stop()
        raw = win._last_assistant_text
        # Capture processes Qt events; stop polling before doing so to prevent
        # reentrant completion of the next test using this response.
        timer.stop()
        win._chat.finish_typing()
        rendered = win._chat._log.toPlainText()
        doc = win._chat._log.toHtml()
        item = {"test": index + 1, "response_received": bool(raw), "seconds": round(elapsed, 1),
                "stream_frames": state["frames"], "raw_chars": len(raw),
                "numeric_entity_visible": bool(re.search(r"&#(?:x[0-9a-fA-F]+|\d+);", rendered)),
                "code_card": "iris-copy://" in doc, "tables": doc.count("<table")}
        results.append(item)
        (out / f"test-{index+1}-raw.md").write_text(raw, encoding="utf-8")
        (out / f"test-{index+1}-rendered.txt").write_text(rendered, encoding="utf-8")
        (out / f"test-{index+1}.html").write_text(doc, encoding="utf-8")
        win._chat._log.verticalScrollBar().setValue(0)
        win.grab().save(str(out / f"test-{index+1}-main.png"))
        # Same response in actual IDE companion mode, with the same ChatPanel.
        win._ui_mode = "ide_companion"
        win._chat._log.resize(480, win._chat._log.height())
        app.processEvents()
        win._chat._log.grab().save(str(out / f"test-{index+1}-ide-log.png"))
        print(json.dumps(item, ensure_ascii=False), flush=True)
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        state["index"] += 1
        if state["index"] == len(PROMPTS):
            timer.stop()
            app.quit()
        else:
            QTimer.singleShot(100, submit)

    timer = QTimer()
    timer.setInterval(500)
    timer.timeout.connect(poll)
    QTimer.singleShot(1000, submit)
    app.exec()
    return 0 if len(results) == 4 and all(r["response_received"] for r in results) else 1

if __name__ == "__main__":
    sys.exit(main())
