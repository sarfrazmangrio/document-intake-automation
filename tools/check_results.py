"""Pass or fail check: compare what the workflow wrote to the sheet with the expected answers.

Export the sheet's "Documents" tab (and, if you want line items scored too, the "Lines" tab) as CSV, then run:

    python tools/check_results.py --documents documents.csv [--lines lines.csv] [--report report.md] [--only-present]

--only-present scores just the documents that are in the sheet, for a run on part of the test set.

A document passes when every field matches, its flags match the planted problems exactly,
and its status is right ("Needs review" when it has a flag, "OK" when it has none).
Exit code 0 means every document passed; 1 means at least one failed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXPECTED = ROOT / "test_set" / "expected.json"

DOC_COLUMNS = ["file", "doc_type", "issuer", "doc_number", "doc_date", "due_date", "effective_date", "expiry_date",
               "currency", "counterparty", "policy_number", "coverage_limit", "subtotal", "tax_rate_percent",
               "tax_amount", "total", "status", "flags"]
LINE_COLUMNS = ["file", "line_no", "description", "quantity", "unit_price", "amount"]
NUMBER_FIELDS = {"coverage_limit", "subtotal", "tax_rate_percent", "tax_amount", "total"}
DATE_FIELDS = {"doc_date", "due_date", "effective_date", "expiry_date"}
MONEY_TOLERANCE = 0.011


# ------------------------------------------------------------------ normalizing

def blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def norm_text(v):
    return None if blank(v) else re.sub(r"\s+", " ", str(v)).strip().casefold()


def norm_date(v):
    if blank(v):
        return None
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})", str(v))
    return m.group(1) if m else str(v).strip()


def norm_number(v):
    if blank(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    cleaned = re.sub(r"[^0-9.\-]", "", str(v))
    try:
        return float(cleaned)
    except ValueError:
        return str(v).strip()


def same(field: str, expected, found) -> bool:
    if field in NUMBER_FIELDS:
        e, f = norm_number(expected), norm_number(found)
        if e is None or f is None or isinstance(e, str) or isinstance(f, str):
            return e == f
        return abs(e - f) <= MONEY_TOLERANCE
    if field in DATE_FIELDS:
        return norm_date(expected) == norm_date(found)
    return norm_text(expected) == norm_text(found)


def split_flags(v) -> set[str]:
    if blank(v):
        return set()
    return {x.strip().lower() for x in re.split(r"[;,]", str(v)) if x.strip()}


# ------------------------------------------------------------------ loading

def load_expected(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ scoring

def score(expected: dict, doc_rows: list[dict], line_rows: list[dict] | None = None) -> dict:
    fields = expected["fields"]
    by_file = {}
    for row in doc_rows:
        by_file.setdefault(row.get("file", "").strip(), row)
    lines_by_file = {}
    for row in line_rows or []:
        lines_by_file.setdefault(row.get("file", "").strip(), []).append(row)

    results, totals = [], {"fields": 0, "fields_ok": 0, "filled": 0, "filled_ok": 0,
                           "flags_expected": 0, "flags_caught": 0, "false_alarms": 0, "lines": 0, "lines_ok": 0}
    for doc in expected["documents"]:
        file, problems = doc["file"], []
        row = by_file.get(file)
        if row is None:
            results.append({"file": file, "passed": False, "problems": ["not in the sheet"]})
            totals["fields"] += len(fields)
            totals["filled"] += sum(1 for k in fields if doc["fields"].get(k) is not None)
            totals["flags_expected"] += len(doc["expected_flags"])
            continue
        for k in fields:
            exp, got = doc["fields"].get(k), row.get(k)
            ok = same(k, exp, got)
            totals["fields"] += 1
            totals["fields_ok"] += ok
            if exp is not None:
                totals["filled"] += 1
                totals["filled_ok"] += ok
            if not ok:
                problems.append(f"{k}: expected {exp!r}, found {got!r}")
        want, have = {x.lower() for x in doc["expected_flags"]}, split_flags(row.get("flags"))
        totals["flags_expected"] += len(want)
        totals["flags_caught"] += len(want & have)
        totals["false_alarms"] += len(have - want)
        if want - have:
            problems.append(f"missed flags: {', '.join(sorted(want - have))}")
        if have - want:
            problems.append(f"false alarms: {', '.join(sorted(have - want))}")
        want_status = "needs review" if want else "ok"
        if norm_text(row.get("status")) != want_status:
            problems.append(f"status: expected {'Needs review' if want else 'OK'}, found {row.get('status')!r}")
        if line_rows is not None:
            got_lines = sorted(lines_by_file.get(file, []), key=lambda r: norm_number(r.get("line_no")) or 0)
            exp_lines = doc["lines"]
            if len(got_lines) != len(exp_lines):
                problems.append(f"line items: expected {len(exp_lines)}, found {len(got_lines)}")
            for i, exp_line in enumerate(exp_lines):
                totals["lines"] += 1
                if i >= len(got_lines):
                    continue
                got = got_lines[i]
                bad = [k for k in ("description", "quantity", "unit_price", "amount")
                       if not (same("subtotal", exp_line[k], got.get(k)) if k != "description"
                               else norm_text(exp_line[k]) == norm_text(got.get(k)))]
                if bad:
                    problems.append(f"line {i + 1}: {', '.join(bad)} differ")
                else:
                    totals["lines_ok"] += 1
        results.append({"file": file, "passed": not problems, "problems": problems})
    return {"results": results, "totals": totals}


def summary_lines(scored: dict, with_lines: bool) -> list[str]:
    t, res = scored["totals"], scored["results"]
    passed = sum(r["passed"] for r in res)
    pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"
    out = [
        f"Documents passed: {passed} of {len(res)}",
        f"Fields correct: {t['fields_ok']} of {t['fields']} ({pct(t['fields_ok'], t['fields'])}); "
        f"printed fields only: {t['filled_ok']} of {t['filled']} ({pct(t['filled_ok'], t['filled'])})",
        f"Planted problems flagged: {t['flags_caught']} of {t['flags_expected']}; false alarms: {t['false_alarms']}",
    ]
    if with_lines:
        out.append(f"Line items correct: {t['lines_ok']} of {t['lines']} ({pct(t['lines_ok'], t['lines'])})")
    failed = [r for r in res if not r["passed"]]
    if failed:
        out.append("")
        out.append("Failed documents:")
        for r in failed:
            out.append(f"- {r['file']}: " + "; ".join(r["problems"]))
    return out


# ------------------------------------------------------------------ helpers for tests and examples

def perfect_rows(expected: dict) -> tuple[list[dict], list[dict]]:
    """The sheet rows a perfect run would write (used by the tests and as a format example)."""
    docs, lines = [], []
    for doc in expected["documents"]:
        row = {k: "" for k in DOC_COLUMNS}
        row["file"] = doc["file"]
        for k, v in doc["fields"].items():
            row[k] = "" if v is None else v
        row["flags"] = "; ".join(doc["expected_flags"])
        row["status"] = "Needs review" if doc["expected_flags"] else "OK"
        docs.append(row)
        for i, ln in enumerate(doc["lines"], start=1):
            lines.append({"file": doc["file"], "line_no": i, **{k: ln[k] for k in LINE_COLUMNS[2:]}})
    return docs, lines


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--documents", type=Path, required=True, help="CSV export of the Documents tab")
    ap.add_argument("--lines", type=Path, help="CSV export of the Lines tab (optional)")
    ap.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED)
    ap.add_argument("--report", type=Path, help="also write the result as a Markdown file")
    ap.add_argument("--only-present", action="store_true",
                    help="score only the documents that appear in the sheet (for a run on part of the test set)")
    args = ap.parse_args(argv)

    expected = load_expected(args.expected)
    doc_rows = read_csv(args.documents)
    if args.only_present:
        present = {row.get("file", "").strip() for row in doc_rows}
        expected = {**expected, "documents": [d for d in expected["documents"] if d["file"] in present]}
    scored = score(expected, doc_rows, read_csv(args.lines) if args.lines else None)
    lines = summary_lines(scored, with_lines=bool(args.lines))
    print("\n".join(lines))
    if args.report:
        args.report.write_text("# Test run result\n\n" + "\n".join(
            (f"- {x}" if x and not x.startswith("-") and not x.endswith(":") else x) for x in lines) + "\n", encoding="utf-8")
    all_passed = all(r["passed"] for r in scored["results"])
    print("\nPASS" if all_passed else "\nFAIL")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
