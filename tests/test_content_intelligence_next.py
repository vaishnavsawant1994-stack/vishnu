from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from types import SimpleNamespace

import pytest

from file_intelligence import ContentKind, FileIntelligenceEngine, LocalContentIndex
from file_intelligence.models import SourceReference, VishnuBlock, VishnuDocument
from file_intelligence.readers import ContentReadError
from knowledge.universal_store import UniversalKnowledgeStore
from projects.content_access import ProjectContentAccess
from projects.store import ProjectStore
from tools.content_intelligence import register as register_content_tools
from tools.registry import Risk


def _epub_bytes() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("OEBPS/chapter.xhtml", "<html><body><h1>Chapter</h1><p>EPUB revenue 42</p></body></html>")
    return payload.getvalue()


def _email_bytes(text: str = "Project is green.") -> bytes:
    return (
        "Subject: Project status\r\n"
        "From: a@example.com\r\n"
        "To: b@example.com\r\n"
        "MIME-Version: 1.0\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"{text}\r\n"
    ).encode("utf-8")


def _tar_bytes() -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        raw = b"TAR local content 73"
        info = tarfile.TarInfo("nested/report.txt")
        info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))
    return payload.getvalue()


def _pdf_form_bytes() -> bytes:
    from reportlab.pdfgen import canvas

    payload = io.BytesIO()
    pdf = canvas.Canvas(payload)
    pdf.drawString(72, 760, "Invoice form")
    pdf.acroForm.textfield(name="invoice_number", value="INV-1234", x=72, y=710, width=160, height=20)
    pdf.save()
    return payload.getvalue()


def test_layout_forms_tables_and_single_line_key_values():
    engine = FileIntelligenceEngine()
    doc = engine.extract(
        filename="invoice.txt",
        data=b"INVOICE\nInvoice No: 1234\n[x] Approved\n- Paid\n",
    )
    assert any(block.kind == "heading" and block.text == "INVOICE" for block in doc.blocks)
    assert any(block.kind == "key_value" and block.data["key"] == "Invoice No" for block in doc.blocks)
    assert any(block.kind == "form_field" and block.data["checked"] is True for block in doc.blocks)
    assert any(block.kind == "list_item" and block.text == "Paid" for block in doc.blocks)

    table = VishnuBlock(
        "table",
        "Customer | Alice",
        SourceReference(page=2, table=1),
        data={"rows": [["Field", "Value"], ["Customer", "Alice"]]},
    )
    from file_intelligence.layout import enrich_layout

    enriched = enrich_layout([table])
    normalized = next(block for block in enriched if block.kind == "table")
    assert normalized.data["column_count"] == 2
    assert normalized.data["row_count"] == 2
    assert any(
        block.kind == "key_value"
        and block.data.get("key") == "Customer"
        and block.source.page == 2
        for block in enriched
    )


def test_extended_formats_are_local_and_preserve_provenance():
    engine = FileIntelligenceEngine()

    mail = engine.extract(filename="status.eml", data=_email_bytes())
    assert mail.content_kind == ContentKind.EMAIL
    assert any(block.source.field == "subject" for block in mail.blocks)
    assert any("Project is green" in block.text and block.source.email_part for block in mail.blocks)

    book = engine.extract(filename="book.epub", data=_epub_bytes())
    assert book.content_kind == ContentKind.EBOOK
    assert any(block.source.member == "OEBPS/chapter.xhtml" for block in book.blocks)
    assert "EPUB revenue 42" in book.full_text

    code = engine.extract(filename="worker.py", data=b"def run():\n    return 42\n")
    assert code.content_kind == ContentKind.CODE
    assert any(block.kind == "code" and block.metadata.get("language_hint") == "py" for block in code.blocks)


def test_pdf_acroform_fields_and_tar_gzip_are_local():
    engine = FileIntelligenceEngine()
    pdf = engine.extract(filename="invoice.pdf", data=_pdf_form_bytes())
    form = next(block for block in pdf.blocks if block.kind == "form_field" and block.source.field == "invoice_number")
    assert form.data["value"] == "INV-1234"
    assert form.data["embedded_pdf_form"] is True

    tar_doc = engine.extract(filename="bundle.tar", data=_tar_bytes())
    assert "TAR local content 73" in tar_doc.full_text
    assert any(block.source.member == "nested/report.txt" for block in tar_doc.blocks)

    compressed = gzip.compress(b"GZIP local content 84")
    gz_doc = engine.extract(filename="note.txt.gz", data=compressed)
    assert "GZIP local content 84" in gz_doc.full_text
    assert any(block.source.member == "note.txt" for block in gz_doc.blocks)


