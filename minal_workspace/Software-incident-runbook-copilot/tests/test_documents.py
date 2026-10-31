from pathlib import Path

import pytest

from incident_copilot.documents import chunk_document, clean_markdown, parse_markdown_document
from incident_copilot.models import SourceDocument


CORPUS = Path(__file__).parents[1] / "corpus"


def test_parse_all_corpus_markdown_has_valid_metadata_and_content() -> None:
    documents = [parse_markdown_document(path, CORPUS) for path in CORPUS.rglob("*.md")
                 if path.name != "README.md"]

    assert len(documents) == 18
    assert len({document.doc_id for document in documents}) == 18
    assert all(document.content and document.content_hash for document in documents)


def test_clean_markdown_preserves_headings_and_decodes_entities() -> None:
    cleaned = clean_markdown(
        "# Alert &amp; recovery\r\n<script>discard this</script>\r\nPage 1 of 2\r\n"
        "Keep <strong>the warning</strong>."
    )

    assert cleaned == "# Alert & recovery\n\nKeep the warning."


def test_parser_rejects_missing_required_metadata(tmp_path: Path) -> None:
    source = tmp_path / "bad.md"
    source.write_text("---\ndoc_id: BAD-1\n---\n# Missing fields\nText", encoding="utf-8")

    with pytest.raises(ValueError, match="missing metadata"):
        parse_markdown_document(source, tmp_path)


def test_chunking_keeps_section_boundaries_and_citation_metadata() -> None:
    source = CORPUS / "runbooks" / "RB-PAY-014-kafka-consumer-lag.md"
    document = parse_markdown_document(source, CORPUS)
    chunks = chunk_document(document, max_tokens=70, overlap_tokens=8,
                            token_counter=lambda text: len(text.split()))

    assert chunks
    assert all(chunk.doc_id == "RB-PAY-014" for chunk in chunks)
    assert all(chunk.citation.startswith("RB-PAY-014#") for chunk in chunks)
    assert all(chunk.service == "checkout-worker" for chunk in chunks)
    assert {chunk.section_path for chunk in chunks} >= {
        "Alert meaning",
        "Triage",
        "Recovery decision",
    }
    assert not any("## Triage" in chunk.content and "## Recovery decision" in chunk.content
                   for chunk in chunks)


def test_chunking_keeps_fenced_code_and_tables_intact() -> None:
    document = SourceDocument.from_parts(
        source_path="synthetic.md",
        metadata={"doc_id": "TEST-1", "service": "test", "environment": "production",
                  "version": 1, "status": "active", "owner": "test",
                  "last_reviewed": "2026-10-23", "source_type": "runbook"},
        title="Synthetic procedure",
        content=("# Synthetic procedure\n## Recovery\n\n"
                 "```text\nfirst line\n\nsecond line\n```\n\n"
                 "| signal | meaning |\n| --- | --- |\n| lag | backlog |\n"),
        content_hash="test-hash",
    )

    chunks = chunk_document(document, max_tokens=3, overlap_tokens=0,
                            token_counter=lambda text: len(text.split()))

    joined = "\n".join(chunk.content for chunk in chunks)
    assert "first line\n\nsecond line" in joined
    assert "| signal | meaning |\n| --- | --- |\n| lag | backlog |" in joined
