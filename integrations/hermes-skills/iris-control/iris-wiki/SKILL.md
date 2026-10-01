---
name: iris-wiki
description: >
  Save notes into Iris Wiki (user vault) and open them in the Iris Wiki UI.
  Use when: 위키에 저장, Iris Wiki에 남겨, 사이트 정보 위키에, 메모 저장,
  save to wiki, write wiki note, remember this page in Iris Wiki.
---

# Iris Wiki

## Prefer Iris Control MCP

Use `iris_get_state` / `iris_get_catalog` / `iris_invoke` (server `iris-control`).
Do **not** invent Obsidian vault paths or claim a note was saved unless
`wiki.write_user_note` returns `ok`.

User notes live under `~/.iris-light/iris-wiki/` and appear in the UI as `user/...`.

## When

- User asks to save page/site/summary/memo **into Iris Wiki**.
- User pastes a URL and asks to capture the site info in Wiki.

## Steps

1. **PDF / URL / 파일 경로** → prefer `wiki.import_content` with `source` (one-shot extract + save + open Wiki UI).
   - `mode`: `raw` (full text) or `summarize` (LLM summary before save).
   - PDF: local `.pdf` path (user may attach file in chat — path appears in message).
   - URL: `https://...` page text fetch (stdlib; JS-heavy sites may be incomplete).
   - Text: `.md`, `.txt`, etc.
2. Or: `content.extract` first to preview, then `wiki.write_user_note` with `title`+`content`.
3. Manual markdown only: `wiki.write_user_note` with args:
   - `title` (required) — short note title
   - `content` (required) — markdown body (facts, links, bullets)
   - `source_url` (optional) — original URL
   - `rel_path` (optional) — 비우면 Iris가 임베딩 유사도와 모델 JSON으로 분류한다.
     `사용자/`(특징·취미·강점·약점·사고력·가치관), `학습자료/{분야}/`, `인사이트/{주제}/`,
     `projects/{열린 프로젝트}/`, `research/{주제}/`.
     애매하면 `inbox/` 에 남고 `ask_folder` 가 true다. inbox를 기본값으로 넣지 말 것.
   - `open` (optional, default true) — open Wiki UI on the new note
4. Confirm with the returned `rel_path` (e.g. `user/학습자료/수학/note.md`).
5. Search saved notes: `wiki.search` with `query`. This is not conversation History.
6. If the user only wants to open an existing note: `wiki.open_note` with `rel_path`.
7. List notes: `wiki.list_notes`. Reload UI: `wiki.reload`.

## Rules

- Never say “저장했습니다” without a successful `wiki.write_user_note` or `wiki.import_content` result.
- Local Iris may handle save without MCP when user attaches a file or pastes a URL with save intent.
- Prefer `mode=summarize` when user asks to 요약/정리; default `raw` for full capture.
- Do not write under `docs/` — user wiki only.
- Prefer the classified folder. Do not set `rel_path` to `inbox/` unless the user named that folder.
- `wiki.search` reads saved notes. Do not treat those excerpts as prior chat transcripts.
- After write, Iris opens the Wiki workspace and shows the note when `open=true`.
