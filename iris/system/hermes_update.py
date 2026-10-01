"""Hermes git 설치본이 origin/main 보다 뒤인지 확인하고, 버튼으로 갱신한다.

검사만 하고 설치는 하지 않는다. 적용은 ``hermes update --yes`` 후 gateway 재시작.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from iris.system.win_subprocess import no_window_kwargs

_UPDATE_TIMEOUT_SEC = 2400.0


@dataclass(frozen=True)
class HermesUpdateStatus:
    available: bool
    local_sha: str = ""
    remote_sha: str = ""
    detail: str = ""
    repo: str = ""


def hermes_repo_dir(command: str = "hermes") -> Path | None:
    """실행 중인 hermes 체크아웃. venv Scripts 위, 없으면 HERMES_HOME/hermes-agent."""
    from iris.infrastructure.hermes_credentials import hermes_home
    from iris.system.hermes_gateway import hermes_executable

    exe = hermes_executable(command)
    if exe:
        for parent in Path(exe).resolve().parents:
            if (parent / ".git").exists() and (parent / "hermes_cli").is_dir():
                return parent
    repo = hermes_home() / "hermes-agent"
    if (repo / ".git").exists():
        return repo
    return None


def _git(repo: Path, *args: str, timeout: float = 25.0) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            **no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def fetch_hermes_remote_sha(repo: Path) -> str:
    """origin/main SHA. 네트워크 실패 시 빈 문자열."""
    text = _git(repo, "ls-remote", "origin", "refs/heads/main", timeout=25.0)
    sha = text.split()[0] if text else ""
    if len(sha) >= 7 and all(c in "0123456789abcdefABCDEF" for c in sha):
        return sha
    return ""


def check_hermes_update(
    *,
    command: str = "hermes",
    repo: Path | None = None,
    remote_sha: str | None = None,
) -> HermesUpdateStatus:
    """로컬 HEAD와 origin/main 이 다르면 업데이트 가능.

    ``remote_sha`` 를 넘기면 네트워크를 타지 않는다 (자검용).
    """
    root = repo if repo is not None else hermes_repo_dir(command)
    if root is None or not (root / ".git").exists():
        return HermesUpdateStatus(available=False, detail="Hermes git 설치 없음")
    local = _git(root, "rev-parse", "HEAD", timeout=15.0)
    if not local:
        return HermesUpdateStatus(
            available=False, detail="로컬 리비전 확인 실패", repo=str(root)
        )
    remote = (remote_sha if remote_sha is not None else fetch_hermes_remote_sha(root)).strip()
    if not remote:
        return HermesUpdateStatus(
            available=False,
            local_sha=local,
            detail="원격 main 확인 실패",
            repo=str(root),
        )
    if local.lower() == remote.lower():
        return HermesUpdateStatus(
            available=False,
            local_sha=local,
            remote_sha=remote,
            detail="최신",
            repo=str(root),
        )
    return HermesUpdateStatus(
        available=True,
        local_sha=local,
        remote_sha=remote,
        detail=f"{local[:7]} → {remote[:7]}",
        repo=str(root),
    )


def hermes_update_argv(exe: str) -> list[str]:
    return [exe, "update", "--yes"]


def _note(on_progress: Callable[[str], None] | None, msg: str) -> None:
    if on_progress:
        on_progress(msg)


def apply_hermes_update(
    *,
    command: str = "hermes",
    base_url: str = "",
    api_key: str = "",
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """``hermes update --yes`` 후 gateway 를 다시 띄운다.

    Windows 에서 gateway 가 venv 파일을 잠그므로 갱신 전에 먼저 내린다.
    갱신이 실패해도 gateway 는 다시 올리려 한다.
    """
    from iris.system.hermes_gateway import (
        get_last_gateway_diagnosis,
        hermes_executable,
        restart_hermes_gateway,
        stop_hermes_gateway,
    )

    exe = hermes_executable(command)
    if not exe:
        raise RuntimeError("hermes 실행 파일이 없습니다")
    repo = hermes_repo_dir(command)

    _note(on_progress, "Hermes gateway 중지…")
    stop_hermes_gateway(command, wait_sec=20.0)

    _note(on_progress, "Hermes 업데이트 중…")
    try:
        proc = subprocess.run(
            hermes_update_argv(exe),
            cwd=str(repo) if repo is not None else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=_UPDATE_TIMEOUT_SEC,
            check=False,
            **no_window_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        _restart_after(command, base_url, api_key, on_progress)
        raise RuntimeError("Hermes 업데이트 시간 초과") from exc
    except OSError as exc:
        _restart_after(command, base_url, api_key, on_progress)
        raise RuntimeError(f"Hermes 업데이트를 시작하지 못했습니다: {exc}") from exc

    tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    if proc.returncode != 0:
        _restart_after(command, base_url, api_key, on_progress)
        snippet = tail[-400:] if tail else str(proc.returncode)
        raise RuntimeError(f"hermes update 실패: {snippet}")

    _note(on_progress, "Hermes gateway 재시작…")
    ok = restart_hermes_gateway(
        base_url,
        api_key=api_key,
        command=command,
        wait_sec=90.0,
        on_progress=on_progress,
    )
    if not ok:
        diag = get_last_gateway_diagnosis()
        why = (diag.message if diag is not None else "") or "gateway 재시작 실패"
        raise RuntimeError(f"업데이트는 적용됐으나 gateway 재시작 실패: {why[:240]}")
    return "Hermes 업데이트가 끝났고 gateway를 재시작했습니다."


def _restart_after(
    command: str,
    base_url: str,
    api_key: str,
    on_progress: Callable[[str], None] | None,
) -> None:
    from iris.system.hermes_gateway import restart_hermes_gateway

    _note(on_progress, "Hermes gateway 재시작…")
    try:
        restart_hermes_gateway(
            base_url,
            api_key=api_key,
            command=command,
            wait_sec=90.0,
            on_progress=on_progress,
        )
    except Exception:
        return
