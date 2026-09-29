"""컨텍스트 아카이브 — 모델을 갈아탈 때 남기는 대화 원문 스냅샷.

claude-code-router(MIT)의 `gateway/context-archive/store.ts` 설계를 IRIS SQLite로
옮긴 것이다. 핵심은 **세대 체인**이다.

    generation 1 (qwen3:8b)  ←parent─  generation 2 (gemma4:free)  ←parent─ …

모델을 바꿀 때마다 그 시점의 messages 전체를 스냅샷으로 남기고, 새 세대가 이전
세대를 가리킨다. 새 모델에게는 요약(인수인계문)만 주되, 요약으로 모자라면
`lineage()` 를 타고 올라가 원문을 다시 꺼낼 수 있다.

보존 정책(개수·용량·기간)으로 오래된 스냅샷을 지우되, **현재 체인은 보호**한다.
지금 쓰고 있는 대화의 조상을 용량 때문에 날려버리면 복원이 끊기기 때문이다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from iris.storage.database import Database

STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUSES: tuple[str, ...] = (STATUS_PENDING, STATUS_READY, STATUS_FAILED)

_LINEAGE_LIMIT = 32


@dataclass(frozen=True)
class ArchiveRetention:
    """보존 한도. 셋 중 하나라도 넘으면 오래된 것부터 지운다."""

    max_snapshots: int = 200
    max_bytes: int = 64 * 1024 * 1024
    retention_days: int = 30

    def expires_at(self, created_at: str) -> str:
        base = _parse(created_at) or datetime.now()
        return (base + timedelta(days=max(1, int(self.retention_days)))).isoformat(
            timespec="seconds"
        )


DEFAULT_RETENTION = ArchiveRetention()


@dataclass(frozen=True)
class ArchiveSnapshot:
    archive_id: str
    conversation_id: int
    generation: int
    parent_archive_id: str
    model: str
    backend: str
    body: str  # messages JSON
    body_sha256: str
    status: str
    created_at: str
    expires_at: str

    @property
    def messages(self) -> list[dict[str, str]]:
        try:
            data = json.loads(self.body)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(data, list):
            return []
        out: list[dict[str, str]] = []
        for item in data:
            if isinstance(item, dict) and item.get("role"):
                out.append(
                    {"role": str(item.get("role")), "content": str(item.get("content") or "")}
                )
        return out

    @property
    def byte_size(self) -> int:
        return len(self.body.encode("utf-8"))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None


def new_archive_id() -> str:
    return uuid.uuid4().hex[:16]


def new_session_token() -> str:
    """아카이브 조회용 토큰. 모델 프롬프트에 실려 나가므로 추측 불가해야 한다."""
    return uuid.uuid4().hex


def sha256_of(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def ensure_archive_schema(db: Database) -> None:
    db._execute(
        """
        CREATE TABLE IF NOT EXISTS context_archives (
            archive_id TEXT PRIMARY KEY,
            conversation_id INTEGER NOT NULL,
            generation INTEGER NOT NULL,
            parent_archive_id TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            backend TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            body_sha256 TEXT NOT NULL,
            token_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL DEFAULT '',
            UNIQUE(conversation_id, generation)
        )
        """
    )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_context_archives_conv "
        "ON context_archives(conversation_id, generation DESC)"
    )
    db._execute(
        "CREATE INDEX IF NOT EXISTS idx_context_archives_expires "
        "ON context_archives(expires_at)"
    )
    db._commit()


def _row_to_snapshot(row) -> ArchiveSnapshot:
    return ArchiveSnapshot(
        archive_id=str(row["archive_id"]),
        conversation_id=int(row["conversation_id"] or 0),
        generation=int(row["generation"] or 0),
        parent_archive_id=str(row["parent_archive_id"] or ""),
        model=str(row["model"] or ""),
        backend=str(row["backend"] or ""),
        body=str(row["body"] or "[]"),
        body_sha256=str(row["body_sha256"] or ""),
        status=str(row["status"] or STATUS_PENDING),
        created_at=str(row["created_at"] or ""),
        expires_at=str(row["expires_at"] or ""),
    )


def latest_snapshot(db: Database, conversation_id: int) -> ArchiveSnapshot | None:
    ensure_archive_schema(db)
    row = db._execute(
        """
        SELECT * FROM context_archives
        WHERE conversation_id = ?
        ORDER BY generation DESC LIMIT 1
        """,
        (int(conversation_id),),
    ).fetchone()
    return _row_to_snapshot(row) if row else None


def create_snapshot(
    db: Database,
    conversation_id: int,
    messages: list[dict[str, str]],
    *,
    model: str = "",
    backend: str = "",
    session_token: str = "",
    retention: ArchiveRetention = DEFAULT_RETENTION,
) -> ArchiveSnapshot:
    """현 대화 원문을 새 세대로 박제한다. 직전 세대가 부모가 된다."""
    ensure_archive_schema(db)
    previous = latest_snapshot(db, conversation_id)
    generation = (previous.generation if previous else 0) + 1
    parent = previous.archive_id if previous else ""
    body = json.dumps(list(messages or []), ensure_ascii=False)
    stamp = _now()
    snapshot = ArchiveSnapshot(
        archive_id=new_archive_id(),
        conversation_id=int(conversation_id),
        generation=generation,
        parent_archive_id=parent,
        model=str(model or ""),
        backend=str(backend or ""),
        body=body,
        body_sha256=sha256_of(body),
        status=STATUS_PENDING,
        created_at=stamp,
        expires_at=retention.expires_at(stamp),
    )
    db._execute(
        """
        INSERT INTO context_archives(
            archive_id, conversation_id, generation, parent_archive_id,
            model, backend, body, body_sha256, token_hash, status, created_at, expires_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.archive_id,
            snapshot.conversation_id,
            snapshot.generation,
            snapshot.parent_archive_id,
            snapshot.model,
            snapshot.backend,
            snapshot.body,
            snapshot.body_sha256,
            sha256_of(session_token) if session_token else "",
            snapshot.status,
            snapshot.created_at,
            snapshot.expires_at,
        ),
    )
    db._commit()
    _extend_lineage_expiry(db, snapshot.archive_id, snapshot.expires_at, retention)
    prune(db, retention, protect_archive_id=snapshot.archive_id)
    return snapshot


