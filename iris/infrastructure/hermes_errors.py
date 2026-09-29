"""Hermes 채팅 오류 분류 — 게이트웨이 Bearer vs Ollama 클라우드 401."""

from __future__ import annotations

# UI·테스트가 안정적으로 잡는 접두 (문구 변경 시 테스트도 같이)
CLOUD_AUTH_ERROR_PREFIX = "Ollama 클라우드 미로그인"
GATEWAY_AUTH_ERROR_PREFIX = "Hermes 게이트웨이 API 키"

CLOUD_AUTH_USER_MSG = (
    f"{CLOUD_AUTH_ERROR_PREFIX}입니다. "
    "Ollama 앱에서 로그인하거나 로컬 모델로 바꾸세요."
)
GATEWAY_AUTH_USER_MSG = (
    f"{GATEWAY_AUTH_ERROR_PREFIX} 불일치(HTTP 401). "
    "시작 프로토콜 「다시 설정」으로 API_SERVER_KEY를 맞추세요."
)


def is_cloud_runtime_name(name: str) -> bool:
    from iris.infrastructure.ollama_client import OllamaModelInfo
    from iris.storage.api_providers import is_api_runtime_model

    n = (name or "").strip()
    if not n or is_api_runtime_model(n):
        return False
    return bool(OllamaModelInfo(name=n).is_cloud)


def looks_like_upstream_unauthorized(err_msg: str) -> bool:
    """SSE/업스트림이 올린 401 Unauthorized (게이트웨이 Bearer 문구와 구분)."""
    s = (err_msg or "").strip().lower()
    if not s:
        return False
    if "gateway" in s and "api" in s:
        return False
    if s in ("unauthorized", "http 401: unauthorized", "401 unauthorized"):
        return True
    return "401" in s and "unauthorized" in s


def looks_like_no_tools_error(err_msg: str) -> bool:
    s = (err_msg or "").strip().lower()
    return "does not support tools" in s or "not support tools" in s


def format_hermes_sse_error(err_msg: str, *, model: str = "") -> str:
    """SSE error.message → 사용자용 RuntimeError 본문 (앞에 'Hermes: ' 붙이지 않음)."""
    raw = (err_msg or "").strip()
    if looks_like_upstream_unauthorized(raw):
        if is_cloud_runtime_name(model) or ":cloud" in raw.lower() or "-cloud" in raw.lower():
            return CLOUD_AUTH_USER_MSG
        # 모델명을 모를 때도 클라우드 401과 동일 패턴이면 클라우드 안내 우선
        # (게이트웨이 Bearer 실패는 HTTPError 경로 — 여기로 안 옴)
        try:
            from iris.infrastructure.ollama_usage import ollama_cloud_signed_in

            if not ollama_cloud_signed_in():
                return CLOUD_AUTH_USER_MSG
        except Exception:
            pass
        return CLOUD_AUTH_USER_MSG
    if looks_like_no_tools_error(raw):
        return (
            "이 모델은 도구(tools)를 지원하지 않습니다. "
            "도구 지원 모델을 선택하세요. "
            f"({raw[:120]})"
        )
    return raw


def format_hermes_http_401() -> str:
    """urllib HTTPError 401 — 게이트웨이 Bearer 실패 전용."""
    return GATEWAY_AUTH_USER_MSG


def is_cloud_auth_user_message(err: str) -> bool:
    return CLOUD_AUTH_ERROR_PREFIX in (err or "")


def cloud_model_blocked_without_login(model: str) -> bool:
    """클라우드 모델인데 Ollama 미로그인이면 True."""
    if not is_cloud_runtime_name(model):
        return False
    try:
        from iris.infrastructure.ollama_usage import ollama_cloud_signed_in

        return not ollama_cloud_signed_in()
    except Exception:
        return True


def resolve_initial_model(preferred: str, available: list[str]) -> str:
    """부팅·목록 로드 시 쓸 모델.

    클라우드인데 미로그인이면 로컬 설치 채팅 모델로 바꾼다.
    API runtime·로그인된 클라우드·로컬은 preferred 유지(목록에 있을 때).
    """
    from iris.storage.api_providers import is_api_runtime_model
    from iris.system.setup_protocol import prefer_chat_model

    names = [str(n).strip() for n in available if str(n).strip()]
    pref = (preferred or "").strip()
    if pref in ("(unset)",):
        pref = ""

    if pref and is_api_runtime_model(pref):
        return pref

    if pref and not cloud_model_blocked_without_login(pref):
        if not names or pref in names:
            return pref

    # 미로그인 클라우드 / 목록에 없는 preferred → 로컬
    local_hint = pref if pref and not is_cloud_runtime_name(pref) else ""
    local = prefer_chat_model(names, preferred=local_hint)
    if local:
        return local
    return pref


if __name__ == "__main__":
    assert looks_like_upstream_unauthorized("HTTP 401: Unauthorized")
    assert not looks_like_upstream_unauthorized("Invalid gateway API key")
    assert is_cloud_runtime_name("gemma4:31b-cloud")
    assert not is_cloud_runtime_name("exaone3.5:2.4b")
    assert CLOUD_AUTH_ERROR_PREFIX in format_hermes_sse_error(
        "HTTP 401: Unauthorized", model="gemma4:31b-cloud"
    )
    assert GATEWAY_AUTH_ERROR_PREFIX in format_hermes_http_401()
    assert "도구" in format_hermes_sse_error(
        "registry.ollama.ai/library/exaone3.5:2.4b does not support tools"
    )
    from unittest.mock import patch

    with patch(
        "iris.infrastructure.ollama_usage.ollama_cloud_signed_in", return_value=False
    ):
        assert (
            resolve_initial_model(
                "gemma4:31b-cloud", ["gemma4:31b-cloud", "exaone3.5:2.4b"]
            )
            == "exaone3.5:2.4b"
        )
        assert resolve_initial_model("", ["exaone3.5:2.4b"]) == "exaone3.5:2.4b"
    with patch(
        "iris.infrastructure.ollama_usage.ollama_cloud_signed_in", return_value=True
    ):
        assert (
            resolve_initial_model(
                "gemma4:31b-cloud", ["gemma4:31b-cloud", "exaone3.5:2.4b"]
            )
            == "gemma4:31b-cloud"
        )
    print("hermes_errors self-check ok")
