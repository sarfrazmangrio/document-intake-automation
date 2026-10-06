# Full run (7 Oct 2026)

All 30 test documents through the core flow (`n8n/document_intake_core.json`, the version that sends one document at a time), in n8n 2.42.3 on Windows (Docker Desktop), with Claude Haiku 4.5.

Result (`report.md`, from `python tools/check_results.py`):
- 30 of 30 documents passed: 450 of 450 fields (300 of 300 printed fields) and 140 of 140 line items correct.
- All 11 planted problems flagged, with no false alarms (table below).
- No call failed: `run_log.csv` has no errors.
- Cost: USD 0.1425 for the 30 documents (101,155 input and 8,266 output tokens), about USD 0.0048 per document, at Haiku 4.5's list price. The two-page invoice (INV-03) cost the most, USD 0.0106.
- Time: under 2 minutes for all 30 documents, checked against the clock. The run log doesn't record time yet.

The hard cases all passed: 2 scanned invoices (INV-10 and INV-19), a scanned receipt (R-07), a phone photo (R-03.jpg), a two-page invoice (INV-03), and slash dates in both US (month first) and Pakistani (day first) order.

| Document | Planted problem | Flag raised |
|---|---|---|
| INV-04 | Subtotal misprinted | `lines_sum_to_subtotal` |
| INV-06 | Due date before the invoice date | `due_before_invoice` |
| INV-09 | A line amount isn't quantity × unit price | `line_math` |
| INV-12 | Invoice number missing | `missing_required_field` |
| INV-16 | Total misprinted | `total_equals_subtotal_plus_tax` |
| INV-19 | Scanned copy of INV-15 | `duplicate_document` |
| R-04 | Repeats R-02 | `duplicate_document` |
| R-05 | Date left blank | `missing_required_field` |
| R-06 | Total printed 100 too high | `total_equals_subtotal_plus_tax` |
| C-02 | Expired on 31 Aug 2026 | `certificate_expired` |
| C-03 | Policy number left blank | `missing_required_field` |

The files here are the workflow's own output: `documents.csv`, `lines.csv` and `run_log.csv`.
