# Document intake automation (n8n + Claude)

Work in progress (Build 1, started 6 Oct 2026). Results will be added once the workflow runs end to end.

## The problem

Invoices, receipts and certificates arrive by email or in a shared folder, and someone retypes them into Excel or Google Sheets. Typing errors and missing documents slip through.

## What it will do

1. A document lands in the intake folder (or the inbox).
2. n8n sends it to Claude, which returns a fixed set of fields. Anything not printed comes back empty instead of guessed.
3. Checks run on every document:
   - required fields;
   - valid dates;
   - line amounts, subtotal, tax and total add up;
   - duplicates;
   - expired certificates.
4. One row per document goes to the Documents sheet, and line items go to the Lines sheet. Each row is marked OK or Needs review, with the reason.
5. A document that fails a check sends an alert.

Done means:
- every test document gives the expected row and flags;
- accuracy, cost per document and time are measured;
- the README and a short demo video show the run.

## Test set: 30 documents with known answers

All companies, people and addresses are made up.

| Documents | What they test |
|---|---|
| `INV-01` to `INV-20` | Invoices from 4 vendors with different layouts, date and number formats. Includes 2 scans, a two-page invoice and 6 planted problems. Copied from [invoice-extraction-demo](https://github.com/sarfrazmangrio/invoice-extraction-demo). |
| `R-01` to `R-07` | Till receipts from 2 shops (PKR and USD). Includes a phone photo (`R-03.jpg`), a scan (`R-07`), a duplicate (`R-04` repeats `R-02`), a missing date (`R-05`) and a total printed 100 too high (`R-06`). |
| `C-01` to `C-03` | Certificates of insurance from suppliers. `C-02` expired on 31 Aug 2026, and `C-03` has a blank policy number. |

`test_set/expected.json` holds the true value of every field and every line item. It also lists the flags each document should get: 11 planted problems in total.

To rebuild the receipts, certificates and expected answers:

```
python tools/generate_test_set.py
```

## Checking a run

Export the sheet's Documents tab (and optionally the Lines tab) as CSV, then:

```
python tools/check_results.py --documents documents.csv --lines lines.csv --report report.md
```

It prints:
- documents passed;
- fields correct;
- planted problems flagged and false alarms;
- line items correct;
- every mismatch.

The exit code is 0 only when all 30 documents pass. The column layout is in [docs/output_contract.md](docs/output_contract.md); `docs/example_documents.csv` shows what a perfect run writes. To score a run on only some of the documents, add `--only-present`.

Tests: `python -m pytest -q`. They cover the check itself, the workflow file and the workflow's checks code.

## Running n8n

n8n runs in Docker on the same computer. From the `n8n` folder, run `docker compose up -d`, then open http://localhost:5678 and create the owner account. The settings in `n8n/docker-compose.yml`:
- switch on the local-folder trigger;
- keep the command-execution node blocked;
- limit file access to the mounted `files` folder.

Tested with n8n 2.42.3 (Community Edition) on Docker Desktop 4.94 for Windows. On Windows, Docker Desktop also needs:
- the Virtual Machine Platform Windows feature;
- CPU virtualization (Intel VT-x or AMD-V) switched on in the BIOS/UEFI.

## The workflow (core flow)

`n8n/document_intake_core.json` is the workflow to import. It is assembled from the JavaScript in `n8n/src` by `python tools/build_workflow.py`, so edit the sources, not the JSON.

1. Reads every PDF, JPG and PNG in `files/intake`.
2. Sends each file to Claude (Haiku 4.5), one at a time, as a document or image block. Structured outputs make every reply follow one schema with the 15 fields in the output contract plus the line items. Anything not printed comes back empty.
3. Runs the checks (required fields, dates, arithmetic, duplicates, expired certificates) and marks each document OK or Needs review.
4. Writes `documents.csv`, `lines.csv` and `run_log.csv` (tokens, cost and any error per document) to `files/output`.

A call that fails becomes a Needs review row flagged `extraction_failed`, and the error goes to the run log; the other documents carry on.

The API key lives in an n8n credential (Header Auth, name `x-api-key`), never in the workflow file.

Status:
- Against a stand-in for the Claude API that returns the expected answers, the whole flow ran in n8n 2.42.3 and 30 of 30 documents passed. This tests everything except Claude's reading.
- First run with the real API (6 Oct, 7 of the 30 documents, including a scan, a phone photo and 2 planted problems): 7 of 7 passed, 105 of 105 fields and 23 of 23 line items correct, both problems flagged with no false alarms, USD 0.0315 in all. Details in [results/2026-10-06-first-run](results/2026-10-06-first-run/).
- Next: the other 23 documents.

## Built with

Claude Code as the coding assistant; n8n; the Claude API; Python.
