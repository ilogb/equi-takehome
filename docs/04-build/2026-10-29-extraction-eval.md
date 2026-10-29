# Extraction eval results (2026-10-29)

`make eval` run on 2026-10-29: extraction model `gpt-6.1-sol`, mapping model `gpt-6.1-terra`,
8 fixtures with hand-checked truth files.

## Summary

- **Recall: 108 of 108 expected values found (100%)**, across every document and every measure.
- **No holding gains leaked as fund returns** (the Harborline trap: 0, want 0).
- Precision is 100% on every fully listed file except the Harborline custody statement (57%, see below).
- 443 s in total; 72,781 input and 61,850 output tokens; about **$0.76** at list prices.

## Per document

| File | Recall | Precision | Rows | Seconds | Est. cost |
|---|---|---|---|---|---|
| fundsmith_factsheet_2026-01.pdf | 3/3 | n/a (partial truth) | 262 | 166.1 | $0.2863 |
| man-ahl_factsheet_2026-08.pdf | 9/9 | n/a (partial truth) | 158 | 108.4 | $0.2252 |
| uvic-pension_performance-report_2026-07.pdf | 9/9 | n/a (partial truth) | 76 | 44.2 | $0.0801 |
| alderbank_performance-summary_2026-09.csv | 29/29 | 100% | 29 | 32.4 | $0.0424 |
| harborline-custody_account-statement_2026-09.pdf | 4/4 | 57% | 7 | 21.6 | $0.0253 |
| kestrel-ridge_investor-update_2026-01.eml | 4/4 | 100% | 4 | 13.0 | $0.0125 |
| larchmont-quay_q3-letter_fwd_2026-10.eml | 15/15 | 100% | 15 | 17.6 | $0.0260 |
| northwind-capital_monthly-returns_2026-09.csv | 35/35 | 100% | 35 | 39.6 | $0.0602 |

## Per measure (recall)

| Measure | Hits |
|---|---|
| account_return | 2/2 (100%) |
| account_value | 2/2 (100%) |
| aum | 1/1 (100%) |
| benchmark_return | 20/20 (100%) |
| return | 83/83 (100%) |

## Reading the numbers

- **Partial truth files.** The three real factsheets list only a sample of their values, so
  rows beyond that sample are not errors and precision is not scored ("n/a"). The extras the
  eval prints for them are real values the sample did not list, for example each Fundsmith share
  class's NAV and Man AHL's AUM and 1- and 3-year returns.
- **Harborline 57%.** The three extras are the per-unit prices of holdings in the custody
  statement (Man AHL, Fundsmith, Vanguard), stored as NAV. They are real prices printed in the
  document, but the truth file does not count them, so they lower precision.
- **Period "other".** Several extras use period kind `other` (for example monthly or
  since-inception figures); see "Units and periods" in the README's next steps.

## Raw output

```
Per document
file                                                          recall   prec  rows    sec
fundsmith_factsheet_2026-01.pdf                              3/3        n/a   262  166.1   $0.2863
    EXTRA Fundsmith Equity Fund | T Class Acc | nav other 2026-01-30 61.04
    EXTRA Fundsmith Equity Fund | T Class Inc | nav other 2026-01-30 57.38
    EXTRA Fundsmith Equity Fund | R Class Acc | nav other 2026-01-30 57.03
    EXTRA Fundsmith Equity Fund | R Class Inc | nav other 2026-01-30 55.95
    EXTRA Fundsmith Equity Fund | I Class Acc | nav other 2026-01-30 62.14
man-ahl_factsheet_2026-08.pdf                                9/9        n/a   158  108.4   $0.2252
    EXTRA Man AHL Diversified | None | aum other 2026-08-28 313174253
    EXTRA Man AHL Diversified | Class DN USD | return other 2026-08-31 0.0111
    EXTRA Man AHL Diversified | Class DN USD | return other 2026-08-31 0.0021
    EXTRA Man AHL Diversified | Class DN USD | return 1y 2026-08-31 0.3678
    EXTRA Man AHL Diversified | Class DN USD | return 3y 2026-08-31 0.2189
uvic-pension_performance-report_2026-07.pdf                  9/9        n/a    76   44.2   $0.0801
    EXTRA Balanced Fund | None | return other 2026-07-31 0.0811
    EXTRA Balanced Fund | None | return ytd 2026-06-30 0.0386
    EXTRA Balanced Fund | None | return 1y 2026-06-30 0.0723
    EXTRA Balanced Fund | None | return other 2026-06-30 0.0979
    EXTRA Balanced Fund | None | return ytd 2026-05-31 0.0279
alderbank_performance-summary_2026-09.csv                   29/29      100%    29   32.4   $0.0424
harborline-custody_account-statement_2026-09.pdf             4/4        57%     7   21.6   $0.0253
    EXTRA Man AHL Diversified plc | DN USD | nav other 2026-09-30 312.44
    EXTRA Fundsmith SICAV Equity Fund | T EUR Acc | nav other 2026-09-30 71.38
    EXTRA Vanguard Total Stock Market Index | Adm | nav other 2026-09-30 166.07
kestrel-ridge_investor-update_2026-01.eml                    4/4       100%     4   13.0   $0.0125
larchmont-quay_q3-letter_fwd_2026-10.eml                    15/15      100%    15   17.6   $0.0260
northwind-capital_monthly-returns_2026-09.csv               35/35      100%    35   39.6   $0.0602

Per measure (recall)
measure                    hits
account_return          2/2     100%
account_value           2/2     100%
aum                     1/1     100%
benchmark_return       20/20    100%
return                 83/83    100%

Harborline holding gains read as fund return: 0 (want 0)
Total time: 443.0s
Tokens (API-reported): input 72,781, output 61,850; estimated cost $0.7580 (list prices in evals/run_eval.py)
```