def test_archive_traversal_is_rejected():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escape.txt", "blocked")
    with pytest.raises(ContentReadError):
        FileIntelligenceEngine().extract(filename="unsafe.zip", data=payload.getvalue())


def test_local_index_keeps_exact_source_and_strict_scope(tmp_path):
    index = LocalContentIndex(tmp_path / "content.sqlite3")
    one = VishnuDocument(
        "doc-a", "a.pdf", ContentKind.PDF, "application/pdf", "application/pdf", ".pdf", "aaa", 10,
        blocks=[VishnuBlock("paragraph", "secret revenue 42", SourceReference(page=7))],
    )
    two = VishnuDocument(
        "doc-b", "b.pdf", ContentKind.PDF, "application/pdf", "application/pdf", ".pdf", "bbb", 10,
        blocks=[VishnuBlock("paragraph", "secret revenue 99", SourceReference(page=9))],
    )
    index.index_document(one, scope_type="project", scope_id="project-a")
    index.index_document(two, scope_type="project", scope_id="project-b")

    hits = index.search("secret revenue", scope_type="project", scope_id="project-a")
    assert hits
    assert {hit["document_id"] for hit in hits} == {"doc-a"}
    assert hits[0]["citation"]["source"]["page"] == 7
    assert index.search("secret revenue", scope_type="project", scope_id="missing") == []


def test_project_content_access_indexes_broader_formats_without_cross_project_leak(tmp_path):
    store = ProjectStore(tmp_path / "projects.sqlite3")
    project_a = store.create(name="A")
    project_b = store.create(name="B")
    project_a = store.add_upload(
        project_a["id"], title="status.eml", media_type="message/rfc822", content=_email_bytes("Alpha secret 42")
    )
    project_b = store.add_upload(
        project_b["id"], title="status.eml", media_type="message/rfc822", content=_email_bytes("Beta secret 99")
    )
    file_a = next(item for item in project_a["files"] if item["title"] == "status.eml")
    file_b = next(item for item in project_b["files"] if item["title"] == "status.eml")

    access = ProjectContentAccess(store, ocr_provider=None)
    hits_a = access.search(project_a["id"], "secret")
    assert hits_a and {hit["document_id"] for hit in hits_a} == {file_a["id"]}
    assert all(hit["document_id"] != file_b["id"] for hit in hits_a)
    with pytest.raises(KeyError):
        access.read(project_a["id"], file_b["id"])


def test_universal_knowledge_ingestion_and_exact_search(tmp_path):
    store = UniversalKnowledgeStore(tmp_path / "knowledge.sqlite3", tmp_path / "objects")
    detail = store.ingest(filename="status.eml", data=_email_bytes("Knowledge exact phrase"), access_class="owner")
    assert detail["filename"] == "status.eml"
    hits = store.search_exact("Knowledge exact", access_classes={"owner"})
    assert hits
    assert hits[0]["document_id"] == detail["id"]
    assert hits[0]["citation"]["source"].get("email_part")


def test_knowledge_package_exports_universal_store_without_replacing_legacy_store():
    import knowledge.store as store_module
    from knowledge import KnowledgeStore, UniversalKnowledgeStore as ExportedUniversalKnowledgeStore

    assert KnowledgeStore is store_module.KnowledgeStore
    assert ExportedUniversalKnowledgeStore is UniversalKnowledgeStore


def test_agent_content_tools_are_typed_read_only_and_project_scoped(tmp_path):
    class Registry:
        def __init__(self):
            self.tools = {}

        def register(self, tool):
            self.tools[tool.name] = tool

    projects = ProjectStore(tmp_path / "projects.sqlite3")
    project = projects.create(name="Tool project")
    projects.add_upload(
        project["id"], title="notes.md", media_type="text/markdown", content=b"Agent searchable phrase"
    )

    registry = Registry()
    register_content_tools(registry, SimpleNamespace(data_dir=tmp_path))
    expected = {
        "search_project_content",
        "read_project_content",
        "extract_project_tables",
        "extract_project_forms",
        "search_knowledge_content",
    }
    assert expected.issubset(registry.tools)
    assert all(registry.tools[name].risk == Risk.READ_ONLY for name in expected)
    assert registry.tools["search_project_content"].input_schema["required"] == ["project_id", "query"]
    result = registry.tools["search_project_content"].handler({"project_id": project["id"], "query": "searchable"})
    assert result["project_id"] == project["id"]
    assert result["results"]
    assert result["content_is_untrusted"] is True
