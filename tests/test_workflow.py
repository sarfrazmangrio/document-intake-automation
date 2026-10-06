"""The n8n workflow file must match its sources, and its checks must catch every planted problem."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_workflow  # noqa: E402
import check_results as cr  # noqa: E402


def test_workflow_file_matches_sources():
    on_disk = json.loads(build_workflow.OUT.read_text(encoding="utf-8"))
    assert on_disk == build_workflow.build(), "run: python tools/build_workflow.py"


def test_workflow_settings():
    wf = build_workflow.build()
    nodes = {n["name"]: n for n in wf["nodes"]}
    http = nodes["Claude: extract fields"]
    assert http["onError"] == "continueRegularOutput"
    assert http["parameters"]["options"]["batching"]["batch"]["batchSize"] == 1
    assert nodes["Read intake files"]["parameters"]["fileSelector"].startswith("/files/intake/")
    assert all(n["parameters"]["fileName"].startswith("/files/output/")
               for n in wf["nodes"] if n["parameters"].get("operation") == "write")


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_checks_code_on_a_perfect_extraction(tmp_path):
    subprocess.run(["node", str(ROOT / "tools" / "simulate_checks.mjs"), str(tmp_path)], check=True, capture_output=True)
    expected = cr.load_expected(cr.DEFAULT_EXPECTED)
    docs = cr.read_csv(tmp_path / "documents.csv")
    scored = cr.score(expected, docs, cr.read_csv(tmp_path / "lines.csv"))
    assert all(r["passed"] for r in scored["results"]), [r for r in scored["results"] if not r["passed"]]
    t = scored["totals"]
    assert t["flags_caught"] == t["flags_expected"] == 11 and t["false_alarms"] == 0
    failed = next(r for r in docs if r["file"] == "ZZ-failed.pdf")
    assert failed["status"] == "Needs review" and failed["flags"] == "extraction_failed"
    log = next(r for r in cr.read_csv(tmp_path / "run_log.csv") if r["file"] == "ZZ-failed.pdf")
    assert "529" in log["error"]


def test_only_present_scores_part_of_the_test_set(tmp_path):
    expected = cr.load_expected(cr.DEFAULT_EXPECTED)
    docs, _ = cr.perfect_rows(expected)
    cr.write_csv(tmp_path / "docs.csv", [r for r in docs if r["file"] in ("INV-01.pdf", "C-02.pdf")], cr.DOC_COLUMNS)
    assert cr.main(["--documents", str(tmp_path / "docs.csv"), "--only-present"]) == 0
    assert cr.main(["--documents", str(tmp_path / "docs.csv")]) == 1
