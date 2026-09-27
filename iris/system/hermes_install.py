"""Hermes Windows 설치 우회 — uv managed Python junction(WinError 448) 회피.

공식 install.ps1 은 시스템 Python을 거부하고 checkout 전용 uv managed
interpreter 만 받는다. OneDrive/필터 등으로 minor-version junction 생성이
실패하면(os error 448) 설치가 멈춘다.

우회: staging clone + (3.11→3.12→3.13) Python 으로 venv 생성 후
uv sync(lock) 우선, 실패 시 pip install -e .
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from iris.system import hermes_gateway as gw

HERMES_REPO_HTTPS = "https://github.com/NousResearch/hermes-agent.git"
StreamFn = Callable[[str], None]
_HERMES_PYTHON_MIN = (3, 11)
_HERMES_PYTHON_MAX_EXCLUSIVE = (3, 14)
_LAST_BYPASS_LOG: str = ""
# trash/staging 잔존 상한 (오래된 것부터 삭제)
_MAX_TRASH_KEEP = 3
_NEEDS_USER_MSG_LIMIT = 800
_NEEDS_USER_MSG_LINES = 12

_UV_MOUNT_MARKERS = (
    "os error 448",
    "error 448",
    "신뢰할 수 없는 탑재",
    "untrusted mount",
    "failed to create python minor version link",
    "python 3.11 not available",
    "failed to install python 3.11",
)


def looks_like_uv_python_mount_failure(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return False
    return any(m in t for m in _UV_MOUNT_MARKERS)


def _no_window() -> dict:
    if sys.platform != "win32":
        return {}
    return {"creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0))}


def _run(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 600.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        **_no_window(),
    )


def python_version(path: Path) -> tuple[int, int] | None:
    """Return a candidate interpreter's major/minor version."""
    try:
        proc = _run(
            [str(path), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(?m)^(\d+)\.(\d+)\s*$", proc.stdout or "")
    return (int(match.group(1)), int(match.group(2))) if proc.returncode == 0 and match else None


def is_supported_hermes_python(path: Path) -> bool:
    version = python_version(path)
    return version is not None and _HERMES_PYTHON_MIN <= version < _HERMES_PYTHON_MAX_EXCLUSIVE


def find_bootstrap_python() -> Path | None:
    """Hermes venv 베이스 — `.python-version`(3.11) 정합: 3.11→3.12→3.13, Iris .venv는 맨 뒤."""
    try:
        from iris.system.hermes_iris_control_sync import project_root

        root = project_root()
    except Exception:  # noqa: BLE001
        root = Path.cwd()
    if sys.platform == "win32":
        py = shutil.which("py")
        if py:
            for flag in ("-3.11", "-3.12", "-3.13"):
                try:
                    proc = _run([py, flag, "-c", "import sys; print(sys.executable)"], timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                line = (proc.stdout or "").strip().splitlines()
                if proc.returncode == 0 and line:
                    p = Path(line[-1].strip())
                    if p.is_file() and is_supported_hermes_python(p):
                        return p
    for name in ("python3.11", "python3.12", "python3.13", "python3", "python"):
        found = shutil.which(name)
        if found and is_supported_hermes_python(Path(found)):
            return Path(found)
    for cand in (
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ):
        if cand.is_file() and is_supported_hermes_python(cand):
            return cand
    if sys.executable:
        p = Path(sys.executable)
        if p.is_file() and is_supported_hermes_python(p):
            return p
    return None


def ensure_system_python_winget(
    *,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    on_stream: StreamFn | None = None,
) -> Path | None:
    """winget 으로 Python 3.11 설치 시도. 이미 있으면 find_bootstrap_python."""
    existing = find_bootstrap_python()
    if existing is not None:
        return existing
    if sys.platform != "win32":
        return None
    winget = shutil.which("winget")
    if not winget:
        local = os.environ.get("LOCALAPPDATA", "")
        cand = Path(local) / "Microsoft" / "WindowsApps" / "winget.exe"
        winget = str(cand) if cand.is_file() else None
    if not winget:
        return None
    if on_stream:
        on_stream("시스템 Python 3.11 설치 (winget)…")
    cmd = [
        winget,
        "install",
        "-e",
        "--id",
        "Python.Python.3.11",
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    try:
        if run_streamed is not None:
            run_streamed(cmd, timeout=900.0, hard_timeout=1800.0, hidden=False)
        else:
            _run(cmd, timeout=1800.0)
    except (OSError, subprocess.TimeoutExpired):
        pass
    # PATH refresh for this process
    user = os.environ.get("PATH", "")
    machine = ""
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment"
        ) as key:
            user, _ = winreg.QueryValueEx(key, "Path")
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ) as key:
            machine, _ = winreg.QueryValueEx(key, "Path")
    except OSError:
        pass
    if user or machine:
        os.environ["PATH"] = f"{user};{machine}"
    return find_bootstrap_python()


def _kill_hermes_tree_holders(agent: Path) -> None:
    if sys.platform != "win32" or not agent.is_dir():
        return
    prefix = str(agent.resolve()).lower()
    try:
        import psutil  # type: ignore
    except ImportError:
        # taskkill by image — best effort
        flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for image in ("hermes.exe", "python.exe", "pythonw.exe"):
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", image],
                capture_output=True,
                creationflags=flags,
                timeout=8,
                check=False,
            )
        return
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            exe = (proc.info.get("exe") or "") or ""
            if exe and exe.lower().startswith(prefix):
                proc.kill()
        except (psutil.Error, OSError):
            continue
    time.sleep(0.4)


def force_retire_hermes_agent(
    *,
    command: str = "hermes",
    keep_staging: str | None = None,
) -> str:
    """잠긴 hermes-agent / .broken-* / staging-* 를 rename 으로 치우고 삭제 시도.

    keep_staging: 진행 중 clone 디렉터리명(예: hermes-agent.staging-…)만 보존.
    """
    home = gw.hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    try:
        gw.stop_hermes_gateway(command, wait_sec=6.0)
    except Exception:  # noqa: BLE001
        pass

    notes: list[str] = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    targets = [home / "hermes-agent"]
    try:
        targets.extend(
            sorted(
                p
                for p in home.iterdir()
                if p.is_dir()
                and (
                    p.name.startswith("hermes-agent.broken-")
                    or p.name.startswith("hermes-agent.trash-")
                    or (
                        p.name.startswith("hermes-agent.staging-")
                        and p.name != (keep_staging or "")
                    )
                )
            )
        )
    except OSError:
        pass

    for path in targets:
        if not path.exists():
            continue
        _kill_hermes_tree_holders(path)
        trash = home / f"hermes-agent.trash-{stamp}-{path.name[-8:]}"
        try:
            path.rename(trash)
            notes.append(f"치움→{trash.name}")
            path = trash
        except OSError as exc:
            notes.append(f"rename 실패({exc})")
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
        if path.exists():
            # robocopy mirror empty — Windows 잠금 파일 우회에 자주 통함
            empty = home / f".empty-wipe-{stamp}"
            try:
                empty.mkdir(exist_ok=True)
                subprocess.run(
                    [
                        "cmd",
                        "/c",
                        "robocopy",
                        str(empty),
                        str(path),
                        "/MIR",
                        "/NFL",
                        "/NDL",
                        "/NJH",
                        "/NJS",
                        "/nc",
                        "/ns",
                        "/np",
                    ],
                    capture_output=True,
                    timeout=120,
                    check=False,
                    **_no_window(),
                )
                shutil.rmtree(empty, ignore_errors=True)
                shutil.rmtree(path, ignore_errors=True)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if path.exists():
            notes.append(f"잔존:{path.name}")
        else:
            notes.append(f"삭제:{path.name}")

    # 오래된 trash 최대 N개 · 남은 staging(보존분 제외) 전부 삭제
    try:
        trashes = sorted(
            p for p in home.iterdir() if p.is_dir() and p.name.startswith("hermes-agent.trash-")
        )
        for old in trashes[:-_MAX_TRASH_KEEP]:
            shutil.rmtree(old, ignore_errors=True)
        for st in home.iterdir():
            if (
                st.is_dir()
                and st.name.startswith("hermes-agent.staging-")
                and st.name != (keep_staging or "")
            ):
                shutil.rmtree(st, ignore_errors=True)
    except OSError:
        pass
    return "; ".join(notes) if notes else "정리할 hermes-agent 없음"


def _user_path_prepend(scripts: Path) -> None:
    if sys.platform != "win32" or not scripts.is_dir():
        return
    s = str(scripts)
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
        ) as key:
            try:
                cur, typ = winreg.QueryValueEx(key, "Path")
            except OSError:
                cur, typ = "", winreg.REG_EXPAND_SZ
            parts = [p for p in str(cur).split(";") if p]
            if not any(p.lower() == s.lower() for p in parts):
                winreg.SetValueEx(key, "Path", 0, typ, s + ";" + str(cur))
    except OSError:
        pass
    path = os.environ.get("PATH", "")
    if s.lower() not in path.lower():
        os.environ["PATH"] = s + os.pathsep + path


