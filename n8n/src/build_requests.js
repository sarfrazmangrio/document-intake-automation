// Code node "Build Claude requests" (run once for all items).
// Turns each file read from the intake folder into one Claude API request.
// The file goes to Claude as a document block (PDF) or an image block (JPG, PNG),
// and structured outputs force the reply to match SCHEMA.

const MODEL = 'claude-haiku-4-5-20251001';
const API_URL = 'https://api.anthropic.com/v1/messages';
const MEDIA_TYPES = { pdf: 'application/pdf', jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png' };

const SYSTEM_PROMPT = `You extract data from business documents for a bookkeeping team: supplier invoices, till receipts and certificates of insurance.

Rules:
- Copy values exactly as printed. Do not calculate, correct or fill in anything; the numbers are checked later.
- If a field is blank or not printed, return an empty string for text and null for numbers. Never invent a number, date or amount.
- Dates: return YYYY-MM-DD. Slash dates on documents from the United States are month first (MM/DD/YYYY); on documents from Pakistan and other countries they are day first (DD/MM/YYYY). Ignore times.
- Amounts and quantities: plain numbers with no currency symbols or thousands separators. Read lakh-style grouping correctly (1,23,450 is 123450).
- currency: the ISO 4217 code (USD, PKR, ...) from the symbol, code or wording; if none is printed, the currency of the issuer's country.
- doc_number: the number without its label or # sign.
- Invoices: issuer is the company that issued the invoice; counterparty is the party billed.
- Receipts: issuer is the shop; counterparty is empty.
- Certificates of insurance: issuer is the insurer; counterparty is the insured, not the certificate holder; doc_date is the date issued; coverage_limit is the each-occurrence limit; currency is the currency of that limit. Certificates have no lines and no subtotal, tax or total.
- lines: one entry per printed line item, in order, across all pages. Do not add subtotal, tax or total rows.
- tax_rate_percent: the printed rate (18 for 18%); tax_amount: the printed tax amount. Both null if there is no tax line.`;

const TEXT = { type: 'string' };
const NUMBER_OR_NULL = { type: ['number', 'null'] };
const SCHEMA = {
  type: 'object',
  properties: {
    doc_type: { type: 'string', enum: ['invoice', 'receipt', 'certificate'] },
    issuer: { ...TEXT, description: 'Invoices: the vendor. Receipts: the shop. Certificates: the insurer.' },
    doc_number: { ...TEXT, description: 'Invoice, receipt, order or certificate number without its label; empty if blank.' },
    doc_date: { ...TEXT, description: 'Invoice date, receipt date or date issued, as YYYY-MM-DD; empty if not printed.' },
    due_date: { ...TEXT, description: 'Invoices only: payment due date as YYYY-MM-DD; otherwise empty.' },
    effective_date: { ...TEXT, description: 'Certificates only: policy effective date as YYYY-MM-DD; otherwise empty.' },
    expiry_date: { ...TEXT, description: 'Certificates only: policy expiry date as YYYY-MM-DD; otherwise empty.' },
    currency: { ...TEXT, description: 'ISO 4217 code, e.g. USD or PKR.' },
    counterparty: { ...TEXT, description: 'Invoices: the billed party. Certificates: the insured, not the certificate holder. Receipts: empty.' },
    policy_number: { ...TEXT, description: 'Certificates only: policy number as printed; empty if blank.' },
    coverage_limit: { ...NUMBER_OR_NULL, description: 'Certificates only: the each-occurrence limit.' },
    lines: {
      type: 'array',
      description: 'One entry per printed line item, in order. Excludes subtotal, tax and total rows.',
      items: {
        type: 'object',
        properties: { description: TEXT, quantity: NUMBER_OR_NULL, unit_price: NUMBER_OR_NULL, amount: NUMBER_OR_NULL },
        required: ['description', 'quantity', 'unit_price', 'amount'],
        additionalProperties: false,
      },
    },
    subtotal: { ...NUMBER_OR_NULL, description: 'Printed subtotal.' },
    tax_rate_percent: { ...NUMBER_OR_NULL, description: 'Printed tax rate, e.g. 18 for 18%.' },
    tax_amount: { ...NUMBER_OR_NULL, description: 'Printed tax amount.' },
    total: { ...NUMBER_OR_NULL, description: 'Printed total.' },
  },
  required: ['doc_type', 'issuer', 'doc_number', 'doc_date', 'due_date', 'effective_date', 'expiry_date', 'currency',
    'counterparty', 'policy_number', 'coverage_limit', 'lines', 'subtotal', 'tax_rate_percent', 'tax_amount', 'total'],
  additionalProperties: false,
};

const out = [];
const items = $input.all();
for (let i = 0; i < items.length; i++) {
  const bin = items[i].binary && items[i].binary.data;
  if (!bin) continue;
  const fileName = bin.fileName || `file-${i + 1}`;
  const ext = String(bin.fileExtension || fileName.split('.').pop() || '').toLowerCase();
  const mediaType = MEDIA_TYPES[ext];
  if (!mediaType) continue; // not a PDF or an image: leave it in the folder
  const buffer = await this.helpers.getBinaryDataBuffer(i, 'data');
  const source = { type: 'base64', media_type: mediaType, data: buffer.toString('base64') };
  const block = mediaType === 'application/pdf' ? { type: 'document', source } : { type: 'image', source };
  out.push({
    json: {
      file: fileName,
      api_url: API_URL,
      request: {
        model: MODEL,
        max_tokens: 4096,
        system: SYSTEM_PROMPT,
        messages: [{ role: 'user', content: [block, { type: 'text', text: 'Extract this document.' }] }],
        output_config: { format: { type: 'json_schema', schema: SCHEMA } },
      },
    },
  });
}
// Fixed order, so "duplicate of an earlier document" means earlier in file-name order.
out.sort((a, b) => a.json.file.localeCompare(b.json.file, 'en', { numeric: true }));
return out;
