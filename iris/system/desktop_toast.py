"""아이리스가 꺼져 있을 때 쓰는 바탕화면 알림.

앱이 떠 있으면 기존 알림 패널(`notify.add_alert`)이 훨씬 낫다. 여기는 **창이 없는
상태**에서 예약 루틴 결과를 알리는 용도다.

새 pip 의존성을 쓰지 않는다. Windows 에 원래 있는 PowerShell 로 WinRT 토스트를
띄우고, 그게 막히면(정책·PowerShell 제한 등) 조용히 실패한다 — 알림을 못 띄웠다고
루틴 결과까지 잃으면 안 된다. 결과는 어차피 DB·위키에 남는다.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

APP_ID = "Iris.Light"
_TIMEOUT_SEC = 20

# Windows 는 **등록된 AppUserModelID** 로 온 토스트만 띄운다. 모르는 AppID 로 보내면
# PowerShell 은 종료 코드 0 을 주고 알림은 조용히 사라진다 — 실패를 알 방법이 없다.
# 그래서 먼저 시작 메뉴 바로가기로 우리 AppID 를 등록하고, 그게 안 되면 항상 등록돼
# 있는 PowerShell 의 AppID 를 빌려 쓴다(앱 이름이 "Windows PowerShell" 로 뜨는 대신
# 알림은 확실히 뜬다).
POWERSHELL_AUMID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
    "\\WindowsPowerShell\\v1.0\\powershell.exe"
)
SHORTCUT_NAME = "Iris Light.lnk"


def is_supported() -> bool:
    return platform.system() == "Windows"


def _xml_escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _ps_quote(text: str) -> str:
    """PowerShell 작은따옴표 문자열 — 안의 작은따옴표는 두 번."""
    return "'" + str(text or "").replace("'", "''") + "'"


def build_toast_xml(title: str, body: str, *, launch: str = "") -> str:
    """토스트 XML.

    `launch` 를 주면 눌렀을 때 그 URI 가 열린다(`activationType="protocol"`).
    COM 활성화와 달리 COM 서버를 등록할 필요가 없다.

    PowerShell 로 감싸기 전 단계라 따옴표가 그대로다 — 검증은 여기서 한다.
    """
    attrs = ""
    if str(launch or "").strip():
        attrs = f" activationType='protocol' launch='{_xml_escape(launch)}'"
    return (
        f"<toast{attrs}><visual><binding template='ToastGeneric'>"
        f"<text>{_xml_escape(title)}</text>"
        f"<text>{_xml_escape(body)}</text>"
        "</binding></visual></toast>"
    )


def build_toast_script(
    title: str,
    body: str,
    *,
    app_id: str = APP_ID,
    launch: str = "",
) -> str:
    """토스트를 띄우는 PowerShell 한 덩어리."""
    xml = build_toast_xml(title, body, launch=launch)
    return (
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType=WindowsRuntime] > $null; "
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
        "ContentType=WindowsRuntime] > $null; "
        "$doc = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f"$doc.LoadXml({_ps_quote(xml)}); "
        "$toast = New-Object Windows.UI.Notifications.ToastNotification $doc; "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        f"{_ps_quote(app_id)}).Show($toast)"
    )


def start_menu_shortcut() -> Path:
    appdata = os.environ.get("APPDATA") or ""
    base = Path(appdata) if appdata else Path.home() / "AppData/Roaming"
    return base / "Microsoft/Windows/Start Menu/Programs" / SHORTCUT_NAME


def register_app_id(app_id: str = APP_ID) -> bool:
    """시작 메뉴 바로가기에 AppUserModelID 를 심어 우리 이름으로 알림을 보낼 수 있게.

    Windows 는 이 바로가기를 보고 AppID 를 인정한다. 한 번만 만들면 된다.
    실패해도 예외를 올리지 않는다 — 폴백 AppID 가 있다.
    """
    if not is_supported():
        return False
    link = start_menu_shortcut()
    if link.is_file():
        return True
    try:
        import pythoncom
        from win32com.client import Dispatch
        from win32comext.propsys import propsys, pscon

        link.parent.mkdir(parents=True, exist_ok=True)
        shortcut = Dispatch("WScript.Shell").CreateShortCut(str(link))
        shortcut.TargetPath = sys.executable
        shortcut.Arguments = ""
        shortcut.Description = "Iris Light"
        shortcut.save()

        store = propsys.SHGetPropertyStoreFromParsingName(
            str(link), None, 0x00000002, propsys.IID_IPropertyStore
        )
        store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id))
        store.Commit()
        return True
    except Exception:  # noqa: BLE001
        # 바로가기를 못 만들면 폴백으로 간다. 만들다 만 파일은 치운다.
        try:
            if link.is_file():
                link.unlink()
        except OSError:
            pass
        return False


def _send(head: str, text: str, app_id: str, launch: str = "") -> bool:
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                build_toast_script(head, text, app_id=app_id, launch=launch),
            ],
            capture_output=True,
            timeout=_TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def resolve_app_id(preferred: str = APP_ID) -> str:
    """실제로 쓸 AppID. 우리 것을 등록했으면 그것, 아니면 PowerShell 것."""
    return preferred if register_app_id(preferred) else POWERSHELL_AUMID


def ensure_click_handler() -> bool:
    """토스트를 누르면 아이리스가 뜨도록 URI 스킴을 등록한다."""
    try:
        from iris.system.uri_handler import register

        return register().registered
    except Exception:  # noqa: BLE001
        return False


def show_toast(
    title: str,
    body: str,
    *,
    app_id: str = "",
    launch: str = "",
) -> bool:
    """바탕화면 알림.

    `launch` 를 주면 눌렀을 때 그 URI 가 열린다. 스킴 등록은 여기서 알아서 한다.

    반환 True 는 "PowerShell 이 오류 없이 끝났다"는 뜻이다. Windows 가 실제로
    화면에 띄웠는지는 알 수 없다(집중 지원·알림 끔 설정이면 센터로만 간다).
    """
    if not is_supported():
        return False
    head = str(title or "").strip() or "Iris"
    text = str(body or "").strip()
    if not text:
        return False
    target = str(launch or "").strip()
    if target and not ensure_click_handler():
        # 스킴을 못 걸었으면 누를 수 없는 토스트다. 알림 자체는 그대로 띄운다.
        target = ""
    chosen = (app_id or "").strip() or resolve_app_id()
    if _send(head, text, chosen, target):
        return True
    # 우리 AppID 로 실패했으면 확실히 등록된 쪽으로 한 번 더.
    if chosen != POWERSHELL_AUMID:
        return _send(head, text, POWERSHELL_AUMID, target)
    return False


if __name__ == "__main__":
    assert _xml_escape("<a & b>") == "&lt;a &amp; b&gt;"
    assert _xml_escape('"q"') == "&quot;q&quot;"
    assert _ps_quote("it's") == "'it''s'"

    script = build_toast_script("아침 뉴스", "1. A  2. B")
    assert "ToastNotificationManager" in script
    assert "아침 뉴스" in script and "1. A" in script
    # 사용자 문자열이 스크립트를 깨뜨리면 안 된다
    nasty = build_toast_script("'; Remove-Item C:\\ -Recurse; '", "<script>")
    assert "Remove-Item C:\\ -Recurse" in nasty  # 문자열 안에 갇혀 있다
    assert nasty.count("'") % 2 == 0
    assert "&lt;script&gt;" in nasty

    clickable = build_toast_xml("t", "b", launch="iris-light://routine/3")
    assert "activationType='protocol'" in clickable
    assert "launch='iris-light://routine/3'" in clickable
    assert "activationType" not in build_toast_xml("t", "b")
    assert build_toast_xml("t", "b", launch="   ") == build_toast_xml("t", "b")
    # launch 값도 XML 이스케이프를 거쳐야 한다
    assert "&amp;" in build_toast_xml("t", "b", launch="x://a?b=1&c=2")
    assert "&apos;" in build_toast_xml("t", "b", launch="x://a'b")
    # 스크립트로 감싸면 작은따옴표가 두 번이 된다(PowerShell 리터럴 규칙)
    assert "activationType=''protocol''" in build_toast_script(
        "t", "b", launch="iris-light://routine/3"
    )

    assert show_toast("제목", "") is False  # 빈 본문은 안 띄운다
    print("desktop_toast self-check ok")