def combined_install_log_tail(*parts: str, limit: int = 1200) -> str:
    blob = "\n".join(p for p in parts if p)
    if len(blob) <= limit:
        return blob
    return blob[-limit:]


def last_bypass_log_path() -> str:
    return _LAST_BYPASS_LOG


def new_bypass_pip_log_path() -> Path:
    logs = gw.hermes_home() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return logs / f"iris-bypass-pip-{stamp}.log"


def write_bypass_pip_log(stdout: str, stderr: str, *, path: Path | None = None) -> Path:
    global _LAST_BYPASS_LOG
    log_path = path or new_bypass_pip_log_path()
    blob = "\n".join(p for p in (stderr or "", stdout or "") if p)
    log_path.write_text(blob, encoding="utf-8", errors="replace")
    _LAST_BYPASS_LOG = str(log_path)
    return log_path


def format_pip_failure(stdout: str, stderr: str, *, log_path: Path | str) -> str:
    """pip 실패 메시지 — 앞(Obtaining…)이 아니라 꼬리 + 전체 로그 경로."""
    tail = combined_install_log_tail(stderr or "", stdout or "", limit=1200)
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    short = "\n".join(lines[-_NEEDS_USER_MSG_LINES:]) if lines else "(로그 없음)"
    return f"pip 설치 실패 (로그: {log_path})\n{short}"


