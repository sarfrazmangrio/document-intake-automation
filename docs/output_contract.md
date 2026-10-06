# Output contract: what the workflow writes

The workflow writes to two sheets, with the same columns whether the target is Google Sheets or an Excel file. The pass or fail check (`tools/check_results.py`) reads CSV exports of these sheets.

## Documents (one row per document)

| Column | Invoice | Receipt | Certificate |
|---|---|---|---|
| file | file name | file name | file name |
| doc_type | `invoice` | `receipt` | `certificate` |
| issuer | vendor | shop | insurer |
| doc_number | invoice number | receipt or order number | certificate number |
| doc_date | invoice date | receipt date | date issued |
| due_date | due date | | |
| effective_date | | | policy effective |
| expiry_date | | | policy expires |
| currency | ISO code | ISO code | currency of the limit |
| counterparty | customer billed | | insured company |
| policy_number | | | policy number |
| coverage_limit | | | each-occurrence limit |
| subtotal, tax_rate_percent, tax_amount, total | as printed | as printed | |
| status | `OK` or `Needs review` | | |
| flags | rule names separated by `;` | | |

Formats:
- Dates are `YYYY-MM-DD`.
- Numbers are plain numbers (thousands separators and currency symbols are tolerated by the check).
- A field that isn't printed stays empty.

## Lines (one row per line item)

`file, line_no, description, quantity, unit_price, amount`

## Flag names

| Flag | Meaning |
|---|---|
| `missing_required_field` | A required field is empty. Invoices: vendor, number, date, total. Receipts: shop, number, date, total. Certificates: insured, insurer, policy number, expiry date |
| `invalid_date` | A date isn't a real calendar date |
| `due_before_invoice` | The due date is before the invoice date |
| `line_math` | Quantity x unit price doesn't equal the line amount |
| `lines_sum_to_subtotal` | The line amounts don't add up to the subtotal |
| `tax_matches_rate` | The tax doesn't match the printed rate |
| `total_equals_subtotal_plus_tax` | The total doesn't equal subtotal plus tax |
| `duplicate_document` | Same issuer and number as an earlier document |
| `certificate_expired` | The policy expiry date has passed |
