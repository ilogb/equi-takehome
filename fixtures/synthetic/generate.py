"""Generate the synthetic test documents in this folder, with expected values.

Every manager, fund, person and email domain here is fictional. The files fill
gaps in the real corpus: only one real CSV (prices, not returns) and no real
emailed fund updates. Each document has deliberate traps, listed in its
`.truth.json` under "traps".

Deterministic: rerunning rewrites byte-identical files.

    python3 fixtures/synthetic/generate.py
"""

from __future__ import annotations

import csv
import io
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

OUT = Path(__file__).parent

MONTH_ENDS = [
    "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31",
    "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30",
]
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
MINUS = "−"  # typographic minus, as pasted from Word or a web page


def frac(pct: str) -> Decimal:
    """'2.37' (percent) -> Decimal('0.0237') (fraction)."""
    return Decimal(pct) / 100


def compound(returns: list[Decimal]) -> Decimal:
    """Chain-link monthly returns, rounded to the 2dp percent a document prints."""
    total = Decimal(1)
    for r in returns:
        total *= 1 + r
    return ((total - 1) * 100).quantize(Decimal("0.01"), ROUND_HALF_UP) / 100


def fmt_pct(r: Decimal, negative_style: str = "-") -> str:
    """Fraction -> printed percent: '1.05%', '(0.84%)', '−0.45%' or '-0.45%'."""
    text = f"{abs(r) * 100:.2f}%"
    if r >= 0:
        return text
    if negative_style == "parens":
        return f"({text})"
    return f"{negative_style}{text}"


def obs(fund, metric, period_kind, period_end, value, *, share_class=None,
        benchmark_name=None, currency=None, unit="fraction", where=None):
    return {
        "fund": fund,
        "share_class": share_class,
        "metric": metric,
        "period_kind": period_kind,
        "period_end": period_end,
        "value": str(value),
        "unit": unit,
        "currency": currency,
        "benchmark_name": benchmark_name,
        "where": where,
    }


def write_truth(name: str, manager: str, as_of: str, doc_type: str,
                observations: list[dict], traps: list[str]) -> None:
    truth = {
        "file": name,
        "synthetic": True,
        "manager": manager,
        "doc_type": doc_type,
        "as_of_date": as_of,
        "observations": observations,
        "traps": traps,
    }
    path = OUT / name.rsplit(".", 1)[0]
    path.with_suffix(".truth.json").write_text(json.dumps(truth, indent=2) + "\n")


def write_bytes(name: str, text: str, *, bom: bool = False, crlf: bool = False) -> None:
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    data = text.encode("utf-8")
    (OUT / name).write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


# --------------------------------------------------------------------------
# 1. Long-format CSV: one row per fund-month, percent written as plain numbers.
# --------------------------------------------------------------------------

def northwind_csv() -> None:
    name = "northwind-capital_monthly-returns_2026-09.csv"
    macro = "Northwind Global Macro Fund, L.P."
    credit = "Northwind Credit Opportunities Fund"
    series = {
        macro: ("Founders", "HFRI Macro (Total) Index",
                ["2.37", "-1.12", "0.85", "1.46", "-0.38", "0.92", "1.73", "-2.05", "0.61"],
                ["1.10", "-0.45", "0.30", "0.88", "0.12", "0.40", "0.95", "-0.80", "0.25"]),
        credit: ("Class A", "ICE BofA US High Yield Index",
                 ["0.94", "0.71", "-0.22", "0.58", None, "0.66", "0.83", "0.47", "0.52"],
                 ["1.02", "0.35", "-0.61", "0.79", "0.20", "0.94", "0.58", "0.36", "0.71"]),
    }
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Fund", "Share Class", "Period", "Net Return %", "Benchmark", "Benchmark Return %"])
    observations = []
    for fund, (share_class, bench, rets, bench_rets) in series.items():
        for i, month_end in enumerate(MONTH_ENDS):
            # Trap: the July row spells the macro fund differently.
            written_name = "Northwind Global Macro Fund LP" if (fund == macro and i == 6) else fund
            ret = rets[i]
            w.writerow([written_name, share_class, month_end, ret or "", bench, bench_rets[i]])
            if ret is not None:
                observations.append(obs(fund, "return", "month", month_end, frac(ret),
                                        share_class=share_class))
            observations.append(obs(fund, "benchmark_return", "month", month_end,
                                    frac(bench_rets[i]), share_class=share_class,
                                    benchmark_name=bench))
    write_bytes(name, buf.getvalue(), crlf=True)
    write_truth(name, "Northwind Capital", "2026-09-30", "performance_report", observations, [
        "Returns are percent written as plain numbers under a '%' header: 2.37 means 0.0237.",
        "July row names the macro fund 'Northwind Global Macro Fund LP'; it is the same fund.",
        "Credit fund May 2026 return is blank: no observation, not zero. Its benchmark row still counts.",
        "CRLF line endings, as exported from Excel.",
    ])


