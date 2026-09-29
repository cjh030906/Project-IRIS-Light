"""실제 MainWindow로 History 기록 → 모델 전환 → 맥락 이관을 한 번 돌려 본다.

사용자의 진짜 위키(`~/.iris-light/iris-wiki`)를 더럽히지 않도록 창을 띄운 뒤
임시 위키로 갈아끼운다.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from iris.ui.qt_bootstrap import ensure_qt_webengine_ready


def main() -> None:
    ensure_qt_webengine_ready()
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from iris.knowledge.history_store import count_entries, list_entries
    from iris.knowledge.iris_wiki import IrisWiki
    from iris.runtime.model_switch import ModelSwitchService
    from iris.storage.database import Database
    from iris.storage.failover_prefs import (
        FallbackEntry,
        load_failover_settings,
        save_failover_settings,
    )
    from iris.ui.window.main_window import MainWindow

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        win = MainWindow(test_mode=True)
        app.processEvents()

        # 0) 갓 띄운 창이 전환 관련 상태를 다 갖고 있어야 한다. 하나라도 빠지면
        #    전환 전 첫 메시지에서 AttributeError 로 죽는다(실제로 났던 버그).
        for attr in (
            "_model_switch",
            "_pending_handoff",
            "_pending_handoff_ctx",
            "_last_archive_id",
            "_handoff_summary_worker",
            "_history_embed_worker",
        ):
            assert hasattr(win, attr), f"MainWindow.__init__ 이 {attr} 를 안 만든다"
        win._chat_messages_with_project_context()  # 전환 전에도 조립이 되어야 한다
        print("  초기 상태 · 첫 메시지 조립 ok")

        # 진짜 사용자 데이터 대신 임시 DB·위키로 갈아끼운다
        db = Database(root / "smoke.db")
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        # win._db 는 그대로 둔다 — 창 내부가 쓰는 연결을 뺏으면 종료가 지저분해진다.
        # 새 기능은 전부 _model_switch 를 거치므로 그것만 임시 DB로 바꾸면 된다.
        win._iris_wiki = wiki
        win._model_switch = ModelSwitchService(db, wiki=wiki)
        win._conversation_id = 1
        win._history = []
        win._pending_handoff = ""
        win._context_limit_cache = {}
        # 전환으로 치려면 "이전 모델"이 있어야 한다 — test_mode는 비어 있다
        win._settings.ollama_model = "big:paid"
        win._context_limit_cache["big:paid"] = 1_000_000

        # 1) 대화·수행·입력이 History에 쌓인다
        for role, text in (
            ("user", "설치 프로그램이 권한 오류로 죽습니다"),
            ("assistant", "venv 폴더 소유권을 고치면 됩니다"),
            ("user", "0.1.16으로 올려주세요"),
        ):
            win._history.append({"role": role, "content": text})
            win._record_wiki_history("chat", text, role=role)
        win._record_wiki_history("action", "setup.ps1 -Recreate 실행", title="설치 재시도")
        win._record_wiki_history("input", "오류 로그 붙여넣기", source="clipboard")

        assert count_entries(db) == 5, count_entries(db)
        day_files = list((wiki.user_root / "history").rglob("*.md"))
        assert day_files, "위키 History 파일이 안 생김"
        day_text = "\n".join(f.read_text(encoding="utf-8") for f in day_files)
        assert "설치 프로그램이 권한 오류로 죽습니다" in day_text
        assert "setup.ps1 -Recreate 실행" in day_text
        print(f"  기록 5건 · 위키 파일 {len(day_files)}개")

        # 2) 검색이 과거 기록을 찾아낸다
        hits = win._model_switch.retrieve("권한 오류")
        assert hits, "History 검색 결과 없음"
        print(f"  검색 '권한 오류' → {len(hits)}건 (상위: {hits[0].entry.body[:20]}…)")

        # 3) 큰 대화 → 작은 모델로 전환하면 인수인계문이 붙는다
        win._history.append({"role": "assistant", "content": "가" * 30000})
        win._context_limit_cache["tiny:free"] = 4096
        win._apply_selected_model("tiny:free", persist=False)
        assert win._pending_handoff, "좁은 컨텍스트인데 인수인계문이 없다"
        assert "0.1.16으로 올려주세요" in win._pending_handoff
        assert "설치 프로그램이 권한 오류로 죽습니다" in win._pending_handoff
        print(f"  전환(좁은 컨텍스트) → 인수인계문 {len(win._pending_handoff)}자")

        # 4) 넉넉한 모델로 가면 원문 그대로 — 요약으로 정보를 잃지 않는다
        win._pending_handoff = ""
        win._apply_selected_model("big:paid", persist=False)
        assert win._pending_handoff == "", "원문이 들어가는데 요약을 끼웠다"
        print("  전환(넉넉한 컨텍스트) → 원문 그대로")

        # 5) 전환 기록이 History에 남는다
        switches = [e for e in list_entries(db) if e.tags == "model-switch"]
        assert len(switches) == 2, [e.title for e in switches]
        print(f"  모델 전환 기록 {len(switches)}건")

        # 6) 자동 전환 체인이 설정대로 만들어진다
        settings = load_failover_settings(db)
        settings.chain = [FallbackEntry(model="free:a", backend="ollama")]
        save_failover_settings(db, settings)
        win._context_limit_cache["free:a"] = 128_000
        attempts = win._fallback_attempts("big:paid", [{"role": "user", "content": "q"}])
        assert [a.model for a in attempts] == ["big:paid", "free:a"], attempts
        print(f"  전환 체인: {' → '.join(a.model for a in attempts)}")

        win.close()
        app.processEvents()
        win.deleteLater()
        app.processEvents()
        db.close()

    print("history_handoff smoke ok")


if __name__ == "__main__":
    main()
