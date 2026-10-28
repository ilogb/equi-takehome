import json
from datetime import date
from decimal import Decimal

from app.llm.fake import FakeLLM
from app.pipeline.schema import DocumentExtraction
from evals.match import Got, TruthRow, load_truth, match
from evals.run_eval import FIXTURES, evaluate_file, harborline_gain_leaks


def truth(entity="Fundsmith Equity Fund", share_class="T Class Acc", value="-0.005", end=date(2026, 1, 31)):
    return TruthRow(entity, share_class, "return", "month", end, Decimal(value))


def got(entity="Fundsmith Equity", share_class="T Class EUR Acc", value="-0.005", end=date(2026, 1, 31), **kw):
    return Got(entity, share_class, kw.get("measure", "return"), kw.get("period_kind", "month"), end, Decimal(value))


def test_containment_matches_fundsmith_names():
    s = match([truth()], [got()])
    assert (s.hits, s.recall, s.misses) == (1, 1.0, [])


def test_containment_rejects_other_fund_and_class():
    assert match([truth()], [got(entity="Fundsmith Emerging")]).hits == 0
    assert match([truth()], [got(share_class="I Acc")]).hits == 0


def test_value_tolerance():
    assert match([truth()], [got(value="-0.00504")]).hits == 1
    assert match([truth()], [got(value="-0.0051")]).hits == 0


def test_period_end_snapped_but_measure_and_kind_exact():
    assert match([truth()], [got(end=date(2026, 1, 28))]).hits == 1
    assert match([truth()], [got(measure="benchmark_return")]).hits == 0
    assert match([truth()], [got(period_kind="ytd")]).hits == 0


def test_partial_has_no_precision():
    extra = got(entity="Other Fund", share_class=None)
    assert match([truth()], [got(), extra], partial=True).precision is None
    full = match([truth()], [got(), extra])
    assert full.precision == 0.5 and len(full.extras) == 1


def test_load_truth_reads_partial_flag():
    rows, partial = load_truth(FIXTURES / "real" / "man-ahl_factsheet_2026-08.truth.json")
    assert partial and rows[0].value == Decimal("0.0842") and rows[0].period_end == date(2026, 1, 31)


def _recorded(tmp_path, value_for_gain):
    row = dict(
        entity="Calder Family Office LLC", entity_kind="account", share_class=None, measure="account_return",
        period_kind="month", period_end="2026-09-30", value_as_written="1.62%", unit_hint="percent",
        currency=None, benchmark_name=None, table_index=None, row_index=None, col_index=None,
    )
    leak = dict(row, entity="Man AHL Diversified", entity_kind="fund", measure="return",
                value_as_written=value_for_gain, share_class="Class DN USD")
    ex = dict(doc_type="statement", manager="Harborline", funds=[], as_of_date="2026-09-30", currency="USD",
              summary="s", tags=[], tables=[], rows=[row, leak])
    DocumentExtraction.model_validate(ex)
    (tmp_path / "harborline-custody_account-statement_2026-09.pdf.json").write_text(json.dumps(ex))
    return FakeLLM(tmp_path)


def test_dry_run_scores_and_flags_harborline_leak(tmp_path):
    llm = _recorded(tmp_path, "21.7%")
    result = evaluate_file(FIXTURES / "synthetic" / "harborline-custody_account-statement_2026-09.pdf", llm)
    assert result.error is None and result.score.hits == 1 and result.score.total == 4
    assert result.score.precision is not None
    assert len(harborline_gain_leaks([result])) == 1
    assert [d.value for d in result.rows][1] == Decimal("0.217")


def test_dry_run_clean_has_no_leak(tmp_path):
    llm = _recorded(tmp_path, "5%")
    result = evaluate_file(FIXTURES / "synthetic" / "harborline-custody_account-statement_2026-09.pdf", llm)
    assert harborline_gain_leaks([result]) == []


def test_every_truth_file_has_a_document_and_report_renders(tmp_path):
    from evals.run_eval import fixtures_with_truth, report

    assert len(fixtures_with_truth()) == 8
    llm = _recorded(tmp_path, "21.7%")
    res = evaluate_file(FIXTURES / "synthetic" / "harborline-custody_account-statement_2026-09.pdf", llm)
    res.usage = {'gpt-6.1-sol': (1_000_000, 100_000)}
    text = report([res], harborline_gain_leaks([res]), 1.0)
    assert "account_return" in text and "LEAK" in text and "1/4" in text
    assert "$3.0000" in text


def test_got_row_satisfies_at_most_one_truth_row():
    a, b = truth(share_class="A Acc"), truth(share_class="I Acc")
    assert match([a, b], [got(share_class=None)]).hits == 1


def test_exact_share_class_preferred_over_blank():
    a = truth(share_class="A Acc")
    s = match([a, truth(share_class=None)], [got(share_class=None), got(share_class="A Acc")])
    assert s.hits == 2


def test_all_noise_entity_matches_nothing():
    assert match([truth(entity="Fund")], [got(entity="Fundsmith Equity")]).hits == 0
    assert match([truth()], [got(entity="Fund")]).hits == 0


def test_estimate_cost_arithmetic():
    from evals.run_eval import estimate_cost

    assert estimate_cost({"gpt-6.1-sol": (1_000_000, 100_000)}) == Decimal(3)
    assert estimate_cost({"gpt-6.1-terra": (500_000, 200_000), "text-embedding-3-small": (1_000_000, 0)}) == Decimal("1.52")
    assert estimate_cost({"mystery": (1, 1)}) is None


def test_exception_in_one_fixture_is_an_error_row_not_a_crash(tmp_path):
    class Boom(FakeLLM):
        def extract(self, **kw):
            raise ValueError("bad pdf")

    res = evaluate_file(FIXTURES / "synthetic" / "harborline-custody_account-statement_2026-09.pdf", Boom(tmp_path))
    assert res.score is None and res.error.startswith("ValueError: bad pdf")
    from evals.run_eval import report

    assert "ERROR ValueError" in report([res], [], 1.0)
