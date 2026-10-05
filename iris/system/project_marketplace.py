"""열린 프로젝트의 Open VSX 확장. 설치는 VSIX를 Theia deployedPlugins 에 푼다."""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\.[A-Za-z0-9][A-Za-z0-9_-]*$")


def search_extensions(query: str, *, fetch=None) -> list[dict[str, str]]:
    text = (query or "").strip()
    if not text:
        raise ValueError("query required")
    url = "https://open-vsx.org/api/-/search?size=8&query=" + quote(text)
    raw = fetch(url) if fetch is not None else _http_json(url)
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, str]] = []
    for item in raw.get("extensions") or []:
        if not isinstance(item, dict):
            continue
        ns = str(item.get("namespace") or "").strip()
        name = str(item.get("name") or "").strip()
        ext_id = f"{ns}.{name}" if ns and name else ""
        if not _ID.match(ext_id):
            continue
        out.append(
            {
                "id": ext_id,
                "version": str(item.get("version") or ""),
                "display_name": str(item.get("displayName") or item.get("display_name") or name),
            }
        )
    return out


def pin_extension(project_root: str, extension_id: str) -> dict[str, str]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("열린 프로젝트가 없습니다.")
    ext_id = (extension_id or "").strip()
    if not _ID.match(ext_id):
        raise ValueError("extension id는 publisher.name 형식이어야 합니다.")
    vs = root / ".vscode" / "extensions.json"
    vs.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if vs.is_file():
        try:
            loaded = json.loads(vs.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    recs = data.get("recommendations")
    if not isinstance(recs, list):
        recs = []
    if ext_id not in recs:
        recs.append(ext_id)
    data["recommendations"] = recs
    vs.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    iris = root / ".iris"
    iris.mkdir(parents=True, exist_ok=True)
    market = iris / "marketplace.json"
    pinned: list = []
    if market.is_file():
        try:
            loaded = json.loads(market.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                pinned = loaded
        except json.JSONDecodeError:
            pinned = []
    if not any(isinstance(row, dict) and row.get("id") == ext_id for row in pinned):
        pinned.append({"id": ext_id, "source": "open-vsx"})
    market.write_text(json.dumps(pinned, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"id": ext_id, "recommendations": str(vs), "record": str(market)}


_MAX_VSIX = 40_000_000
_MAX_UNPACKED = 80_000_000


def install_extension(
    project_root: str,
    extension_id: str,
    deploy_root: str,
    *,
    fetch=None,
    download=None,
) -> dict[str, str]:
    """핀 다음 Open VSX VSIX를 deployedPlugins/<id>/ 에 푼다. package.json 이 있을 때만 반환."""
    pinned = pin_extension(project_root, extension_id)
    ext_id = pinned["id"]
    dest_root = Path(deploy_root).expanduser().resolve()
    if not str(dest_root):
        raise ValueError("deploy root required")
    ns, name = ext_id.split(".", 1)
    meta_url = f"https://open-vsx.org/api/{quote(ns)}/{quote(name)}"
    raw = fetch(meta_url) if fetch is not None else _http_json(meta_url)
    if not isinstance(raw, dict):
        raise ValueError("Open VSX metadata was not an object")
    files = raw.get("files") if isinstance(raw.get("files"), dict) else {}
    download_url = str(files.get("download") or "").strip()
    version = str(raw.get("version") or "").strip()
    if not download_url.startswith("https://"):
        raise ValueError("Open VSX download URL missing")
    blob = download(download_url) if download is not None else _http_bytes(download_url)
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        raise ValueError("empty VSIX")
    folder = dest_root / ext_id
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        _extract_vsix(bytes(blob), folder)
        package = folder / "extension" / "package.json"
        meta = _require_vscode_package(package)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    _stamp_record(Path(pinned["record"]), ext_id, version or str(meta.get("version") or ""), str(folder))
    return {
        "id": ext_id,
        "version": version or str(meta.get("version") or ""),
        "recommendations": pinned["recommendations"],
        "record": pinned["record"],
        "deployed": str(folder),
        "package": str(package),
        "installed": "true",
    }


def _extract_vsix(blob: bytes, folder: Path) -> None:
    root = folder.resolve()
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ValueError("VSIX is not a zip") from exc
    with zf:
        total = 0
        for info in zf.infolist():
            total += int(info.file_size)
            if total > _MAX_UNPACKED:
                raise ValueError("VSIX unpacked size exceeds 80MB")
            name = info.filename.replace("\\", "/")
            if not name or name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("VSIX path escapes the deploy folder")
            target = (root / name).resolve()
            if target != root and root not in target.parents:
                raise ValueError("VSIX path escapes the deploy folder")
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


def _require_vscode_package(package: Path) -> dict:
    if not package.is_file():
        raise ValueError("VSIX has no extension/package.json")
    try:
        meta = json.loads(package.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("extension/package.json is not JSON") from exc
    if not isinstance(meta, dict):
        raise ValueError("extension/package.json is not an object")
    engines = meta.get("engines") if isinstance(meta.get("engines"), dict) else {}
    if not str(meta.get("name") or "").strip() or not str(meta.get("version") or "").strip():
        raise ValueError("extension/package.json missing name or version")
    if not str(engines.get("vscode") or "").strip():
        raise ValueError("extension/package.json missing engines.vscode")
    return meta


def _stamp_record(market: Path, ext_id: str, version: str, deployed: str) -> None:
    try:
        loaded = json.loads(market.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = []
    if not isinstance(loaded, list):
        loaded = []
    found = False
    for row in loaded:
        if isinstance(row, dict) and row.get("id") == ext_id:
            row["version"] = version
            row["deployed"] = deployed
            row["source"] = "open-vsx"
            found = True
    if not found:
        loaded.append({"id": ext_id, "source": "open-vsx", "version": version, "deployed": deployed})
    market.write_text(json.dumps(loaded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _http_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "iris-light"})
    with urlopen(req, timeout=30) as resp:
        chunks: list[bytes] = []
        size = 0
        while True:
            part = resp.read(1024 * 256)
            if not part:
                break
            size += len(part)
            if size > _MAX_VSIX:
                raise ValueError("VSIX exceeds 40MB")
            chunks.append(part)
    return b"".join(chunks)


def _http_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "iris-light", "Accept": "application/json"})
    with urlopen(req, timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}
