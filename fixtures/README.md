# Test documents

| Folder | What | Count |
|---|---|---|
| `real/` | Public documents from real managers, chosen by the user from a 29-file recon set. Committed so the repo runs as-is for reviewers. | 7 |
| `synthetic/` | Fictional managers, built by `generate.py` to cover what the real set lacks (return CSVs, emailed updates). | 4 |

`real/manifest.csv` records each file's source URL, landing page, retrieval
date, sha256 and notes, including any terms-of-use wording the source states.

`*.truth.json` sits next to a document and lists the observations an extractor
should produce, with values as fractions (`-0.005` = -0.5%) and the traps the
document contains. Synthetic truths are complete. Real truths are marked
`"partial": true`: they pin the 2026 return figures, checked by hand against
the PDF text, not every number in the file.

**January 2026 returns across the set** (the "best January" question):

| Fund | Jan 2026 | Source |
|---|---|---|
| Man AHL Diversified (DN USD) | +8.42% | real |
| Alderbank European Equity (I EUR Acc) | +3.21% | synthetic |
| Alderbank European Equity (A EUR Acc) | +3.12% | synthetic |
| Northwind Global Macro (Founders) | +2.37% | synthetic |
| Kestrel Ridge L/S Equity | +1.90% | synthetic |
| Northwind Credit Opportunities (A) | +0.94% | synthetic |
| UVic Balanced Fund | −0.21% | real |
| Alderbank Asia Income (A USD Dist) | −0.45% | synthetic |
| Fundsmith Equity (T EUR Acc) | −0.50% | real |
| Larchmont Quay Multi-Strategy | −0.60% | synthetic |

The iShares SWDA, JPMorgan JPEF and Fundsmith August files have no January
2026 monthly figure; the TSP CSV holds daily prices, from which a January
return can be computed but is not stated.
