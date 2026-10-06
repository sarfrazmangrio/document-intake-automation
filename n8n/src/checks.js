// Code node "Checks and rows" (run once for all items).
// Reads Claude's replies, runs the checks on every document and builds the sheet rows.
// Input: every reply from "Claude: extract fields", collected by the loop in the same order as "Build Claude requests".
// Output: one item per document with { row, lines, log }.

const DOC_COLUMNS = ['file', 'doc_type', 'issuer', 'doc_number', 'doc_date', 'due_date', 'effective_date', 'expiry_date',
  'currency', 'counterparty', 'policy_number', 'coverage_limit', 'subtotal', 'tax_rate_percent', 'tax_amount', 'total',
  'status', 'flags'];
const MONEY_TOLERANCE = 0.011; // amounts are printed to 2 decimals
const PRICES_PER_MTOK = { 'claude-haiku-4-5': [1.0, 5.0] }; // USD per million tokens (input, output)
const REQUIRED = {
  invoice: ['issuer', 'doc_number', 'doc_date', 'total'],
  receipt: ['issuer', 'doc_number', 'doc_date', 'total'],
  certificate: ['counterparty', 'issuer', 'policy_number', 'expiry_date'],
};

const blank = (v) => v === null || v === undefined || (typeof v === 'string' && v.trim() === '');
const num = (v) => (blank(v) ? null : Number(v));
const normKey = (t) => String(t).toLowerCase().replace(/[^a-z0-9]/g, '');

function parseDate(v) {
  if (blank(v)) return null;
  const s = String(v).trim();
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return 'invalid';
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3] ? s : 'invalid';
}

function checkDocument(doc, today) {
  const flags = new Set();
  const type = String(doc.doc_type || '').toLowerCase();
  for (const field of REQUIRED[type] || REQUIRED.invoice) if (blank(doc[field])) flags.add('missing_required_field');

  const dates = {};
  for (const field of ['doc_date', 'due_date', 'effective_date', 'expiry_date']) {
    dates[field] = parseDate(doc[field]);
    if (dates[field] === 'invalid') flags.add('invalid_date');
  }
  const ok = (d) => d && d !== 'invalid';
  if (type === 'invoice' && ok(dates.doc_date) && ok(dates.due_date) && dates.due_date < dates.doc_date) flags.add('due_before_invoice');
  if (type === 'certificate' && ok(dates.expiry_date) && dates.expiry_date < today) flags.add('certificate_expired');

  const lines = doc.lines || [];
  for (const line of lines) {
    const q = num(line.quantity), p = num(line.unit_price), a = num(line.amount);
    if (q !== null && p !== null && a !== null && Math.abs(q * p - a) > MONEY_TOLERANCE) flags.add('line_math');
  }
  const subtotal = num(doc.subtotal), tax = num(doc.tax_amount), rate = num(doc.tax_rate_percent), total = num(doc.total);
  const amounts = lines.map((l) => num(l.amount));
  if (lines.length && subtotal !== null && !amounts.includes(null)
      && Math.abs(amounts.reduce((s, a) => s + a, 0) - subtotal) > MONEY_TOLERANCE) flags.add('lines_sum_to_subtotal');
  // sellers that round tax to whole units (common for rupees) can be up to 0.5 off
  const taxTolerance = tax !== null && Number.isInteger(tax) ? 0.5 + MONEY_TOLERANCE : MONEY_TOLERANCE;
  if (rate !== null && tax !== null && subtotal !== null && Math.abs((subtotal * rate) / 100 - tax) > taxTolerance) flags.add('tax_matches_rate');
  if (subtotal !== null && total !== null && Math.abs(subtotal + (tax || 0) - total) > MONEY_TOLERANCE) flags.add('total_equals_subtotal_plus_tax');
  return flags;
}

function costUsd(model, usage) {
  const key = Object.keys(PRICES_PER_MTOK).find((p) => String(model || '').startsWith(p));
  if (!key || usage.input_tokens === undefined) return '';
  const [pin, pout] = PRICES_PER_MTOK[key];
  return Math.round(((usage.input_tokens * pin + usage.output_tokens * pout) / 1e6) * 1e6) / 1e6;
}

function parseReply(reply) {
  if (reply.error) {
    const e = reply.error;
    throw new Error(typeof e === 'string' ? e : e.message || JSON.stringify(e));
  }
  if (reply.stop_reason !== 'end_turn') throw new Error(`stopped early (stop_reason=${reply.stop_reason})`);
  const text = (reply.content || []).filter((b) => b.type === 'text').map((b) => b.text).join('');
  return JSON.parse(text);
}

const requests = $('Build Claude requests').all();
const replies = $input.all();
if (requests.length !== replies.length) throw new Error(`${requests.length} requests but ${replies.length} replies`);
const today = $now.toFormat('yyyy-MM-dd');
const seen = new Map();
const out = [];

for (let i = 0; i < replies.length; i++) {
  const file = requests[i].json.file;
  const reply = replies[i].json || {};
  const usage = reply.usage || {};
  const log = { file, model: reply.model || '', input_tokens: usage.input_tokens ?? '', output_tokens: usage.output_tokens ?? '',
    cost_usd: costUsd(reply.model, usage), error: '' };
  const row = Object.fromEntries(DOC_COLUMNS.map((c) => [c, '']));
  row.file = file;

  let doc;
  try {
    doc = parseReply(reply);
  } catch (err) {
    log.error = String(err.message || err);
    row.status = 'Needs review';
    row.flags = 'extraction_failed';
    out.push({ json: { row, lines: [], log } });
    continue;
  }

  const flags = checkDocument(doc, today);
  if (!blank(doc.issuer) && !blank(doc.doc_number)) {
    const key = `${normKey(doc.issuer)}|${normKey(doc.doc_number)}`;
    if (seen.has(key)) flags.add('duplicate_document');
    else seen.set(key, file);
  }

  for (const c of DOC_COLUMNS.slice(1, -2)) row[c] = doc[c] === null || doc[c] === undefined ? '' : doc[c];
  row.doc_type = String(doc.doc_type || '').toLowerCase();
  row.status = flags.size ? 'Needs review' : 'OK';
  row.flags = [...flags].join('; ');
  const lines = (doc.lines || []).map((l, k) => ({ file, line_no: k + 1, description: l.description ?? '',
    quantity: l.quantity ?? '', unit_price: l.unit_price ?? '', amount: l.amount ?? '' }));
  out.push({ json: { row, lines, log } });
}
return out;