def finalize_snapshot(db: Database, archive_id: str, *, model: str = "", backend: str = "") -> None:
    """전환이 성공했다 — 어느 모델로 갔는지 확정하고 ready 로 바꾼다."""
    ensure_archive_schema(db)
    db._execute(
        """
        UPDATE context_archives
        SET status = ?, model = COALESCE(NULLIF(?, ''), model),
            backend = COALESCE(NULLIF(?, ''), backend)
        WHERE archive_id = ? AND status = ?
        """,
        (STATUS_READY, str(model or ""), str(backend or ""), str(archive_id), STATUS_PENDING),
    )
    db._commit()


def fail_snapshot(db: Database, archive_id: str) -> None:
    ensure_archive_schema(db)
    db._execute(
        "UPDATE context_archives SET status = ? WHERE archive_id = ?",
        (STATUS_FAILED, str(archive_id)),
    )
    db._commit()


def get_snapshot(db: Database, archive_id: str) -> ArchiveSnapshot | None:
    ensure_archive_schema(db)
    row = db._execute(
        "SELECT * FROM context_archives WHERE archive_id = ? LIMIT 1", (str(archive_id),)
    ).fetchone()
    return _row_to_snapshot(row) if row else None


def verify_token(db: Database, archive_id: str, session_token: str) -> bool:
    """토큰이 걸린 아카이브인지 확인. 토큰을 안 건 아카이브는 항상 통과."""
    ensure_archive_schema(db)
    row = db._execute(
        "SELECT token_hash FROM context_archives WHERE archive_id = ?", (str(archive_id),)
    ).fetchone()
    if row is None:
        return False
    stored = str(row["token_hash"] or "")
    if not stored:
        return True
    return stored == sha256_of(session_token)


def lineage(db: Database, archive_id: str, *, limit: int = _LINEAGE_LIMIT) -> list[ArchiveSnapshot]:
    """이 아카이브부터 부모를 따라 거슬러 올라간 목록 (최신 → 과거)."""
    ensure_archive_schema(db)
    out: list[ArchiveSnapshot] = []
    seen: set[str] = set()
    current = str(archive_id or "")
    while current and len(out) < max(1, int(limit)) and current not in seen:
        seen.add(current)
        snap = get_snapshot(db, current)
        if snap is None:
            break
        out.append(snap)
        current = snap.parent_archive_id
    return out


def lineage_messages(
    db: Database, archive_id: str, *, limit: int = _LINEAGE_LIMIT
) -> list[dict[str, str]]:
    """체인에서 가장 오래된 세대의 원문 — 가장 많은 맥락을 담고 있다."""
    chain = lineage(db, archive_id, limit=limit)
    if not chain:
        return []
    return chain[-1].messages


def _protected_ids(db: Database, archive_id: str, retention: ArchiveRetention) -> set[str]:
    return {
        s.archive_id
        for s in lineage(db, archive_id, limit=max(1, int(retention.max_snapshots)))
    }


def _extend_lineage_expiry(
    db: Database, archive_id: str, expires_at: str, retention: ArchiveRetention
) -> None:
    """새 세대가 생기면 조상들의 만료도 같이 늘린다 — 체인이 중간에 끊기면 안 된다."""
    for snap in lineage(db, archive_id, limit=max(1, int(retention.max_snapshots))):
        db._execute(
            """
            UPDATE context_archives SET expires_at = ?
            WHERE archive_id = ? AND (expires_at = '' OR expires_at < ?)
            """,
            (expires_at, snap.archive_id, expires_at),
        )
    db._commit()


