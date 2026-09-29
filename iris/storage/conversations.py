"""로컬 채팅 세션 — SQLite conversations + messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from iris.storage.database import Database

ACTIVE_CHAT_PREF_KEY = "active_chat_conversation_id"
DEFAULT_TITLE = "새 채팅"
_TITLE_LIMIT = 36
_USER_TITLE_LIMIT = 48

# ponytail: 어휘 겹침으로 주제 전환을 본다. 오탐이 늘면 LLM 제목 생성으로 교체.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*|[가-힣]{2,}")
_STOPWORDS = frozenset(
    {
        "and",
        "for",
        "the",
        "this",
        "that",
        "with",
        "from",
        "please",
        "can",
        "you",
        "how",
        "what",
        "just",
        "okay",
        "yes",
        "그리고",
        "그래서",
        "그럼",
        "아니면",
        "또는",
        "이것",
        "그것",
        "저것",
        "알려줘",
        "해줘",
        "해주세요",
        "짜줘",
        "관련",
        "대해",
        "대한",
        "뭔가",
        "어떻게",
        "무엇",
        "왜요",
    }
)
_FOLLOWUP_RE = re.compile(
    r"^(그럼|그리고|그래서|아니면|또는|또|다시|응|네|아니|"
    r"ok|okay|yes|no|thanks?|고마워|감사|더|자세히|왜요?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatConversation:
    id: int
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    title_locked: bool = False


@dataclass(frozen=True)
class ChatMessage:
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: str


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def title_from_text(text: str, *, limit: int = _TITLE_LIMIT) -> str:
    body = " ".join((text or "").strip().split())
    if not body:
        return DEFAULT_TITLE
    if len(body) > limit:
        return body[: max(1, limit - 1)] + "…"
    return body


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        p.lower()
        for p in _TOKEN_RE.findall(text or "")
        if p.lower() not in _STOPWORDS and len(p) >= 2
    )


def _is_topic_line(text: str) -> bool:
    body = " ".join((text or "").split())
    if len(body) < 6:
        return False
    tokens = _tokens(body)
    if _FOLLOWUP_RE.match(body) and len(tokens) < 4:
        return False
    return len(tokens) >= 2


def topic_shifted(anchor: str, later: list[str]) -> bool:
    """later 가 anchor 와 다른 주제로 넘어갔는지."""
    if not later:
        return False
    a = _tokens(anchor)
    b = _tokens(" ".join(later))
    if len(b) < 3:
        return False
    shared = a & b
    novel = b - a
    if len(novel) < 3:
        return False
    lead = " ".join(later[0].split())
    if _FOLLOWUP_RE.match(lead) and len(novel) < 5:
        return False
    return len(novel) >= max(3, 2 * len(shared))


def _anchor_line(texts: list[str]) -> str:
    for text in texts:
        if _is_topic_line(text):
            return text
    return texts[0]


# ponytail: 어휘 규칙으로 10~25자 요약을 만든다. 제목이 자주 빗나가면 완료된 턴에서만 LLM으로 교체.
_SUMMARY_LIMIT = 25
_VERB_STEMS = ("수정", "구현", "개선", "추가", "삭제", "연결", "확대", "생성", "검색", "초기화", "저장", "확인", "열기")
_SUMMARY_STOP = _STOPWORDS | {
    "문제",
    "원인",
    "프로그램",
    "링크",
    "입력",
    "선택",
    "이거",
    "저거",
    "그냥",
    "부분",
    "알려",
    "보여",
    "하고",
    "있는",
    "있는데",
    "하면",
    "해서",
}
_TAIL = re.compile(
    r"(에서|으로|부터|까지|처럼|보다|하면|해서|하는|되는|한테|에게|이라고|라고|은|는|이|가|을|를|에|의|도|만|과|와|요|죠|한)$"
)


def _stem_token(token: str) -> str:
    word = token
    if re.fullmatch(r"[가-힣]+", word):
        trimmed = _TAIL.sub("", word)
        if len(trimmed) >= 2:
            word = trimmed
    return word


def summarize_work_title(text: str) -> str:
    """사용자 문장을 대상+작업 형태의 짧은 제목으로 줄인다. 요약이 안 되면 빈 문자열."""
    raw = " ".join((text or "").split())
    if not raw:
        return ""
    auto_link = bool(re.search(r"없으면|자동", raw))
    show_feature = bool(re.search(r"보여\s*주|보고\s*싶", raw))
    folded = raw
    folded = re.sub(r"검색창", "검색", folded)
    folded = re.sub(
        r"프로그램(?:이|을|가)?\s*꺼\w*|꺼지\w*|꺼짐|crash\w*|강제\s*종료",
        " 종료 오류 ",
        folded,
        flags=re.IGNORECASE,
    )
    folded = re.sub(r"에러|버그|errors?", " 오류 ", folded, flags=re.IGNORECASE)
    folded = re.sub(r"고쳐\s*줘(?:요)?", " 수정 ", folded)
    folded = re.sub(r"(붙여|붙이)\s*줘(?:요)?", " 추가 ", folded)
    verb = "|".join(_VERB_STEMS)
    folded = re.sub(rf"({verb})\s*해\s*(?:줘(?:요)?|주세요|봐)?", r" \1 ", folded)
    folded = re.sub(
        r"(?:해\s*줘(?:요)?|해주세요|해\s*주세요|하고\s*싶(?:어|어요|습니다)?|"
        r"싶(?:어|어요|습니다)?|보여\s*주고|보여주고|알려\s*줘(?:요)?|"
        r"문제가\s*있\w*|가능한지|없으면|확인하고|입력하\w*|선택한|창에서|링크를)",
        " ",
        folded,
    )
    tokens: list[str] = []
    for piece in _TOKEN_RE.findall(folded):
        stem = _stem_token(piece)
        key = stem.lower()
        if key in _SUMMARY_STOP or len(stem) < 2:
            continue
        if tokens and tokens[-1].lower() == key:
            continue
        tokens.append(stem)
    if auto_link and "연결" in tokens and "자동" not in tokens:
        tokens.insert(tokens.index("연결"), "자동")
    if show_feature and "기능" not in tokens and not any(t in tokens for t in ("수정", "구현", "삭제")):
        tokens.append("기능")
    if "검색" in tokens and "노드" in tokens:
        merged: list[str] = []
        for token in tokens:
            if token == "노드" and merged and merged[-1] == "검색":
                merged.append("및")
            merged.append(token)
        tokens = merged
    if len([t for t in tokens if t != "및"]) < 2:
        return ""
    while len(tokens) > 2 and len(" ".join(tokens)) > _SUMMARY_LIMIT:
        drop_at = -2 if tokens[-1] in _VERB_STEMS or tokens[-1] == "기능" else -1
        if tokens[drop_at] == "및" and len(tokens) > 3:
            drop_at = -3
        tokens.pop(drop_at)
    title = " ".join(tokens).strip()
    if len(title) > _SUMMARY_LIMIT:
        title = title[: _SUMMARY_LIMIT - 1].rstrip() + "…"
    if title == raw:
        return ""
    return title


def suggest_title(messages: list[ChatMessage] | list[dict[str, str]]) -> str:
    """현재 대화 맥락의 제목 — 첫 주제를 요약하고, 크게 바뀌면 새 주제를 요약."""
    users: list[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            role, content = str(msg.get("role") or ""), str(msg.get("content") or "")
        else:
            role, content = msg.role, msg.content
        body = content.strip()
        if role == "user" and body:
            users.append(body)
    if not users:
        return DEFAULT_TITLE
    start = 0
    for i in range(1, len(users)):
        if topic_shifted(users[start], [users[i]]):
            start = i
    anchor = _anchor_line(users[start:])
    if not _is_topic_line(anchor):
        return DEFAULT_TITLE
    return summarize_work_title(anchor) or DEFAULT_TITLE


def ensure_chat_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '새 채팅',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title_locked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conv "
        "ON chat_messages(conversation_id, id)"
    )
    cols = {
        str(row["name"])
        for row in db._execute("PRAGMA table_info(chat_conversations)").fetchall()
    }
    if "title_locked" not in cols:
        db._execute(
            "ALTER TABLE chat_conversations "
            "ADD COLUMN title_locked INTEGER NOT NULL DEFAULT 0"
        )
    db._commit()


def _conv_from_row(row) -> ChatConversation:
    try:
        locked = bool(int(row["title_locked"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        locked = False
    return ChatConversation(
        id=int(row["id"]),
        title=str(row["title"] or DEFAULT_TITLE),
        created_at=str(row["created_at"] or ""),
        updated_at=str(row["updated_at"] or ""),
        message_count=int(row["message_count"] or 0),
        title_locked=locked,
    )


def create_conversation(db: Database, *, title: str = DEFAULT_TITLE) -> ChatConversation:
    ensure_chat_schema(db)
    stamp = _now()
    name = (title or "").strip() or DEFAULT_TITLE
    cur = db._execute(
        """
        INSERT INTO chat_conversations(title, created_at, updated_at, title_locked)
        VALUES(?, ?, ?, 0)
        """,
        (name, stamp, stamp),
    )
    db._commit()
    cid = int(cur.lastrowid or 0)
    return ChatConversation(
        id=cid,
        title=name,
        created_at=stamp,
        updated_at=stamp,
        message_count=0,
        title_locked=False,
    )


def get_conversation(db: Database, conversation_id: int) -> ChatConversation | None:
    ensure_chat_schema(db)
    row = db._execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at, c.title_locked,
               (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id)
                 AS message_count
          FROM chat_conversations c
         WHERE c.id = ?
        """,
        (int(conversation_id),),
    ).fetchone()
    if row is None:
        return None
    return _conv_from_row(row)


