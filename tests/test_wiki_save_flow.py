from pathlib import Path

import tempfile
import unittest

from iris.knowledge.iris_wiki import IrisWiki
from iris.knowledge.wiki_import_ops import import_to_wiki, save_answer_to_wiki
from iris.knowledge.wiki_save_intent import parse_wiki_save_request


def check_save_answer_with_sources(tmp_path, prompt):
    body = "# 조사 결과\n\n찾은 정보\n\n[출처](https://example.com/article)"
    request = parse_wiki_save_request(prompt, history=[
        {"role": "assistant", "content": body},
    ])
    assert request and request.content == body
    wiki = IrisWiki(docs_root=tmp_path / "docs", user_root=tmp_path / "wiki")
    paths = []
    for _ in range(3):
        result = save_answer_to_wiki(wiki, title=request.title, content=request.content)
        paths.append(result["path"])
        assert body in Path(result["path"]).read_text(encoding="utf-8")
    assert len(set(paths)) == 3


def check_new_research_still_reaches_agent(prompt):
    assert parse_wiki_save_request(prompt, history=[
        {"role": "assistant", "content": "unrelated previous answer"},
    ]) is None


def check_no_answer_does_not_invent_content():
    assert parse_wiki_save_request("이 내용 위키에 저장해줘") is None
    assert parse_wiki_save_request("이 내용 위키에 저장해줘", history=[
        {"role": "assistant", "content": "위키에 저장했습니다. 성공"},
    ]) is None


def check_pdf_attachment_import(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    pdf = tmp_path / "research.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 100 Td (Research evidence) Tj ET")
    page[NameObject("/Contents")] = stream
    writer.write(pdf)
    request = parse_wiki_save_request("이 PDF 위키에 저장해줘", [str(pdf)])
    assert request and request.from_attachment
    wiki = IrisWiki(docs_root=tmp_path / "docs", user_root=tmp_path / "wiki")
    result = import_to_wiki(wiki, source=request.source)
    saved = Path(result["path"]).read_text(encoding="utf-8")
    assert "Research evidence" in saved
    assert "research.pdf" in saved
    assert any(note.rel_path == result["rel_path"] for note in wiki.list_notes())


class WikiSaveFlowTests(unittest.TestCase):
    def test_answer_save(self):
        for prompt in (
            "방금 찾은 내용 위키에 저장해줘", "검색 결과를 위키에 저장해주세요",
            "이 내용을 위키에 저장해 줘", "직전 답변 위키에 기록해줘",
        ):
            with self.subTest(prompt=prompt), tempfile.TemporaryDirectory() as tmp:
                check_save_answer_with_sources(Path(tmp), prompt)

    def test_research_routing(self):
        for prompt in (
            "양자 컴퓨터 검색해서 위키에 저장해줘", "위키에 저장하는 방법 알려줘",
            "새 정보를 위키에 저장해줘",
        ):
            with self.subTest(prompt=prompt):
                check_new_research_still_reaches_agent(prompt)

    def test_missing_content(self):
        check_no_answer_does_not_invent_content()

    def test_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            check_pdf_attachment_import(Path(tmp))


if __name__ == "__main__":
    unittest.main()
