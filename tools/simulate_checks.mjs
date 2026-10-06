// Run the "Checks and rows" Code node outside n8n, on a perfect extraction of the test set.
//
//     node tools/simulate_checks.mjs <output folder>
//
// Each document's reply is its expected answer, shaped like Claude's structured output,
// plus one failed call. Writes documents.csv, lines.csv and run_log.csv to the output folder,
// which tools/check_results.py then scores. Used by tests/test_workflow.py.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outDir = process.argv[2];
if (!outDir) throw new Error('usage: node tools/simulate_checks.mjs <output folder>');

const expected = JSON.parse(fs.readFileSync(path.join(ROOT, 'test_set', 'expected.json'), 'utf8'));
const code = fs.readFileSync(path.join(ROOT, 'n8n', 'src', 'checks.js'), 'utf8');
const TEXT = ['issuer', 'doc_number', 'doc_date', 'due_date', 'effective_date', 'expiry_date', 'currency', 'counterparty', 'policy_number'];
const NUM = ['coverage_limit', 'subtotal', 'tax_rate_percent', 'tax_amount', 'total'];

const reply = (doc) => {
  const data = { doc_type: doc.fields.doc_type, lines: doc.lines };
  for (const k of TEXT) data[k] = doc.fields[k] ?? '';
  for (const k of NUM) data[k] = doc.fields[k] ?? null;
  return { model: 'claude-haiku-4-5-20251001', stop_reason: 'end_turn', content: [{ type: 'text', text: JSON.stringify(data) }],
    usage: { input_tokens: 2000, output_tokens: 300 } };
};
const docs = [...expected.documents].sort((a, b) => a.file.localeCompare(b.file, 'en', { numeric: true }));
const requests = docs.map((d) => ({ json: { file: d.file } })).concat([{ json: { file: 'ZZ-failed.pdf' } }]);
const replies = docs.map((d) => ({ json: reply(d) })).concat([{ json: { error: { message: '529 overloaded' } } }]);

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const node = new AsyncFunction('$input', '$', '$now', code);
const items = await node({ all: () => replies }, () => ({ all: () => requests }), { toFormat: () => expected.check_date });

const quote = (v) => { const s = String(v ?? ''); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
const toCsv = (rows) => { const cols = Object.keys(rows[0]); return [cols.join(','), ...rows.map((r) => cols.map((c) => quote(r[c])).join(','))].join('\n') + '\n'; };
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'documents.csv'), toCsv(items.map((i) => i.json.row)));
fs.writeFileSync(path.join(outDir, 'lines.csv'), toCsv(items.flatMap((i) => i.json.lines)));
fs.writeFileSync(path.join(outDir, 'run_log.csv'), toCsv(items.map((i) => i.json.log)));
console.log(`wrote ${items.length} documents to ${outDir}`);
