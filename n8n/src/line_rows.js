// Code node "Line rows": one sheet row per printed line item.
return $input.all().flatMap((item) => item.json.lines.map((line) => ({ json: line })));
