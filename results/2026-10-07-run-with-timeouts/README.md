# Full run that hit timeouts (7 Oct 2026)

All 30 test documents, with the first version of the core flow.

- 23 of 30 documents passed.
- The other 7 never reached Claude's reading step. Six calls timed out after 120 seconds and one connection dropped ("socket hang up"); `run_log.csv` has the errors.
- Every document Claude did return was correct: all 23 passed with every field and line item right.
- Cost: USD 0.1108 for the 23 documents that went through.

Cause: n8n's HTTP Request node "batching" option staggers the start of each call by a second but doesn't wait for the previous call to finish, so up to 30 uploads were in flight at once.

Fix, in the next version of the workflow:
- a loop sends one document at a time, so each call finishes before the next starts;
- up to 3 tries per document, 5 seconds apart, with a 60-second timeout;
- a document that still fails becomes an `extraction_failed` row, as before.

The fix was tested in n8n 2.42.3 against a stand-in API that failed some calls on purpose. Documents that failed once were retried and passed; one that always failed was tried 3 times and then marked `extraction_failed`.
