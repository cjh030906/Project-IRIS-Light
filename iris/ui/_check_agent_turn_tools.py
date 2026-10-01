"""Hermes가 켜져 있으면 채팅 의도 6종은 모델 도구로 간다.

  .venv\\Scripts\\python.exe -m iris.ui._check_agent_turn_tools
"""

from __future__ import annotations

from iris.runtime.agent_local_gate import hermes_owns_local_intents
from iris.ui._check_control_action_split import _surface


def main() -> None:
    assert hermes_owns_local_intents(True) is True
    assert hermes_owns_local_intents(False) is False

    _window, reg = _surface()
    names = {item["name"] for item in reg.catalog()}
    for name in ("note.export_pdf", "extension.install_github", "project.write_image_code"):
        assert name in names, name

    missing_content = reg.invoke("note.export_pdf", {})
    assert missing_content["ok"] is False
    assert "content" in missing_content["error"]

    missing_url = reg.invoke("extension.install_github", {})
    assert missing_url["ok"] is False
    assert "url" in missing_url["error"]

    missing_image = reg.invoke("project.write_image_code", {})
    assert missing_image["ok"] is False
    assert "image" in missing_image["error"]

    missing_file = reg.invoke(
        "project.write_image_code",
        {"image": "C:/no/such-iris-image.png", "rel_path": "a.py"},
    )
    assert missing_file["ok"] is False
    assert "image" in missing_file["error"]
    print("agent turn tools ok")


if __name__ == "__main__":
    main()