# --------------------------------------------------------------------------
# 2. Wide-format CSV: preamble rows, months as columns, two share classes,
#    mixed negative styles, BOM, a YTD column and a footnote.
# --------------------------------------------------------------------------

def alderbank_csv() -> None:
    name = "alderbank_performance-summary_2026-09.csv"
    euro = "Alderbank European Equity Fund"
    asia = "Alderbank Asia Income Fund"
    rows = [
        (euro, "A EUR Acc", "EUR", "parens",
         ["3.12", "-0.84", "1.05", "2.40", "-1.67", "0.33", "1.98", "-2.21", "0.74"]),
        (euro, "I EUR Acc", "EUR", "parens",
         ["3.21", "-0.76", "1.13", "2.49", "-1.59", "0.41", "2.06", "-2.13", "0.82"]),
        (asia, "A USD Dist", "USD", MINUS,
         ["-0.45", "1.36", "2.08", "-0.92", "0.57", "1.74", "-1.18", "0.66", None]),
    ]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    width = 2 + len(MONTH_LABELS) + 1
    w.writerow(["Alderbank Asset Management - Monthly Performance Summary"] + [""] * (width - 1))
    w.writerow(["As of 30 September 2026"] + [""] * (width - 1))
    w.writerow([""] * width)
    w.writerow(["Fund", "Class"] + [f"{m}-26" for m in MONTH_LABELS] + ["YTD"])
    observations = []
    for fund, share_class, ccy, neg, rets in rows:
        fracs = [frac(r) if r is not None else None for r in rets]
        cells = [fmt_pct(f, neg) if f is not None else "n/a" for f in fracs]
        published = [f for f in fracs if f is not None]
        ytd = compound(published)
        ytd_cell = fmt_pct(ytd, neg) + ("*" if None in fracs else "")
        w.writerow([fund, share_class] + cells + [ytd_cell])
        for month_end, f in zip(MONTH_ENDS, fracs):
            if f is not None:
                observations.append(obs(fund, "return", "month", month_end, f,
                                        share_class=share_class, currency=ccy))
        ytd_end = MONTH_ENDS[len(published) - 1]
        observations.append(obs(fund, "return", "ytd", ytd_end, ytd,
                                share_class=share_class, currency=ccy))
    w.writerow([""] * width)
    w.writerow(["* Asia Income Fund YTD to 31 August 2026; September figure not yet published."]
               + [""] * (width - 1))
    w.writerow(["Source: Alderbank. Returns net of fees in share class currency. "
                "Past performance is not a guide to future returns. Synthetic test data."]
               + [""] * (width - 1))
    write_bytes(name, buf.getvalue(), bom=True, crlf=True)
    write_truth(name, "Alderbank Asset Management", "2026-09-30", "performance_report",
                observations, [
        "Three preamble rows before the real header; two footnote rows after the data.",
        "Wide layout: months are columns 'Jan-26'..'Sep-26'.",
        "Two share classes of one fund: separate series, one fund.",
        "Negatives as '(0.84%)' for the European fund and '−0.45%' (U+2212) for Asia.",
        "Asia September is 'n/a': no observation. Its YTD ends 31 Aug, per the asterisk footnote.",
        "UTF-8 BOM and CRLF line endings.",
    ])


# --------------------------------------------------------------------------
# 3. January investor update email: multipart/alternative, numbers in prose
#    and in a small HTML table; gross vs net trap.
# --------------------------------------------------------------------------

