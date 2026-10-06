"""Assemble the n8n workflow file from the Code node sources in n8n/src.

    python tools/build_workflow.py

Writes n8n/document_intake_core.json, which you import into n8n
(Workflows > Create > ... > Import from file). Edit the JavaScript in n8n/src, not in the JSON.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "n8n" / "src"
OUT = ROOT / "n8n" / "document_intake_core.json"

INTAKE = "/files/intake/*.{pdf,PDF,jpg,JPG,jpeg,JPEG,png,PNG}"
OUTPUT_DIR = "/files/output"


def node_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"document-intake/{name}"))


def node(name, type_, version, x, y, parameters, **extra):
    return {"id": node_id(name), "name": name, "type": type_, "typeVersion": version,
            "position": [x, y], "parameters": parameters, **extra}


def code(name, x, y, source):
    return node(name, "n8n-nodes-base.code", 2, x, y, {"jsCode": (SRC / source).read_text(encoding="utf-8")})


def build() -> dict:
    nodes = [
        node("Run on the intake folder", "n8n-nodes-base.manualTrigger", 1, 0, 300, {}),
        node("Read intake files", "n8n-nodes-base.readWriteFile", 1.1, 220, 300,
             {"fileSelector": INTAKE, "options": {}}),
        code("Build Claude requests", 440, 300, "build_requests.js"),
        # One document per pass, so each call finishes before the next starts.
        node("One document at a time", "n8n-nodes-base.splitInBatches", 3, 660, 300, {"batchSize": 1, "options": {}}),
        node("Claude: extract fields", "n8n-nodes-base.httpRequest", 4.2, 880, 440, {
            "method": "POST",
            "url": "={{ $json.api_url }}",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.request) }}",
            "options": {"timeout": 60000},
        # up to 3 tries, 5 seconds apart; a call that still fails becomes an "extraction_failed" row
        }, retryOnFail=True, maxTries=3, waitBetweenTries=5000, onError="continueRegularOutput"),
        code("Checks and rows", 1100, 300, "checks.js"),
    ]
    outputs = [("Document rows", "document_rows.js", "documents.csv", 120),
               ("Line rows", "line_rows.js", "lines.csv", 300),
               ("Run log rows", "run_log_rows.js", "run_log.csv", 480)]
    connections = {
        "Run on the intake folder": {"main": [[{"node": "Read intake files", "type": "main", "index": 0}]]},
        "Read intake files": {"main": [[{"node": "Build Claude requests", "type": "main", "index": 0}]]},
        "Build Claude requests": {"main": [[{"node": "One document at a time", "type": "main", "index": 0}]]},
        # output 0 ("done") carries every reply once the loop ends; output 1 ("loop") the next document
        "One document at a time": {"main": [[{"node": "Checks and rows", "type": "main", "index": 0}],
                                            [{"node": "Claude: extract fields", "type": "main", "index": 0}]]},
        "Claude: extract fields": {"main": [[{"node": "One document at a time", "type": "main", "index": 0}]]},
        "Checks and rows": {"main": [[{"node": name, "type": "main", "index": 0} for name, *_ in outputs]]},
    }
    for name, source, file_name, y in outputs:
        convert, write = f"{name}: CSV", f"Save {file_name}"
        nodes += [
            code(name, 1320, y, source),
            node(convert, "n8n-nodes-base.convertToFile", 1.1, 1540, y,
                 {"operation": "csv", "options": {"fileName": file_name}}),
            node(write, "n8n-nodes-base.readWriteFile", 1.1, 1760, y,
                 {"operation": "write", "fileName": f"{OUTPUT_DIR}/{file_name}", "dataPropertyName": "data", "options": {}}),
        ]
        connections[name] = {"main": [[{"node": convert, "type": "main", "index": 0}]]}
        connections[convert] = {"main": [[{"node": write, "type": "main", "index": 0}]]}
    return {"name": "Document intake: core flow", "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1"}, "pinData": {}}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", OUT.relative_to(ROOT))