def format_runtime_failure(detail: str, *, log_path: Path | str) -> str:
    """우회 설치 후 probe/import 실패 — pip 실패와 동일하게 로그 경로 + 꼬리."""
    tail = combined_install_log_tail(detail or "", limit=1200)
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    short = "\n".join(lines[-_NEEDS_USER_MSG_LINES:]) if lines else "(로그 없음)"
    return f"우회 설치 후 런타임 실패 (로그: {log_path})\n{short}"


def clip_needs_user_message(msg: str, *, limit: int = _NEEDS_USER_MSG_LIMIT) -> str:
    """NeedsUser 카드용 — 마지막 N줄·전체 limit자(꼬리). 전체 로그는 파일에만."""
    text = (msg or "").strip()
    if not text:
        return text
    lines = [ln for ln in text.splitlines() if ln.strip()]
    short = "\n".join(lines[-_NEEDS_USER_MSG_LINES:]) if lines else text
    if len(short) <= limit:
        return short
    return short[-limit:]


def should_skip_official_installer(
    *,
    prefer_bypass: bool,
    last_error: object = None,
) -> bool:
    """R1(a): 세션 prefer_bypass 또는 직전 last_error가 bypass/448이면 공식 생략."""
    if prefer_bypass:
        return True
    if isinstance(last_error, dict):
        kind = str(last_error.get("kind") or "").lower()
        if kind.startswith("bypass") or "448" in kind:
            return True
        if looks_like_uv_python_mount_failure(str(last_error.get("tail") or "")):
            return True
    return False