KESTREL_TEXT = """\
Dear Investors,

Kestrel Ridge Long/Short Equity Fund returned +1.90% net in January 2026
(+2.30% gross), compared with +1.10% for the MSCI World Index.

Gross exposure ended the month at 168% and net exposure at 42%. Fund assets
were $612m at 31 January.

For the 2025 calendar year the fund returned +14.6% net.

Best regards,
Mara Ellison
Investor Relations, Kestrel Ridge Partners

This message is synthetic test data. Kestrel Ridge Partners is fictional.
"""

KESTREL_HTML = """\
<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222">
<p>Dear Investors,</p>
<p><b>Kestrel Ridge Long/Short Equity Fund</b> returned <b>+1.90% net</b> in
January 2026 (+2.30% gross), compared with +1.10% for the MSCI World Index.</p>
<table cellpadding="6" style="border-collapse:collapse;border:1px solid #ccc">
<tr style="background:#f2f2f2"><th align="left">Period</th><th>Fund (net)</th><th>MSCI World</th></tr>
<tr><td>January 2026</td><td align="right">1.90%</td><td align="right">1.10%</td></tr>
<tr><td>Calendar year 2025</td><td align="right">14.60%</td><td align="right">&ndash;</td></tr>
</table>
<p>Gross exposure ended the month at 168% and net exposure at 42%. Fund assets
were $612m at 31 January.</p>
<p>Best regards,<br>Mara Ellison<br>Investor Relations, Kestrel Ridge Partners</p>
<p style="font-size:11px;color:#888">This message is synthetic test data.
Kestrel Ridge Partners is fictional.</p>
</body></html>
"""


def kestrel_eml() -> None:
    name = "kestrel-ridge_investor-update_2026-01.eml"
    boundary = "=_kestrel_boundary_0001"
    eml = f"""\
From: Kestrel Ridge Investor Relations <ir@kestrelridge.example>
To: allocations@allocator.example
Subject: Kestrel Ridge L/S Equity - January 2026 update
Date: Wed, 04 Feb 2026 09:15:00 -0500
Message-ID: <jan2026-update@kestrelridge.example>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="{boundary}"

--{boundary}
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 8bit

{KESTREL_TEXT}
--{boundary}
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: 8bit

{KESTREL_HTML}
--{boundary}--
"""
    write_bytes(name, eml, crlf=True)
    fund = "Kestrel Ridge Long/Short Equity Fund"
    write_truth(name, "Kestrel Ridge Partners", "2026-01-31", "investor_letter", [
        obs(fund, "return", "month", "2026-01-31", frac("1.90")),
        obs(fund, "benchmark_return", "month", "2026-01-31", frac("1.10"),
            benchmark_name="MSCI World Index"),
        obs(fund, "return", "1y", "2025-12-31", frac("14.6")),
        obs(fund, "aum", "other", "2026-01-31", Decimal("612000000"),
            unit="currency", currency="USD"),
    ], [
        "Net 1.90% is the return; gross 2.30% must not be stored as the return.",
        "Exposure figures (168%, 42%) are percentages but not returns.",
        "'$612m' is AUM in USD: 612000000.",
        "'Calendar year 2025' is a 1y period ending 2025-12-31.",
        "Same numbers appear in the text/plain and text/html parts: extract once.",
    ])


# --------------------------------------------------------------------------
# 4. Forwarded quarterly letter: HTML-only, template-style nested tables,
#    a full 2026 monthly table, QTD/YTD, and a bps figure that is not a return.
# --------------------------------------------------------------------------

