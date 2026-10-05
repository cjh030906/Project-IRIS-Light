# chat_renderer

`iris/ui/chat/chat_renderer.py`

채팅 단일 렌더 API — prose / code / tool / error / citation.

## 주요 정의

- `def render_markdown_document`
- `def render_iris_message`
- `def render_wiki_document`
- `def render_user_message`
- `def render_error_inline`
- `def render_tool_shell`
- `def render_error_message`
- `def render_file_chip`
- `def render_diff_block`
- `def _ide_connected_for_file_chips`
- `def _looks_like_file_path`
- `def _looks_like_git_diff`
- `def _inject_file_chips_in_prose`
- `def _inject_file_chips_in_source`
- `def _upgrade_inline_code_file_chips`
- `def _markdown_body_to_html`
- `def _upgrade_fenced_pre_to_cards`
- `def _plain_to_chat_html`
- `def _sanitize_chat_html`
- `def _style_img_tag`
- `def _merge_cell_style`
- `def _style_table_cell`
- `def _style_tables`
- `def _style_chat_html`

## 내부 의존성

- [[chat_blocks]]
- [[chat_citations]]
- [[markdown_text]]
- [[theme_tokens]]
