# file_write_claim

`iris/ui/chat/file_write_claim.py`

파일 쓰기 완료 문장 게이트와 사진→열린 파일 절차.

## 주요 정의

- `class GateResult`
- `def contains_completion_claim`
- `def verified_write_path`
- `def reveal_line`
- `def settle_completion_claim`
- `def image_write_request`
- `def _image_path`
- `def _editor_paths`
- `def _missing_message`
- `def prepare_image_code_pipe`
- `def extracted_code`
- `def commit_extracted_code`
- `def apply_image_code_pipe`
- `def extract_image_code`
- `def start_image_extract`

## 내부 의존성

- [[at_path_refs]]
- [[image_extract_worker]]
- [[ollama_client]]
- [[openai_compat_client]]
- [[project_ops]]