def prune(
    db: Database,
    retention: ArchiveRetention = DEFAULT_RETENTION,
    *,
    protect_archive_id: str = "",
) -> int:
    """만료·개수·용량 초과분 정리. 보호 체인은 건드리지 않는다. 반환: 지운 개수."""
    ensure_archive_schema(db)
    protected = _protected_ids(db, protect_archive_id, retention) if protect_archive_id else set()
    removed = 0
    now = _now()

    expired = db._execute(
        "SELECT archive_id FROM context_archives WHERE expires_at != '' AND expires_at <= ?",
        (now,),
    ).fetchall()
    for row in expired:
        aid = str(row["archive_id"])
        if aid not in protected:
            db._execute("DELETE FROM context_archives WHERE archive_id = ?", (aid,))
            removed += 1

    rows = db._execute(
        "SELECT archive_id, length(body) AS n FROM context_archives "
        "ORDER BY created_at DESC, rowid DESC"
    ).fetchall()
    max_snapshots = max(1, int(retention.max_snapshots))
    for index, row in enumerate(rows):
        aid = str(row["archive_id"])
        if index >= max_snapshots and aid not in protected:
            db._execute("DELETE FROM context_archives WHERE archive_id = ?", (aid,))
            removed += 1

    rows = db._execute(
        "SELECT archive_id, length(body) AS n FROM context_archives "
        "ORDER BY created_at DESC, rowid DESC"
    ).fetchall()
    max_bytes = max(1, int(retention.max_bytes))
    retained = 0
    for row in rows:
        retained += int(row["n"] or 0)
        aid = str(row["archive_id"])
        if retained > max_bytes and aid not in protected:
            db._execute("DELETE FROM context_archives WHERE archive_id = ?", (aid,))
            removed += 1

    db._commit()
    return removed


def clear_conversation(db: Database, conversation_id: int) -> None:
    ensure_archive_schema(db)
    db._execute(
        "DELETE FROM context_archives WHERE conversation_id = ?", (int(conversation_id),)
    )
    db._commit()


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    assert sha256_of("x") == sha256_of("x") and sha256_of("x") != sha256_of("y")
    assert len(new_archive_id()) == 16
    assert len(new_session_token()) == 32

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "t.db")
        token = new_session_token()

        msgs1 = [{"role": "user", "content": "설치가 안 돼"}, {"role": "assistant", "content": "권한 문제야"}]
        s1 = create_snapshot(db, 5, msgs1, model="qwen3:8b", backend="ollama", session_token=token)
        assert s1.generation == 1 and s1.parent_archive_id == ""
        assert s1.status == STATUS_PENDING
        assert s1.messages == msgs1
        assert s1.body_sha256 == sha256_of(s1.body)

        finalize_snapshot(db, s1.archive_id, model="gemma4:free")
        assert get_snapshot(db, s1.archive_id).status == STATUS_READY

        msgs2 = msgs1 + [{"role": "user", "content": "고쳤어"}]
        s2 = create_snapshot(db, 5, msgs2, model="gemma4:free", backend="ollama", session_token=token)
        assert s2.generation == 2 and s2.parent_archive_id == s1.archive_id

        chain = lineage(db, s2.archive_id)
        assert [c.generation for c in chain] == [2, 1]
        assert lineage_messages(db, s2.archive_id) == msgs1  # 최고참 세대의 원문

        assert verify_token(db, s2.archive_id, token) is True
        assert verify_token(db, s2.archive_id, "틀린토큰") is False
        assert verify_token(db, "없는아카이브", token) is False

        # 다른 대화는 세대가 따로 흐른다
        other = create_snapshot(db, 9, [{"role": "user", "content": "별개 대화"}])
        assert other.generation == 1 and other.parent_archive_id == ""

        # 개수 한도 — 현재 체인은 보호된다
        tight = ArchiveRetention(max_snapshots=2, max_bytes=10**9, retention_days=30)
        for i in range(5):
            create_snapshot(db, 77, [{"role": "user", "content": f"채우기 {i}"}], retention=tight)
        kept = db._execute("SELECT COUNT(*) AS n FROM context_archives").fetchone()["n"]
        assert kept >= 2, kept
        last77 = latest_snapshot(db, 77)
        assert last77 is not None and get_snapshot(db, last77.archive_id) is not None

        # 만료된 것은 지워지되 보호 체인은 남는다
        db._execute(
            "UPDATE context_archives SET expires_at = ? WHERE conversation_id = 9",
            ("2000-01-01T00:00:00",),
        )
        db._commit()
        prune(db, tight, protect_archive_id=last77.archive_id)
        assert get_snapshot(db, other.archive_id) is None
        assert get_snapshot(db, last77.archive_id) is not None

        clear_conversation(db, 77)
        assert latest_snapshot(db, 77) is None
        db.close()

    print("context_archive self-check ok")
