import zipfile

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from content_creator.attribution import classify_attribution, isolate_attributed_text
from content_creator.corpus import assess_corpus
from content_creator.ingestion import content_hash, is_near_duplicate, read_source
from content_creator.voices import SourceRecord


def _write_docx(path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body><w:p><w:r><w:t>By Example Person. DOCX voice sample.</w:t></w:r></w:p></w:body>
    </w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def _write_pdf(path):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): writer._add_object(font)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 200 Td (By Example Person. PDF sample.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as handle:
        writer.write(handle)


def test_supported_source_types_normalize_stably(tmp_path):
    text = tmp_path / "sample.txt"
    html = tmp_path / "sample.html"
    docx = tmp_path / "sample.docx"
    pdf = tmp_path / "sample.pdf"
    transcript = tmp_path / "sample-transcript.txt"
    text.write_text("By Example Person. Text sample.", encoding="utf-8")
    html.write_text(
        "<title>Sample</title><main>By Example Person. HTML sample.</main>",
        encoding="utf-8",
    )
    transcript.write_text("Example: Transcript sample.", encoding="utf-8")
    _write_docx(docx)
    _write_pdf(pdf)

    extracted = [read_source(str(path))[2] for path in (text, html, docx, pdf, transcript)]
    assert all(extracted)
    assert content_hash(extracted[0]) == content_hash(read_source(str(text))[2])
    assert PdfReader(pdf).pages[0].extract_text()


def test_attribution_matrix_and_corpus_gaps():
    direct = classify_attribution("By Example Person. Words.", "Example Person", "text")
    interview = classify_attribution("Example: An answer.", "Example Person", "transcript")
    subject = classify_attribution(
        "A profile of Example Person.", "Example Person", "text"
    )
    uncertain = classify_attribution("Written by Someone Else.", "Example Person", "text")

    assert direct.classification == "directly_authored"
    assert interview.classification == "interview"
    assert subject.voice_weight == 0
    assert uncertain.needs_human_review

    record = SourceRecord(
        id="source-1",
        kind="text",
        locator="fixture",
        content_hash="sha256:x",
        title="Fixture",
        word_count=600,
        attribution=direct,
        approved_for_analysis=True,
        cache_path=".voice-cache/example/source-1.txt",
    )
    report = assess_corpus([record], ["general-text"])
    assert report["supported_packs"]["general-text"] == "medium"
    assert report["gaps"]
    assert is_near_duplicate("same words", ["same words"])


def test_analysis_text_removes_byline_and_isolates_target_speaker():
    direct = classify_attribution(
        "By Example Person. A direct opening.",
        "Example Person",
        "text",
    )
    direct_text, direct_scope = isolate_attributed_text(
        "By Example Person. A direct opening.",
        "Example Person",
        direct,
        "text",
    )
    interview = classify_attribution(
        "Host: What changed?\nExample: The boundary became visible.\n"
        "Host: Why?\nExample: We tested it.",
        "Example Person",
        "transcript",
    )
    interview_text, interview_scope = isolate_attributed_text(
        "Host: What changed?\nExample: The boundary became visible.\n"
        "Host: Why?\nExample: We tested it.",
        "Example Person",
        interview,
        "transcript",
    )

    assert direct_text == "A direct opening."
    assert direct_scope == "full-source-with-byline-removed"
    assert interview_text == "The boundary became visible.\n\nWe tested it."
    assert interview_scope == "speaker-turns-only"


def test_corpus_sufficiency_uses_attribution_weighted_analysis_words():
    interview = classify_attribution(
        "Example: An answer.",
        "Example Person",
        "transcript",
    )
    record = SourceRecord(
        id="source-1",
        kind="transcript",
        locator="fixture",
        content_hash="sha256:x",
        title="Fixture",
        word_count=1000,
        analysis_word_count=900,
        analysis_scope="speaker-turns-only",
        attribution=interview,
        approved_for_analysis=True,
        cache_path=".voice-cache/example/source-1.txt",
    )

    report = assess_corpus([record], ["general-text"])

    assert report["usable_word_count"] == 900
    assert report["attribution_weighted_word_count"] == 450
    assert not report["sufficient"]
    assert "attribution-weighted" in report["gaps"][0]
