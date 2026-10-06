// Code node "Document rows": one sheet row per document, in the column order of docs/output_contract.md.
return $input.all().map((item) => ({ json: item.json.row }));