def set_active_conversation_id(db: Database, conversation_id: int) -> None:
    db.set_preference(ACTIVE_CHAT_PREF_KEY, str(int(conversation_id)))


def active_conversation_id(db: Database) -> int | None:
    raw = (db.get_preference(ACTIVE_CHAT_PREF_KEY, "") or "").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def ensure_active_conversation(db: Database) -> int:
    """저장된 활성 세션이 있으면 쓰고, 없으면 최근 세션 또는 새 세션."""
    ensure_chat_schema(db)
    current = active_conversation_id(db)
    if current is not None and get_conversation(db, current) is not None:
        return current
    row = db._execute(
        "SELECT id FROM chat_conversations ORDER BY updated_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is not None:
        cid = int(row["id"])
        set_active_conversation_id(db, cid)
        return cid
    conv = create_conversation(db)
    set_active_conversation_id(db, conv.id)
    return conv.id


def list_conversations(
    db: Database,
    *,
    limit: int = 50,
    include_empty_id: int | None = None,
) -> list[ChatConversation]:
    ensure_chat_schema(db)
    rows = db._execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at, c.title_locked,
               (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id)
                 AS message_count
          FROM chat_conversations c
         ORDER BY c.updated_at DESC, c.id DESC
        """
    ).fetchall()
    out: list[ChatConversation] = []
    for row in rows:
        item = _conv_from_row(row)
        if item.message_count <= 0 and item.id != include_empty_id:
            continue
        out.append(item)
        if len(out) >= max(1, int(limit)):
            break
    return out


def list_messages(db: Database, conversation_id: int) -> list[ChatMessage]:
    ensure_chat_schema(db)
    rows = db._execute(
        """
        SELECT id, conversation_id, role, content, created_at
          FROM chat_messages
         WHERE conversation_id = ?
         ORDER BY id ASC
        """,
        (int(conversation_id),),
    ).fetchall()
    return [
        ChatMessage(
            id=int(row["id"]),
            conversation_id=int(row["conversation_id"]),
            role=str(row["role"] or ""),
            content=str(row["content"] or ""),
            created_at=str(row["created_at"] or ""),
        )
        for row in rows
    ]


def history_dicts(db: Database, conversation_id: int) -> list[dict[str, str]]:
    return [
        {"role": m.role, "content": m.content}
        for m in list_messages(db, conversation_id)
        if m.role in ("user", "assistant")
    ]


def _set_title(
    db: Database,
    conversation_id: int,
    title: str,
    *,
    locked: bool,
) -> None:
    db._execute(
        "UPDATE chat_conversations SET title = ?, title_locked = ? WHERE id = ?",
        (title, 1 if locked else 0, int(conversation_id)),
    )


def _maybe_refresh_title(db: Database, conversation_id: int) -> None:
    """임시 제목은 첫 응답 뒤에 한 번 요약. 사용자가 잠그면 유지. 주제가 바뀌면 다시 요약."""
    conv = get_conversation(db, conversation_id)
    if conv is None or conv.title_locked:
        return
    messages = list_messages(db, conversation_id)
    if not any(m.role == "assistant" and m.content.strip() for m in messages):
        return
    suggested = suggest_title(messages)
    if suggested in ("", DEFAULT_TITLE) or suggested == conv.title:
        return
    if conv.title in ("", DEFAULT_TITLE):
        _set_title(db, conversation_id, suggested, locked=False)
        return
    users = [
        m.content.strip()
        for m in messages
        if m.role == "user" and m.content.strip()
    ]
    anchor = _anchor_line(users) if users else ""
    if anchor and topic_shifted(anchor, [users[-1]]):
        _set_title(db, conversation_id, suggested, locked=False)


def rename_conversation(db: Database, conversation_id: int, title: str) -> str:
    """사용자가 직접 붙인 제목 — 이후 자동 갱신하지 않는다."""
    ensure_chat_schema(db)
    conv = get_conversation(db, conversation_id)
    name = " ".join((title or "").strip().split())
    if not name:
        return conv.title if conv else DEFAULT_TITLE
    if len(name) > _USER_TITLE_LIMIT:
        name = name[:_USER_TITLE_LIMIT]
    _set_title(db, conversation_id, name, locked=True)
    db._commit()
    return name


def append_message(db: Database, conversation_id: int, role: str, content: str) -> int:
    ensure_chat_schema(db)
    stamp = _now()
    cur = db._execute(
        """
        INSERT INTO chat_messages(conversation_id, role, content, created_at)
        VALUES(?, ?, ?, ?)
        """,
        (int(conversation_id), str(role or ""), str(content or ""), stamp),
    )
    db._execute(
        "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
        (stamp, int(conversation_id)),
    )
    if str(role) in ("user", "assistant") and (content or "").strip():
        _maybe_refresh_title(db, conversation_id)
    db._commit()
    return int(cur.lastrowid or 0)


def pop_last_user_message(db: Database, conversation_id: int) -> bool:
    ensure_chat_schema(db)
    row = db._execute(
        """
        SELECT id, role FROM chat_messages
         WHERE conversation_id = ?
         ORDER BY id DESC LIMIT 1
        """,
        (int(conversation_id),),
    ).fetchone()
    if row is None or str(row["role"]) != "user":
        return False
    db._execute("DELETE FROM chat_messages WHERE id = ?", (int(row["id"]),))
    db._execute(
        "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
        (_now(), int(conversation_id)),
    )
    db._commit()
    return True


def clear_conversation_messages(db: Database, conversation_id: int) -> None:
    ensure_chat_schema(db)
    db._execute(
        "DELETE FROM chat_messages WHERE conversation_id = ?",
        (int(conversation_id),),
    )
    db._execute(
        "UPDATE chat_conversations SET title = ?, title_locked = 0, updated_at = ? WHERE id = ?",
        (DEFAULT_TITLE, _now(), int(conversation_id)),
    )
    db._commit()


def delete_conversation(db: Database, conversation_id: int) -> None:
    ensure_chat_schema(db)
    db._execute(
        "DELETE FROM chat_messages WHERE conversation_id = ?",
        (int(conversation_id),),
    )
    db._execute(
        "DELETE FROM chat_conversations WHERE id = ?",
        (int(conversation_id),),
    )
    db._commit()


def start_new_conversation(db: Database) -> int:
    """현재 빈 세션이 있으면 재사용, 아니면 새로 만든다."""
    ensure_chat_schema(db)
    current = active_conversation_id(db)
    if current is not None:
        conv = get_conversation(db, current)
        if conv is not None and conv.message_count <= 0:
            return current
    conv = create_conversation(db)
    set_active_conversation_id(db, conv.id)
    return conv.id
