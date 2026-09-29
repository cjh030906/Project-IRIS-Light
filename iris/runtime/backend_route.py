"""모델 이름 → 어느 백엔드로 어떻게 부를지.

창(MainWindow)과 헤드리스 CLI 가 **같은 규칙**을 써야 한다. 앱이 켜져 있을 때와
꺼져 있을 때 루틴이 다른 모델로 돌면 사용자는 이유를 알 수 없다.

DB(등록된 API 설정)를 읽으므로 워커 스레드가 아니라 호출부에서 먼저 푼다.
"""

from __future__ import annotations

from typing import Any

from iris.ui.workers.backend_call import BackendRoute


def resolve_backend_route(
    settings: Any,
    db: Any,
    model: str,
) -> BackendRoute | None:
    """지금 설정 기준으로 이 모델을 부를 방법. 못 정하면 None.

    Hermes 가 켜져 있으면 Ollama 이름이든 `api:` id 든 전부 게이트웨이를 거친다.
    꺼져 있으면 `api:` id 는 등록된 프로바이더로, 나머지는 Ollama 데몬으로 간다.
    """
    name = str(model or "").strip()
    if not name:
        return None

    if bool(getattr(settings, "hermes_enabled", False)):
        try:
            from iris.infrastructure.hermes_client import resolve_hermes_inference

            target = resolve_hermes_inference(
                name,
                db=db,
                ollama_base_url=getattr(settings, "ollama_base_url", ""),
            )
        except Exception:  # noqa: BLE001
            return None
        return BackendRoute(
            backend="hermes",
            model=name,
            base_url=getattr(settings, "hermes_base_url", ""),
            api_key=getattr(settings, "hermes_api_key", ""),
            command=getattr(settings, "hermes_command", "hermes"),
            target=target,
        )

    from iris.storage.api_providers import get_api_provider, parse_runtime_model_id

    parsed = parse_runtime_model_id(name)
    if parsed is not None:
        provider_id, api_model = parsed
        provider = get_api_provider(db, provider_id) if db is not None else None
        if provider is None or not (getattr(provider, "base_url", "") or "").strip():
            return None
        return BackendRoute(
            backend="api",
            model=api_model,
            base_url=provider.base_url,
            api_key=provider.api_key,
            auth_style=provider.auth_style,
        )

    return BackendRoute(
        backend="ollama",
        model=name,
        base_url=getattr(settings, "ollama_base_url", ""),
    )


def route_for_routine(settings: Any, db: Any, routine: Any, fallback_model: str = ""):
    """루틴이 쓸 경로. 고정 모델이 있으면 그것, 못 쓰면 현재 모델로 물러선다.

    반환: (route 또는 None, 사용자에게 알릴 문구)
    """
    pinned = (getattr(routine, "model", "") or "").strip()
    wanted = pinned or fallback_model
    route = resolve_backend_route(settings, db, wanted)
    if route is not None:
        return route, ""
    if pinned and fallback_model and fallback_model != pinned:
        route = resolve_backend_route(settings, db, fallback_model)
        if route is not None:
            return route, (
                f"지정 모델 '{pinned}' 을 쓸 수 없어 '{fallback_model}' 으로 실행합니다."
            )
    return None, "쓸 모델을 정하지 못했습니다."


if __name__ == "__main__":
    from types import SimpleNamespace

    ollama_only = SimpleNamespace(
        hermes_enabled=False, ollama_base_url="http://127.0.0.1:11434/v1"
    )
    route = resolve_backend_route(ollama_only, None, "qwen3:8b")
    assert route.backend == "ollama" and route.model == "qwen3:8b"
    assert resolve_backend_route(ollama_only, None, "  ") is None

    # Hermes 가 켜져 있으면 전부 게이트웨이로
    hermes_on = SimpleNamespace(
        hermes_enabled=True,
        hermes_base_url="http://127.0.0.1:8642/v1",
        hermes_api_key="k",
        hermes_command="hermes",
        ollama_base_url="http://127.0.0.1:11434/v1",
    )

    import iris.infrastructure.hermes_client as hc

    original = hc.resolve_hermes_inference
    hc.resolve_hermes_inference = lambda m, **kw: SimpleNamespace(model=f"up/{m}", label=m)
    try:
        route = resolve_backend_route(hermes_on, None, "qwen3:8b")
        assert route.backend == "hermes" and route.target.model == "up/qwen3:8b"
        assert route.api_key == "k"

        # 해석이 실패하면 None
        hc.resolve_hermes_inference = lambda m, **kw: (_ for _ in ()).throw(ValueError("없음"))
        assert resolve_backend_route(hermes_on, None, "api:gone:x") is None
    finally:
        hc.resolve_hermes_inference = original

    # 루틴 고정 모델
    pinned = SimpleNamespace(model="qwen3:32b")
    route, note = route_for_routine(ollama_only, None, pinned, "gemma4:free")
    assert route.model == "qwen3:32b" and note == ""

    unpinned = SimpleNamespace(model="")
    route, note = route_for_routine(ollama_only, None, unpinned, "gemma4:free")
    assert route.model == "gemma4:free" and note == ""

    # 아무 모델도 없으면 솔직히 실패
    route, note = route_for_routine(ollama_only, None, unpinned, "")
    assert route is None and "정하지 못했" in note

    print("backend_route self-check ok")
