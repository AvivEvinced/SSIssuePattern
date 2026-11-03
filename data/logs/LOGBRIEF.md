# Brief: Site Scanner log research in Coralogix

Goal: build a classification of Site Scanner issues by HOW THEY APPEAR IN LOGS, to complement an existing
root-cause taxonomy (scripts/taxonomy.py — read the SUB dict: families A–H, sub-issue ids like A1, B2, E3).
The end use is Coralogix patterns that an agent ("the investigator") uses to diagnose tickets and suggest fixes,
and a tree that support people can understand.

Tool: Coralogix MCP `mcp__Coralogix__query_dataprime` (load with ToolSearch "select:mcp__Coralogix__query_dataprime").
Known facts (verified):
- Apps/subsystems: site-scanner/{crawl-worker, scan-worker, scrape-server, scrape-webapp, front-webapp, admin-webapp, csv-worker},
  admin/admin-server, front/front-server. Logs retained back to at least 2026-05.
- Message field: $d.message; level $d.level; severity $m.severity (Info/WARNING/ERROR...); template id $m.templateid
  (Coralogix log template — great for counting a pattern). crawl-worker has $d.context.url, $d.context.request_id;
  k8s job in $d.resource.attributes['k8s.job.name']. JVM services (admin/front) embed MDC tags in the message text,
  e.g. "[opId=..] [jobId=..] [scanId=..] [tenancyName=..] [propertyId=..] [propertyName=..] [ScanService.kt:214] Scan with ID=.. state changed from RUNNING to FAILED".
  Inspect raw records (limit 2-3) to discover other structured fields (error type, http status, exception JSON, etc.).
- DataPrime syntax tips: no `in [...]` operator — use `||`. `any_value(x)` works in aggregate. Regex match: `$d.message ~ 'text'` or `matches(...)`.
  Free-text over weeks times out (60s): keep wide scans to <=1 day, or filter by application+subsystem+templateid first.
  `groupby ... aggregate count() as n, any_value($d.message:string) as sample` is the workhorse.
- Top WARN/ERROR templates last week (subsystem: message): crawl-worker "not handling request ... max number of successful visits was reached" (627k, benign cap),
  crawl-worker "got error while scraping" (107k), crawl-worker "encountered error while running a function with timeout. retry count: 0" (107k),
  crawl-worker "all attempts to scrape url had failed" (38k), crawl-worker "content type: application/pdf doesn't match ...",
  scan-worker same scraping/timeout errors, scan-worker "got error while running plugin. is plugin mandatory: true",
  scan-worker "got error while trying to upload file to cloud", scrape-server "scan page <url> failed, scan id is <id>",
  admin/front "failed to create entity for property with id: ..", "duplicate key ... JobEntity already exists" (scheduler?),
  front "poll request failed", admin-webapp "failed to generate CSV for scan .. (poller timeout)", "Failed to send crawl completion email",
  front "ViewsController.get failed (NotFoundException:could not find view)", "ScanController.get failed (NotFoundException:Scan could not be found)".
  The detail (exception type, http code, selector) is often in the record payload beyond $d.message — inspect it.
- Signatures reported in Zendesk threads (to verify/locate): "final url not included in whitelist", "http status code is: 403",
  "No element found for selector", "OPEN_PAGE_TIMEOUT", "FAILED_TO_RUN_ENGINES", "Function: gotoURL execution took more than 40000 miliseconds",
  "bound handleRequest execution took more than 300000", "LimitExceededException", "Failed running create crawl request",
  "HikariPool-1 - Connection is not available", "passed its timeout, marking it as FAILED", "JobScheduler ... next schedule job time",
  "state changed from RUNNING to FAILED", "kubernetes job failed", "browser was opened successfully. version: Chrome/",
  "finished waiting for page to stabilize. final url after redirections", "[browser] [error] Failed to load resource: the server responded with a status of 4xx".

SECURITY: logs can contain customer URLs/tenant names (OK to cite briefly) but NEVER copy credentials, tokens, cookies,
auth headers, passwords, emails.

Output (in data/logs/): `<area>.md` (human-readable findings) and `<area>.json` — an array of signatures:
{ "sig_id": "short_snake_case", "where": "subsystem(s)", "stage": "schedule|dispatch|crawl-navigation|crawl-discovery|login|scan-page|engine|post-processing|export|ui-api",
  "message_pattern": "exact text or regex", "templateid": ["..."], "dataprime": "ready-to-run query",
  "key_fields": ["fields that carry the detail, e.g. error type, status code, url, scanId"],
  "volume": "approx count/day or per week (state the window)", "noise": "is it benign/background? how to tell signal from noise",
  "maps_to_sub_issues": ["A1","C2",...], "discriminative": "high|medium|low — does it pin one sub-issue or many?", "notes": "..." }
Final reply (<500 words): key findings, surprises, and any sub-issue for which you found NO log evidence.

## Working rules (v2 — mandatory)
- WRITE INCREMENTALLY: create `<area>.md` immediately, and append findings after every 3–4 queries. Rewrite `<area>.json`
  whenever you add a signature. If you are stopped, whatever is on disk must be usable.
- BUDGET: about 25 Coralogix queries in total. Prefer aggregate queries (groupby + count + any_value sample) over raw dumps;
  when you inspect raw records use limit 2 and `choose` only the fields you need, to keep outputs small.
- Time windows: 1–6 hours for free-text/regex scans; up to 1 day when filtered by application+subsystem+templateid.
  If a query times out, halve the window — don't retry the same query.
- Hint from the first run: scrape-error records carry a structured `errorDescription` (and probably an error type/code field)
  besides $d.message — find it with one raw record and group by it.
