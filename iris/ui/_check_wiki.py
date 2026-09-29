"""ponytail: Iris Wiki write / slug / inbox self-check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from iris.knowledge.iris_wiki import (
    IrisWiki,
    IrisWikiNote,
    markdown_heading,
    match_wiki_notes,
    slugify_note_name,
)
from iris.ui.knowledge.wiki_graph_view import camera_aim, rotate_xyz


def main() -> None:
    assert slugify_note_name("Hello World!") == "hello-world"
    assert "위키" in slugify_note_name("Iris 위키 메모")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        path, rel = wiki.write_inbox_note(
            "Example Site",
            "- about: demo\n- topic: wiki",
            source_url="https://example.com",
        )
        assert rel == "inbox/example-site.md", rel
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "# Example Site" in text
        assert "https://example.com" in text
        assert any(n.rel_path == "user/inbox/example-site.md" for n in wiki.list_notes())

        try:
            wiki.write_inbox_note("x", "y", rel_path="docs/evil.md")
            raise AssertionError("docs write should fail")
        except ValueError:
            pass

        try:
            wiki.write_inbox_note("x", "y", rel_path="../outside.md")
            raise AssertionError("traversal should fail")
        except ValueError:
            pass

    assert markdown_heading("# network_security.pdf\n\nbody") == "network_security.pdf"
    notes = [
        IrisWikiNote("user/inbox/network_security.md", "Network Security", "user/inbox", "user"),
        IrisWikiNote("user/inbox/web.md", "Web Security Notes", "user/inbox", "user"),
        IrisWikiNote("user/inbox/other.md", "재고 관리", "user/inbox", "user"),
    ]
    sec = match_wiki_notes(notes, "security")
    assert [n.title for n in sec] == ["Network Security", "Web Security Notes"], sec
    assert match_wiki_notes(notes, "재고")[0].title == "재고 관리"
    assert match_wiki_notes(notes, "") == []
    for x, y, z in ((0.4, -0.2, 0.3), (-0.5, 0.1, 0.2), (0.1, 0.6, -0.4)):
        angle, tilt = camera_aim(x, y, z)
        x2, y2, z2 = rotate_xyz(x, y, z, angle, tilt)
        assert abs(x2) < 0.08 and abs(y2) < 0.08 and z2 > 0, (x2, y2, z2)

    from PyQt6.QtWidgets import QApplication

    from iris.ui.workspaces.obsidian_workspace_page import ObsidianWorkspacePage

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wiki = IrisWiki(docs_root=root / "docs", user_root=root / "wiki")
        wiki.write_inbox_note(
            "Network Security",
            "notes",
            rel_path="inbox/network-security.md",
        )
        page = ObsidianWorkspacePage()
        page.resize(1200, 700)
        page.set_wiki(wiki)
        graph = page._split.widget(0)
        info = page._split.widget(1)
        assert graph.minimumWidth() == 280
        assert info.minimumWidth() == 240
        page._split.resize(1200, 700)
        page._apply_saved_split()
        assert info.maximumWidth() == 500
        assert page._search.maximumWidth() == 280
        from iris.ui.workspaces.obsidian_workspace_page import _WikiSplitHandle

        assert page._split.handleWidth() == 10
        assert isinstance(page._split.handle(1), _WikiSplitHandle)
        page._search.setText("security")
        assert page._list.count() == 1
        page.activate_result()
        assert page._title.text() == "Network Security"
        assert page._graph._selected_rel.endswith("network-security.md")
        assert page._graph._aim is not None
        assert page._graph._aim["z1"] > 1.5
        page.hide_results()
    print("wiki self-check ok")


if __name__ == "__main__":
    main()