def _run_pkg_install(
    cmd: list[str],
    *,
    cwd: str,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """pip/uv 단계 — quiet 구간 idle 오탐 방지(hard만, idle 없음)."""
    if run_streamed is not None:
        return run_streamed(
            cmd,
            cwd=cwd,
            env=env,
            timeout=None,
            hard_timeout=3600.0,
            hidden=True,
        )
    return _run(cmd, cwd=cwd, env=env, timeout=3600.0)


def _try_uv_sync(
    agent: Path,
    venv_py: Path,
    venv_dir: Path,
    *,
    on_stream: StreamFn | None,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None,
) -> subprocess.CompletedProcess[str] | None:
    """uv.lock 있으면 uv sync --frozen (Hermes `venv/` 경로 유지). 없으면 None."""
    if not (agent / "uv.lock").is_file():
        return None
    uv = shutil.which("uv")
    if not uv:
        return None
    if on_stream:
        on_stream("uv sync --frozen (lock)…")
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    cmd = [
        uv,
        "sync",
        "--frozen",
        "--active",
        "--python",
        str(venv_py),
        "--extra",
        "homeassistant",
        "--extra",
        "mcp",
    ]
    try:
        return _run_pkg_install(cmd, cwd=str(agent), run_streamed=run_streamed, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def _swap_staging_into_place(home: Path, staging: Path, agent: Path) -> str | None:
    """staging → hermes-agent rename. 실패 시 메시지."""
    if agent.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        trash = home / f"hermes-agent.trash-{stamp}-swap"
        try:
            agent.rename(trash)
            shutil.rmtree(trash, ignore_errors=True)
        except OSError as exc:
            return f"기존 hermes-agent 교체 실패: {exc}"
    try:
        staging.rename(agent)
    except OSError as exc:
        return f"staging rename 실패: {exc}"
    return None


def install_hermes_with_system_python(
    *,
    command: str = "hermes",
    on_stream: StreamFn | None = None,
    run_streamed: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """공식 스크립트 대신 staging clone+venv+uv/pip 로 Hermes 설치."""

    def _emit(msg: str) -> None:
        if on_stream:
            on_stream(msg)

    if should_abort and should_abort():
        return False, "사용자가 중단함"

    py = ensure_system_python_winget(run_streamed=run_streamed, on_stream=on_stream)
    if py is None:
        return False, "베이스 Python을 찾지 못했습니다 (py -3.11 / winget Python.Python.3.11)"

    _emit(f"우회 설치: 베이스 Python = {py}")
    wipe = force_retire_hermes_agent(command=command)
    _emit(f"런타임 정리: {wipe}")

    home = gw.hermes_home()
    agent = home / "hermes-agent"
    home.mkdir(parents=True, exist_ok=True)
    git = shutil.which("git")
    if not git:
        return False, "git 이 없습니다"

    if should_abort and should_abort():
        return False, "사용자가 중단함"

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    staging = home / f"hermes-agent.staging-{stamp}"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)

    _emit(f"Hermes 저장소 HTTPS clone → {staging.name}…")
    clone = _run(
        [git, "-c", "core.longpaths=true", "clone", "--depth", "1", HERMES_REPO_HTTPS, str(staging)],
        timeout=600.0,
    )
    if clone.returncode != 0 or not staging.is_dir():
        err = combined_install_log_tail(clone.stderr or "", clone.stdout or "", limit=400)
        shutil.rmtree(staging, ignore_errors=True)
        return False, f"git clone 실패: {err}"

    work = staging
    venv_dir = work / "venv"
    _emit("venv 생성 (시스템 Python, uv managed 없음)…")
    venv_proc = _run([str(py), "-m", "venv", str(venv_dir)], timeout=180.0)
    if venv_proc.returncode != 0:
        err = combined_install_log_tail(venv_proc.stderr or "", venv_proc.stdout or "", limit=300)
        shutil.rmtree(staging, ignore_errors=True)
        return False, f"venv 실패: {err}"

    venv_py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not venv_py.is_file():
        shutil.rmtree(staging, ignore_errors=True)
        return False, f"venv python 없음: {venv_py}"

    if should_abort and should_abort():
        shutil.rmtree(staging, ignore_errors=True)
        return False, "사용자가 중단함"

    log_path = new_bypass_pip_log_path()
    install_out = ""
    install_err = ""
    pip: subprocess.CompletedProcess[str] | None = None

    uv_result = _try_uv_sync(
        work, venv_py, venv_dir, on_stream=on_stream, run_streamed=run_streamed
    )
    if uv_result is not None and uv_result.returncode == 0:
        pip = uv_result
        install_out = uv_result.stdout or ""
        install_err = uv_result.stderr or ""
        _emit("uv sync 완료")
    else:
        if uv_result is not None:
            _emit("uv sync 실패 — pip -e 폴백…")
            install_out += uv_result.stdout or ""
            install_err += uv_result.stderr or ""
        _emit("pip 업그레이드…")
        _run(
            [str(venv_py), "-m", "pip", "install", "-U", "pip", "wheel", "setuptools"],
            timeout=300.0,
        )
        # API gateway→aiohttp([homeassistant]), MCP→mcp([mcp]).
        _emit("Hermes 패키지 설치 (pip install -e .)…")
        pip_cmd = [str(venv_py), "-m", "pip", "install", "-e", ".[homeassistant,mcp]"]
        try:
            pip = _run_pkg_install(pip_cmd, cwd=str(work), run_streamed=run_streamed)
        except (OSError, subprocess.TimeoutExpired) as exc:
            write_bypass_pip_log(install_out, f"{install_err}\n{exc}", path=log_path)
            shutil.rmtree(staging, ignore_errors=True)
            return False, format_pip_failure(install_out, f"{install_err}\n{exc}", log_path=log_path)

        install_out += pip.stdout or ""
        install_err += pip.stderr or ""

        if pip.returncode != 0:
            _emit(".[homeassistant,mcp] 실패 — core + aiohttp/mcp 폴백…")
            pip_cmd = [str(venv_py), "-m", "pip", "install", "-e", "."]
            try:
                pip = _run_pkg_install(pip_cmd, cwd=str(work), run_streamed=run_streamed)
            except (OSError, subprocess.TimeoutExpired) as exc:
                write_bypass_pip_log(install_out, f"{install_err}\n{exc}", path=log_path)
                shutil.rmtree(staging, ignore_errors=True)
                return False, format_pip_failure(
                    install_out, f"{install_err}\n{exc}", log_path=log_path
                )
            install_out += pip.stdout or ""
            install_err += pip.stderr or ""
            if pip.returncode == 0:
                boost = _run(
                    [
                        str(venv_py),
                        "-m",
                        "pip",
                        "install",
                        "aiohttp==3.14.3",
                        "mcp==2.0.0",
                        "httpx2==2.7.0",
                        "starlette==1.3.1",
                    ],
                    timeout=300.0,
                )
                install_out += boost.stdout or ""
                install_err += boost.stderr or ""
                if boost.returncode != 0:
                    write_bypass_pip_log(install_out, install_err, path=log_path)
                    shutil.rmtree(staging, ignore_errors=True)
                    return False, format_pip_failure(install_out, install_err, log_path=log_path)

        if pip.returncode != 0:
            # dead requirements.txt 폴백 제거 — lock 있으면 uv export → pip
            uv = shutil.which("uv")
            if uv and (work / "uv.lock").is_file():
                _emit("pip -e 실패 — uv export → pip 폴백…")
                export_path = work / ".iris-uv-export.txt"
                exp = _run(
                    [uv, "export", "--frozen", "--no-hashes", "-o", str(export_path)],
                    cwd=str(work),
                    timeout=120.0,
                )
                install_out += exp.stdout or ""
                install_err += exp.stderr or ""
                if exp.returncode == 0 and export_path.is_file():
                    try:
                        pip = _run_pkg_install(
                            [str(venv_py), "-m", "pip", "install", "-r", str(export_path)],
                            cwd=str(work),
                            run_streamed=run_streamed,
                        )
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        write_bypass_pip_log(install_out, f"{install_err}\n{exc}", path=log_path)
                        shutil.rmtree(staging, ignore_errors=True)
                        return False, format_pip_failure(
                            install_out, f"{install_err}\n{exc}", log_path=log_path
                        )
                    install_out += pip.stdout or ""
                    install_err += pip.stderr or ""

            if pip.returncode != 0:
                write_bypass_pip_log(install_out, install_err, path=log_path)
                shutil.rmtree(staging, ignore_errors=True)
                return False, format_pip_failure(install_out, install_err, log_path=log_path)

    swap_err = _swap_staging_into_place(home, staging, agent)
    if swap_err:
        write_bypass_pip_log(install_out, f"{install_err}\n{swap_err}", path=log_path)
        shutil.rmtree(staging, ignore_errors=True)
        return False, swap_err

    # 성공 시에도 전체 로그 남김(지원용)
    write_bypass_pip_log(install_out or "(ok)", install_err, path=log_path)

    venv_dir = agent / "venv"
    venv_py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    scripts = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    _user_path_prepend(scripts)

    hermes_exe = scripts / ("hermes.exe" if sys.platform == "win32" else "hermes")
    if not hermes_exe.is_file():
        check = _run(
            [str(venv_py), "-c", "import hermes_cli, aiohttp, mcp"],
            timeout=60.0,
        )
        if check.returncode != 0:
            blob_err = "\n".join(
                p
                for p in (
                    install_err,
                    check.stderr or "",
                    check.stdout or "",
                    "hermes_cli/aiohttp/mcp import 실패",
                )
                if p
            )
            write_bypass_pip_log(install_out, blob_err, path=log_path)
            return False, format_runtime_failure(
                "hermes_cli/aiohttp/mcp import 실패 — 패키지 설치 불완전",
                log_path=log_path,
            )

    ok, detail = gw.probe_hermes_runtime(command=command, timeout_sec=30.0)
    if ok:
        return True, f"우회 설치 성공 ({detail})"
    if venv_py.is_file():
        check = _run(
            [str(venv_py), "-c", "import hermes_cli, aiohttp, mcp; print('ok')"],
            timeout=60.0,
        )
        if check.returncode == 0 and "ok" in (check.stdout or ""):
            return True, f"우회 설치 성공 (venv import ok; probe={detail})"
    write_bypass_pip_log(
        install_out or "",
        "\n".join(p for p in (install_err, f"probe: {detail}") if p),
        path=log_path,
    )
    return False, format_runtime_failure(str(detail), log_path=log_path)


if __name__ == "__main__":
    assert looks_like_uv_python_mount_failure(
        "Failed to create Python minor version link directory\n"
        "cause: 경로에 신뢰할 수 없는 탑재 지점이 포함되어 있습니다. (os error 448)"
    )
    assert looks_like_uv_python_mount_failure("Python 3.11 not available")
    assert not looks_like_uv_python_mount_failure("connection refused")
    head = "Obtaining file:///tmp/hermes-agent\nInstalling build dependencies...\n"
    err = "ERROR: Could not find a version that satisfies the requirement missing-pkg\n"
    msg = format_pip_failure(head + ("...\n" * 80) + err, "", log_path="iris-bypass-pip-test.log")
    assert "ERROR:" in msg and "iris-bypass-pip" in msg
    assert not msg.strip().endswith("Obtaining file:///tmp/hermes-agent")
    assert should_skip_official_installer(
        prefer_bypass=False,
        last_error={"kind": "bypass_pip", "tail": "x"},
    )
    assert should_skip_official_installer(prefer_bypass=True, last_error=None)
    assert not should_skip_official_installer(prefer_bypass=False, last_error=None)
    rt = format_runtime_failure("probe timeout", log_path="iris-bypass-pip-rt.log")
    assert "런타임 실패" in rt and "iris-bypass-pip-rt" in rt
    clipped = clip_needs_user_message("line\n" * 40 + ("x" * 900))
    assert len(clipped) <= _NEEDS_USER_MSG_LIMIT
    print("hermes_install helpers ok", find_bootstrap_python())
