"""Extraction eval: run the real pipeline logic over every fixture with a truth file and report.

``python -m evals.run_eval`` (``make eval``) makes live OpenAI calls and costs money. It is a report with no
pass mark. ``EXTRACTION_MODEL=... make eval`` A/B-tests another extraction model.
"""

import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

from app.config import Settings
from app.llm.base import LLMError, LLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.pipeline.run import extract_tabular, plan_processing
from app.pipeline.store import RowDraft, build_rows
from evals.match import Score, load_truth, match

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
OUT_DIR = Path(__file__).resolve().parent / "out"
_KINDS = {".pdf": "pdf", ".csv": "csv", ".xlsx": "xlsx", ".html": "html", ".eml": "eml"}
HARBORLINE = "harborline"
HOLDING_GAINS = (Decimal("0.217"), Decimal("0.124"))  # Harborline "Unrealized G/L %" cells: not fund returns


@dataclass
class FileResult:
    name: str
    score: Score | None = None
    rows: list[RowDraft] = field(default_factory=list)
    extraction: dict | None = None
    seconds: float = 0.0
    error: str | None = None


def fixtures_with_truth() -> list[Path]:
    return sorted(_doc_for(p) for p in FIXTURES.glob("*/*.truth.json"))


def _doc_for(truth: Path) -> Path:
    stem = truth.name.removesuffix(".truth.json")
    return next(p for p in truth.parent.iterdir() if p.stem == stem and p.suffix in _KINDS)


def evaluate_file(path: Path, llm: LLMProvider) -> FileResult:
    """Real pipeline logic without a database: plan, extract, build rows, score."""
    result = FileResult(path.name)
    started = time.monotonic()
    try:
        data = path.read_bytes()
        kind = _KINDS.get(path.suffix.lower())
        plan = plan_processing(kind, data, path.name)
        if plan.route == "tabular":
            ex = extract_tabular(path.name, plan.tables, llm, [])
        elif plan.route == "pdf":
            ex = llm.extract(file_name=path.name, pdf=data, text=None, known_funds=[])
        elif plan.route == "text":
            ex = llm.extract(file_name=path.name, pdf=None, text=plan.text.pages[0], known_funds=[])
        else:
            result.error = f"{plan.route}: {plan.error or 'not extracted'}"
            return result
        result.extraction = ex.model_dump(mode="json")
        result.rows = build_rows(ex, ex.as_of_date)
        truth, partial = load_truth(path.with_suffix("").with_suffix(".truth.json"))
        result.score = match(truth, result.rows, partial=partial)
    except LLMError as exc:
        result.error = f"LLMError: {exc}"[:500]
    finally:
        result.seconds = time.monotonic() - started
    return result


def harborline_gain_leaks(results: list[FileResult]) -> list[RowDraft]:
    """Harborline holding gains (0.217, 0.124) that were extracted as a fund ``return``."""
    return [
        r
        for res in results
        if res.name.startswith(HARBORLINE)
        for r in res.rows
        if r.measure == "return" and any(abs(r.value - g) <= Decimal("0.00005") for g in HOLDING_GAINS)
    ]


def make_settings() -> Settings:
    """Settings, but the repo .env wins over the shell for the API key (the shell's copy may be stale)."""
    key = ""
    for env_file in (ROOT / ".env", ROOT / "backend" / ".env"):
        key = dotenv_values(env_file).get("OPENAI_API_KEY") or key
    return Settings(openai_api_key=key) if key else Settings()


class MeteredProvider(OpenAIProvider):
    """OpenAIProvider that totals the token usage the API reports."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.input_tokens = 0
        self.output_tokens = 0

    def _call(self, fn, **kwargs):
        resp = OpenAIProvider._call(fn, **kwargs)
        usage = getattr(resp, "usage", None)
        self.input_tokens += getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        return resp


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def report(results: list[FileResult], leaks: list[RowDraft], seconds: float, usage: tuple[int, int] | None) -> str:
    out = ["", "Per document", f"{'file':58} {'recall':>9} {'prec':>6} {'rows':>5} {'sec':>6}"]
    per_measure: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in results:
        if r.score is None:
            out.append(f"{r.name:58} ERROR {r.error}")
            continue
        s = r.score
        out.append(f"{r.name:58} {s.hits:>3}/{s.total:<5} {_pct(s.precision):>6} {s.got_count:>5} {r.seconds:>6.1f}")
        for t in s.misses:
            out.append(f"    MISS {t.entity} | {t.share_class} | {t.measure} {t.period_kind} {t.period_end} {t.value}")
        for g in s.extras[:5]:
            out.append(f"    EXTRA {g.entity} | {g.share_class} | {g.measure} {g.period_kind} {g.period_end} {g.value}")
        missed = {(t.measure, t.period_kind, t.period_end, t.entity, t.share_class) for t in s.misses}
        truth, _ = load_truth(next(p for p in FIXTURES.glob(f"*/{r.name.rsplit('.', 1)[0]}.truth.json")))
        for t in truth:
            per_measure[t.measure][1] += 1
            per_measure[t.measure][0] += (t.measure, t.period_kind, t.period_end, t.entity, t.share_class) not in missed
    out += ["", "Per measure (recall)", f"{'measure':20} {'hits':>10}"]
    for m, (h, n) in sorted(per_measure.items()):
        out.append(f"{m:20} {h:>4}/{n:<5} {h / n:.0%}")
    out += ["", f"Harborline holding gains read as fund return: {len(leaks)} (want 0)"]
    out += [f"    LEAK {r.entity} {r.period_kind} {r.period_end} {r.value}" for r in leaks]
    out.append(f"Total time: {seconds:.1f}s")
    if usage:
        out.append(f"Tokens (API-reported): input {usage[0]:,}, output {usage[1]:,} (no price table: cost not computed)")
    else:
        out.append("Tokens: not available")
    return "\n".join(out)


def main() -> int:
    settings = make_settings()
    llm = MeteredProvider(settings)
    print(f"extraction model: {settings.extraction_model}; mapping model: {settings.mapping_model}")
    OUT_DIR.mkdir(exist_ok=True)
    started = time.monotonic()
    results = []
    for path in fixtures_with_truth():
        print(f"extracting {path.name} ...", flush=True)
        res = evaluate_file(path, llm)
        results.append(res)
        (OUT_DIR / f"{path.name}.json").write_text(
            json.dumps(
                {
                    "file": path.name, "error": res.error, "seconds": res.seconds,
                    "extraction": res.extraction,
                    "rows": [{**d.__dict__, "value": str(d.value), "period_end": d.period_end.isoformat()} for d in res.rows],
                },
                indent=2,
            )
        )
    elapsed = time.monotonic() - started
    print(report(results, harborline_gain_leaks(results), elapsed, (llm.input_tokens, llm.output_tokens)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
