"""The pass or fail check must pass a perfect run and catch every kind of mistake."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_results as cr  # noqa: E402

EXPECTED = cr.load_expected(cr.DEFAULT_EXPECTED)


def run(docs, lines=None):
    return cr.score(EXPECTED, docs, lines)


def by_file(scored, file):
    return next(r for r in scored["results"] if r["file"] == file)


def test_test_set_shape():
    docs = EXPECTED["documents"]
    assert len(docs) == 30
    assert sum(d["fields"]["doc_type"] == "invoice" for d in docs) == 20
    assert sum(d["fields"]["doc_type"] == "receipt" for d in docs) == 7
    assert sum(d["fields"]["doc_type"] == "certificate" for d in docs) == 3
    assert sum(len(d["expected_flags"]) for d in docs) == 11
    for d in docs:
        assert (cr.ROOT / "test_set" / "documents" / d["file"]).exists(), d["file"]


def test_perfect_run_passes():
    docs, lines = cr.perfect_rows(EXPECTED)
    scored = run(docs, lines)
    assert all(r["passed"] for r in scored["results"])
    t = scored["totals"]
    assert t["fields_ok"] == t["fields"] and t["flags_caught"] == t["flags_expected"] == 11
    assert t["false_alarms"] == 0 and t["lines_ok"] == t["lines"]


def test_wrong_amount_fails_that_document_only():
    docs, _ = cr.perfect_rows(EXPECTED)
    row = next(r for r in docs if r["file"] == "R-01.pdf")
    row["total"] = 6265.00
    scored = run(docs)
    assert not by_file(scored, "R-01.pdf")["passed"]
    assert sum(not r["passed"] for r in scored["results"]) == 1
    assert scored["totals"]["fields_ok"] == scored["totals"]["fields"] - 1


def test_missed_flag_and_false_alarm_are_counted():
    docs, _ = cr.perfect_rows(EXPECTED)
    dup = next(r for r in docs if r["file"] == "R-04.pdf")
    dup["flags"], dup["status"] = "", "OK"
    clean = next(r for r in docs if r["file"] == "R-02.pdf")
    clean["flags"], clean["status"] = "duplicate_document", "Needs review"
    t = run(docs)["totals"]
    assert t["flags_caught"] == 10 and t["false_alarms"] == 1


def test_missing_document_fails():
    docs, _ = cr.perfect_rows(EXPECTED)
    docs = [r for r in docs if r["file"] != "C-02.pdf"]
    scored = run(docs)
    assert by_file(scored, "C-02.pdf")["problems"] == ["not in the sheet"]


def test_formats_from_a_sheet_are_accepted():
    docs, _ = cr.perfect_rows(EXPECTED)
    row = next(r for r in docs if r["file"] == "R-01.pdf")
    row["total"] = "PKR 6,265.80"
    row["doc_date"] = "2026-10-05T00:00:00"
    row["issuer"] = "  BRIGHT  BASKET GROCERS "
    row["flags"] = ""
    assert by_file(run(docs), "R-01.pdf")["passed"]


def test_wrong_line_item_is_reported():
    docs, lines = cr.perfect_rows(EXPECTED)
    lines = copy.deepcopy(lines)
    first = next(l for l in lines if l["file"] == "INV-01.pdf")
    first["amount"] = 999.0
    problems = by_file(run(docs, lines), "INV-01.pdf")["problems"]
    assert problems == ["line 1: amount differ"]