def larchmont_eml() -> None:
    name = "larchmont-quay_q3-letter_fwd_2026-10.eml"
    ms = "Larchmont Quay Multi-Strategy Fund"
    rv = "Larchmont Quay Relative Value Fund"
    ms_rets = [frac(r) for r in ["-0.60", "1.15", "0.42", "0.88", "1.31", "-0.27", "0.95", "0.36", "1.02"]]
    rv_rets = [frac(r) for r in ["0.44", "-0.12", "0.51"]]  # Jul, Aug, Sep only (launched 1 July)
    ms_qtd, ms_ytd = compound(ms_rets[6:]), compound(ms_rets)
    rv_qtd = compound(rv_rets)

    def cell(r: Decimal) -> str:
        text = fmt_pct(r, MINUS)
        colour = "#b00020" if r < 0 else "#222"
        return f'<td align="right" style="padding:4px 8px;color:{colour}">{text}</td>'

    month_head = "".join(f'<th style="padding:4px 8px">{m}</th>' for m in MONTH_LABELS)
    ms_cells = "".join(cell(r) for r in ms_rets)
    rv_cells = '<td align="right" style="padding:4px 8px">&ndash;</td>' * 6 + "".join(cell(r) for r in rv_rets)

    html = f"""\
<html><body style="margin:0;background:#eeeeee">
<div style="font-family:Helvetica,Arial,sans-serif;font-size:13px">
<p>Sharing for the IC pack &mdash; see their table below. RV fund is new this quarter.</p>
<p>Dana</p>
<p>---------- Forwarded message ---------<br>
From: Larchmont Quay Capital &lt;ir@larchmontquay.example&gt;<br>
Date: Tue, 14 Oct 2026 at 08:02<br>
Subject: Larchmont Quay &mdash; Q3 2026 Investor Letter<br>
To: Dana Whitfield &lt;dana@allocator.example&gt;</p>
<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff">
<tr><td style="padding:24px;font-size:20px;color:#0b3d5c">Q3 2026 Investor Letter</td></tr>
<tr><td style="padding:0 24px 12px 24px">
<p>The Multi-Strategy Fund returned {fmt_pct(ms_qtd, MINUS)} in the third quarter,
bringing year-to-date performance to {fmt_pct(ms_ytd, MINUS)}. The Relative Value
Fund, launched on 1 July, returned {fmt_pct(rv_qtd, MINUS)} for its first quarter,
ahead of its cash-plus hurdle by 85 bps.</p>
</td></tr>
<tr><td style="padding:0 24px">
<table cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;font-size:12px">
<tr style="background:#0b3d5c;color:#ffffff"><th style="padding:4px 8px" align="left">2026 (net, %)</th>{month_head}<th style="padding:4px 8px">QTD</th><th style="padding:4px 8px">YTD</th></tr>
<tr><td style="padding:4px 8px">Multi-Strategy</td>{ms_cells}{cell(ms_qtd)}{cell(ms_ytd)}</tr>
<tr><td style="padding:4px 8px">Relative Value</td>{rv_cells}{cell(rv_qtd)}<td align="right" style="padding:4px 8px">n/m</td></tr>
</table>
</td></tr>
<tr><td style="padding:16px 24px;font-size:10px;color:#888">Returns net of all fees. Synthetic
test data; Larchmont Quay Capital is fictional.</td></tr>
</table>
</td></tr></table>
</div>
</body></html>
"""
    eml = f"""\
From: Dana Whitfield <dana@allocator.example>
To: research@allocator.example
Subject: Fwd: Larchmont Quay - Q3 2026 Investor Letter
Date: Wed, 15 Oct 2026 10:41:00 -0400
Message-ID: <fwd-lq-q3@allocator.example>
MIME-Version: 1.0
Content-Type: text/html; charset="utf-8"
Content-Transfer-Encoding: 8bit

{html}"""
    write_bytes(name, eml, crlf=True)
    observations = [obs(ms, "return", "month", m, r) for m, r in zip(MONTH_ENDS, ms_rets)]
    observations += [
        obs(ms, "return", "qtd", "2026-09-30", ms_qtd),
        obs(ms, "return", "ytd", "2026-09-30", ms_ytd),
    ]
    observations += [obs(rv, "return", "month", m, r) for m, r in zip(MONTH_ENDS[6:], rv_rets)]
    observations.append(obs(rv, "return", "qtd", "2026-09-30", rv_qtd))
    write_truth(name, "Larchmont Quay Capital", "2026-09-30", "investor_letter", observations, [
        "Forwarded: the sender is the allocator, the manager is Larchmont Quay.",
        "HTML-only, nested template tables; negatives use U+2212 and are styled red.",
        "Relative Value launched 1 July: Jan-Jun cells are dashes, not zeros; its YTD is 'n/m'.",
        "'85 bps' is excess over a hurdle, not a return.",
        "QTD/YTD appear in both the prose and the table: extract once.",
    ])


if __name__ == "__main__":
    northwind_csv()
    alderbank_csv()
    kestrel_eml()
    larchmont_eml()
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir() if p.name != "generate.py")))
