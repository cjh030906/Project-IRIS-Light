# chat_block_parser

`iris/core/chat_block_parser.py`

스트리밍 채팅 본문 — prose / fenced_code / tool 블록 점진 파싱.

## 주요 정의

- `class RenderOpKind`
- `class RenderOp`
- `class ProseSegment`
- `class CodeSegment`
- `class ToolSegment`
- `def prose_char_count`
- `def parse_chat_segments`
- `def visible_prose_from_segments`
- `def streaming_body_segments`
- `class ChatBlockBuffer`
- `def _next_special_index`
- `def _find_closing_fence`
- `def _safe_partial_code`
- `def _prose_tail`
- `def _nth_code`
- `def _nth_complete_tool`
- `def _parse_tool_body`

## 내부 의존성

- [[chat_blocks]]
- [[chat_display]]
