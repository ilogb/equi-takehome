from pathlib import Path

import pytest

from app.pipeline.detect import is_scanned, kind_for
from app.pipeline.text import TooManyPages, clean_html, eml_body, load_text

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures"


@pytest.mark.parametrize(
    ("mime", "name", "expected"),
    [
        ("application/pdf", "a.pdf", "pdf"),
        ("text/csv", "a.csv", "csv"),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "a.xlsx", "xlsx"),
        ("text/html", "a.html", "html"),
        ("message/rfc822", "a.eml", "eml"),
        ("application/octet-stream", "x.eml", "eml"),
        ("application/vnd.google-apps.spreadsheet", "sheet", None),
        ("application/vnd.google-apps.spreadsheet", "sheet.csv", None),
        ("application/vnd.google-apps.document", "memo.pdf", None),
        ("image/png", "a.png", None),
        ("application/octet-stream", "Report.PDF", "pdf"),
        ("text/plain", "prices.csv", "csv"),
        ("application/vnd.ms-excel", "prices.csv", "csv"),
        ("application/octet-stream", "book.xlsx", "xlsx"),
        ("text/plain", "page.htm", "html"),
        ("application/octet-stream", "page.html", "html"),
        ("text/csv; charset=utf-8", "a", "csv"),
        ("application/octet-stream", "notes.txt", None),
        ("application/octet-stream", "noext", None),
    ],
)
def test_kind_for(mime, name, expected):
    assert kind_for(mime, name) == expected


def test_fixture_pdfs_not_scanned():
    pdfs = sorted(FIXTURES.rglob("*.pdf"))
    assert pdfs
    for pdf in pdfs:
        assert is_scanned(load_text(pdf.read_bytes(), "pdf").pages) is False, pdf.name


def test_image_only_pdf_scanned():
    pdf = ROOT / "docs/03-implementation-plan/spike/scanned.pdf"
    assert is_scanned(load_text(pdf.read_bytes(), "pdf").pages) is True


def test_is_scanned_threshold():
    assert is_scanned(["", "x" * 30]) is False  # exactly half is not "more than half"
    assert is_scanned(["", "short", "x" * 30]) is True


def test_too_many_pages(monkeypatch):
    monkeypatch.setattr("app.pipeline.text.MAX_PDF_PAGES", 0)
    pdf = next(FIXTURES.rglob("*.pdf"))
    with pytest.raises(TooManyPages):
        load_text(pdf.read_bytes(), "pdf")


def test_larchmont_text_not_duplicated():
    raw = (FIXTURES / "synthetic/larchmont-quay_q3-letter_fwd_2026-10.eml").read_bytes()
    html = eml_body(raw)
    assert html.count("Multi-Strategy") == 2  # one table row + one prose mention
    cleaned = clean_html(html)
    assert cleaned.count("Multi-Strategy") == 2
    assert any(line.startswith("Multi-Strategy | ") for line in cleaned.splitlines())


def test_kestrel_prefers_html_part():
    raw = (FIXTURES / "synthetic/kestrel-ridge_investor-update_2026-01.eml").read_bytes()
    assert "1.90%" in load_text(raw, "eml").pages[0]


def test_clean_html_drops_script_and_style():
    out = clean_html("<style>p{}</style><script>x()</script><p>hi</p>")
    assert out == "hi"
