# chat_blocks

`iris/ui/chat/chat_blocks.py`

채팅 출력 블록 — Cursor식 prose / code / tool / citation HTML.

## 주요 정의

- `class ChatBlockKind`
- `class ProseBlock`
- `class FencedCodeBlock`
- `class ToolShellBlock`
- `def tool_block_markers`
- `def collapse_anchor_for`
- `def copy_anchor_for`
- `def parse_copy_anchor`
- `def parse_collapse_block_id`
- `def file_anchor_for`
- `def parse_iris_file_anchor`
- `def parse_file_chip_location`
- `def file_chip_to_html`
- `def diff_block_to_html`
- `def _shell_style`
- `def wrap_document_html`
- `def inline_code_to_html`
- `def _display_lang_name`
- `def fenced_code_to_html`
- `def tool_shell_to_html`
- `def marked_tool_shell_to_html`
- `def replace_marked_tool_block`
- `def handle_tool_collapse_click`
- `def tool_file_to_html`
- `def error_block_to_html`
- `def _host_label`
- `def citation_chip_to_html`

## 내부 의존성

- [[chat_syntax]]
- [[theme_tokens]]
