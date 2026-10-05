# conversations

`iris/storage/conversations.py`

로컬 채팅 세션 — SQLite conversations + messages.

## 주요 정의

- `class ChatConversation`
- `class ChatMessage`
- `def _now`
- `def title_from_text`
- `def load_title_basis`
- `def save_title_basis`
- `def summarize_reply`
- `def _message_parts`
- `def suggest_title`
- `def ensure_chat_schema`
- `def _conv_from_row`
- `def create_conversation`
- `def get_conversation`
- `def set_active_conversation_id`
- `def active_conversation_id`
- `def ensure_active_conversation`
- `def list_conversations`
- `def list_messages`
- `def history_dicts`
- `def _set_title`
- `def _maybe_refresh_title`
- `def refresh_conversation_title`
- `def rename_conversation`
- `def append_message`
- `def pop_last_user_message`
- `def clear_conversation_messages`
- `def delete_conversation`
- `def start_new_conversation`

## 내부 의존성

- [[database]]
