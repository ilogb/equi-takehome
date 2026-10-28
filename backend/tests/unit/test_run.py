from datetime import date

import pytest

from app.llm.fake import FakeLLM
from app.models import FileStatus
from app.pipeline.run import (
    csv_head_tail,
    extract_tabular,
    metadata_text,
    plan_processing,
)
from app.pipeline.schema import DocumentExtraction
from app.pipeline.tabular import RawTable, apply_mapping, read_tables
from app.pipeline.text import clean_html, load_text
from tests.fakes import FIXTURES, ROOT, FakeDriveSource

RECORDED = ROOT / "backend/tests/recorded"
SCANNED = ROOT / "docs/03-implementation-plan/spike/scanned.pdf"


def test_fake_source_serves_fixtures():
    src = FakeDriveSource()
    assert src.download("man-ahl_factsheet_2026-08.pdf").startswith(b"%PDF")
    assert src.downloads == ["man-ahl_factsheet_2026-08.pdf"]


def test_png_unsupported():
    plan = plan_processing(None, b"\x89PNG")
    assert plan.route == "unsupported"


def test_too_many_pages(monkeypatch):
    monkeypatch.setattr("app.pipeline.text.MAX_PDF_PAGES", 0)
    plan = plan_processing("pdf", FakeDriveSource().download("man-ahl_factsheet_2026-08.pdf"))
    assert plan.route == "unsupported"
    assert plan.error == "PDF has more than 50 pages"


def test_scanned_pdf():
    plan = plan_processing("pdf", SCANNED.read_bytes())
    assert plan.route == "scanned"
    assert plan.text is not None and plan.text.pages


def test_man_ahl_extract_pdf():
    plan = plan_processing("pdf", FakeDriveSource().download("man-ahl_factsheet_2026-08.pdf"))
    assert plan.route == "pdf"
    assert plan.text is not None


def test_kestrel_extract_text():
    plan = plan_processing("eml", FakeDriveSource().download("kestrel-ridge_investor-update_2026-01.eml"))
    assert plan.route == "text"
    assert "1.90%" in plan.text.pages[0]


def test_alderbank_tabular():
    data = FakeDriveSource().download("alderbank_performance-summary_2026-09.csv")
    plan = plan_processing("csv", data, "alderbank_performance-summary_2026-09.csv")
    assert plan.route == "tabular"
    assert len(plan.tables) == 1


def test_garbage_pdf_fails_readably():
    plan = plan_processing("pdf", b"this is not a pdf at all")
    assert plan.route == "failed"
    assert plan.error and plan.error.startswith("Could not read file")


def test_garbage_xlsx_fails_readably():
    assert plan_processing("xlsx", b"not a zip").route == "failed"


def test_csv_head_tail_slicing():
    rows = [[str(i)] for i in range(100)]
    head, tail = csv_head_tail(rows)
    assert head == rows[:20] and tail == rows[-5:]
    blank = [[""]] * 3 + rows
    head, tail = csv_head_tail(blank)  # skip = 3 leading blank rows
    assert len(head) == 23 and tail == blank[-5:]


def test_csv_head_tail_short_table_has_no_overlap():
    rows = [[str(i)] for i in range(22)]
    head, tail = csv_head_tail(rows)
    assert head == rows[:20] and tail == rows[20:]
    assert csv_head_tail(rows[:10]) == (rows[:10], [])


class RecordingLLM(FakeLLM):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.mapped: list[tuple[str, int, int]] = []
        self.extracted: list[dict] = []

    def map_table(self, *, name, head, tail):
        self.mapped.append((name, len(head), len(tail)))
        return super().map_table(name=name, head=head, tail=tail)

    def extract(self, *, file_name, pdf=None, text=None, known_funds=()):
        self.extracted.append({"file_name": file_name, "text": text})
        return DocumentExtraction(
            doc_type="performance_report", manager="Alderbank", funds=[], as_of_date=date(2026, 9, 30),
            currency=None, summary="s", tags=[], tables=[], rows=[],
        )


def test_extract_tabular_csv_29_rows():
    name = "alderbank_performance-summary_2026-09.csv"
    tables = read_tables((FIXTURES / "synthetic" / name).read_bytes(), "csv", name)
    llm = RecordingLLM(RECORDED)
    ex = extract_tabular(name, tables, llm, [])
    assert len(llm.mapped) == 1 and llm.mapped[0][0] == name
    assert len(ex.rows) == 29
    assert len(ex.tables) == 1 and ex.tables[0].rows[0] == tables[0].cells[0]
    assert ex.as_of_date == date(2026, 9, 30)
    assert ex.rows == apply_mapping(tables[0], llm.map_table(name=name, head=[], tail=[]), 0)
    first40 = llm.extracted[0]["text"].splitlines()
    assert len(first40) == min(40, len(tables[0].cells))


def test_metadata_text_first_40_lines():
    t = RawTable("x", [[str(i), "a"] for i in range(100)])
    assert metadata_text([t]).splitlines()[-1] == "39,a"


def test_nul_stripped_from_text():
    assert "\x00" not in clean_html("<p>a\x00b</p>")
    pdf = FakeDriveSource().download("man-ahl_factsheet_2026-08.pdf")
    assert all("\x00" not in p for p in load_text(pdf, "pdf").pages)
    eml = b"Subject: x\r\nContent-Type: text/plain\r\n\r\nhello\x00world\r\n"
    assert load_text(eml, "eml").pages == ["helloworld"]
    assert load_text(b"<p>h\x00i</p>", "html").pages == ["hi"]


def test_status_enum_values_used():
    assert FileStatus.scanned_no_text.value == "scanned_no_text"


@pytest.mark.parametrize("bad", [b"", b"%PDF-1.4 garbage"])
def test_more_garbage_pdfs(bad):
    assert plan_processing("pdf", bad).route == "failed"
