# First run with the Claude API (6 Oct 2026)

The core flow (`n8n/document_intake_core.json`) on 7 of the 30 test documents, in n8n 2.42.3 on Windows (Docker Desktop), with Claude Haiku 4.5.

| Document | What it tests |
|---|---|
| INV-01 | US invoice, dates written out |
| INV-02 | Pakistani invoice, day-first slash dates |
| INV-10 | Scanned invoice (no text layer) |
| R-02 | US receipt, month-first slash date |
| R-03.jpg | Phone photo of a receipt |
| R-06 | Planted problem: total printed 100 too high |
| C-02 | Planted problem: expired certificate of insurance |

Result (`report.md`, from `python tools/check_results.py --only-present`):
- 7 of 7 documents passed: 105 of 105 fields and 23 of 23 line items correct.
- Both planted problems flagged, with no false alarms.
- Cost: USD 0.0315 for the 7 documents (22,803 input and 1,736 output tokens), about USD 0.0045 per document, at Haiku 4.5's list price.

Seven documents is a small sample. The other 23 documents run next.

The files here are the workflow's own output: `documents.csv`, `lines.csv` and `run_log.csv`.
