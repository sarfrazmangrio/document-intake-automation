// Code node "Run log rows": tokens, cost and any extraction error for each document.
return $input.all().map((item) => ({ json: item.json.log }));
