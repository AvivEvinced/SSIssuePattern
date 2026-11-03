# Back-test: do real Site Scanner tickets show up in Coralogix logs?

Method: for each ticket (data/backtest_candidates.txt), locate the property/tenant (thread dump), query a 1–2 day
window before the ticket date in Coralogix (DataPrime), record evidence, and judge (a) signal exists,
(b) agrees with root-cause sub-issue (scripts/taxonomy.py SUB), (c) minimal detecting query.
Machine-readable results: backtest.json.

## Per-ticket results

### Schema notes discovered while back-testing
- crawl-worker URL field moved: July 2026 `$d.url` (+ `$d.requestId`); Oct 2026 `$d.context.url`. Use
  `($d.context.url:string ~ X || $d.url:string ~ X)` for queries spanning months.
- Coralogix templateids are re-minted when the service redeploys (same message, different id in Jul vs Oct). Match on message text, not templateid, in reusable patterns.
- HTTP status of the visited page is an **Info** line `http status code is: <n>`; a 403 seed is never WARN/ERROR. Severity filters miss blocks.
- Crawl terminal reason line (Oct): `CRAWL with id <id> failed due to <CODE> - {details}` (codes seen: INTERNAL_ERROR "could not scrape page", DNS_ERROR_COULD_NOT_FIND_URL).
- `[browser] …` console lines (CSP reports, JSON-schema dumps) are huge: exclude them (`!($d.message ~ '^\[browser\]')`) or `substr()` the sample.
- Ticket date is often before the run that matters (customer re-runs for evidence); query from the run date named in the thread.

### #2903 A1 starz.ca (Bell) — YES / agrees
07-27 run: 3 jobs, seed `http status code is: 403` + `[browser] Failed to load resource … 403` + `not including url in result url set. reason: final url not included in whitelist`; www.starz.ca 200 but 1 page. Exactly the thread evidence.

### #3340 A6 investor.capitalone.com — PARTIAL / family-level only
~10-09: 5 crawls die on seed: `got error while scraping net::ERR_HTTP2_PROTOCOL_ERROR` → 100 timeout retries → `all attempts to scrape url had failed` → `CRAWL … failed due to INTERNAL_ERROR`. ~10-14 (after UA override) 2 jobs crawl 40+ pages. Nothing in logs names the UA; `browser … version: Chrome/126` is logged even though UA sent was Chrome/65. Looks like A1/A5 tarpit.

### #3301 A1 myprepaidcenter.com (Bell, DataDome) — YES / agrees, with a trap
`[browser] … status of 405` on the login page, then `No element found for selector: #usernameText` and
`CRAWL … failed due to PAGE_INTERACTION_PLUGIN_ERROR`. Without the 405 line this reads as B2. Rule: check for 403/405 resource errors on the same job before calling a selector problem.

### #3228 E3 Salesforce — YES / agrees
At the scheduled run (09-01 07:00 UTC): scrape-server `HikariPool-1 - Connection is not available … (total=10, active=10, idle=0, waiting=7)` x33 in 15 min; admin-server and front-server `Failed running create crawl request for URL set with ID=…` (Error); admin-server `METRIC_EVENT {eventType: CrawlSummary, propertyId, status: FAILED}`. Nothing in the 2 days before the ticket date: you have to query the failing run's time.
**New find:** `METRIC_EVENT` JSON lines (CrawlSummary on admin/front-server, scan.page.complete on scrape-webapp) carry propertyId/taskId/scanId/status, so they are a structured entry point.

### #2192 E4 NatWest concurrent-scan limit (May) — NO
No `LimitExceededException`, no `natwest` text, and no `state changed from` lines in admin-server on 05-05; crawl-worker
had no records in a sampled May hour. **Early-May 2026 logs are too thin to back-test**: admin-server is mostly poller chatter
("2 / 27 polls need to run…"). Treat tickets before ~June as untestable.

### #2371 B2 bell.jasperwireless.com — YES / agrees (high precision)
`encountered error while running a function with timeout … Exception: {"url": ".../login.jsp", "message": "Failed to execute 'querySelector' on 'Document': '.input type="submit"' is not a valid selector.", "element": {"type":"CLICK_ELEMENT", "elementSelector": ...}}` → PAGE_INTERACTION_PLUGIN_ERROR. 976 `final url after redirections: …/login.jsp` over 3 jobs: the crawl never got past login. The exception payload names the interaction and the selector.

### #3198 B2 Chick-fil-A stale CLICK_ELEMENT (sc- hash classes) — PARTIAL / not attributable
At the discovery time (09-03 15:55) the interaction runs (`current page url: https://order.chick-fil-a.com/location`, `element: #input-1, exists: true`)
but no selector-failure text shows in the top templates, only generic `function with timeout` errors. A stale selector can fail *quietly* and end DONE/0 URLs.
Check `CrawlSummary totalUrlsCount=0` in admin-server, then the per-job interaction lines. Side find: malformed relative link → `…chick-fil-a.com/https:/order…` 404 pages.

### #2914 A5 NatWest 429 rate limiting — NO (run outside window)
In 07-21..07-28 only 7 `http status code is: 200` lines for any natwest URL (a tylbynatwest.com property). The 429-heavy run from the thread was earlier.
Detector to use once the date is known: per-day/per-job histogram of `http status code is: <n>` (share of 429), plus `ERR_HTTP2_SERVER_REFUSED_STREAM`.

### #3420 A2 community.environicsanalytics.com (Zendesk/Cloudflare) — YES (block) / sub-issue not pinned
3 jobs: `http status code is: 403` + browser 403 + `successfully visited 1 pages so far`; redirect to Zendesk `/auth/v3/signin`. No Cloudflare marker in logs, so A2 and A1 look the same.

### #3248 D1 Ulta heavy-page timeouts — NO (run not in window)
Crawl only shows the page cap (`max number of successful visits was reached`); scan-worker had one healthy page.

### #3293 D2 Chick-fil-A huge-DOM locator — PARTIAL
`SCAN with id … failed due to FAILED_TO_RUN_ENGINES - {"details":"could not run analysis"}` is a clean per-page signal with `$d.context.url` (133 in ~1.5 days, mostly Salesforce trailblazer profiles = background), but the locator URL didn't surface in budget.

### #2751, #2752, #2755, #2760, #2764 E1 June outage — YES / agrees (volume signal)
| day | crawl-worker lines | scan-worker lines (errors) | scrape-server lines |
|---|---|---|---|
| 06-24 | 644k | 395k (861) | 112k |
| 06-26 | 71k | **5.3k** | 200k |
| 06-27 | 123k | 272k (**26.3k**) | 223k |
| 06-28 | 584k | **5.2k** | 253k |
| 06-29 | **2.23M** (catch-up) | 1.06M | 492k |
Workers starve while scrape-server is steady → a volume/ratio alert, not a message pattern. The admin-server `state changed from` lines and the `METRIC_EVENT` summaries don't exist in June yet.

## Summary (budget exhausted at ~34 queries; 12 test cases covering 16 tickets)

| ticket | sub | evidence | agrees with sub-issue |
|---|---|---|---|
| #2903 | A1 | yes | yes |
| #3301 | A1 | yes | yes (trap: looks like B2) |
| #3340 | A6 | partial | no (family A only) |
| #3420 | A2 | yes | no (A1/A2 indistinguishable) |
| #2914 | A5 | no (run outside window) | na |
| #2371 | B2 | yes | yes (selector named in exception) |
| #3198 | B2 | partial | no (stale selector fails quietly) |
| #3248 | D1 | no (run outside window) | na |
| #3293 | D2 | partial | na |
| #3228 | E3 | yes | yes |
| #2751×5 | E1 | yes | yes (volume anomaly) |
| #2192 | E4 | no (May logs too thin) | na |

**Hit rate:** some log evidence in 8/12 cases (5 yes + 3 partial; 12/16 tickets when the 5 outage tickets count separately).
Sub-issue pinned correctly in 5/12. Every miss was a "couldn't find the run" problem (no date, before ~June, or another run), not "the run left no trace".

**Well visible:** A1 hard block (403/405 + 1 page + whitelist drop), B2 *malformed* selector (exception JSON names the selector),
E3 dispatch/pool exhaustion (Hikari + 'Failed running create crawl request'), E1 outage (volume collapse).
**Family-only:** A2/A3/A6 (a block is visible, but no Cloudflare/Akamai/UA marker is logged; browser version ≠ UA sent).
**Poorly visible:** B2 *stale* selector (silent DONE/0 URLs), D1/D2 (detectors exist but need exact run/URL; FAILED_TO_RUN_ENGINES has heavy background), E4 (no May data), A5 (needs per-job status histogram on the right run).

**Practical rules for the investigator:**
1. Anchor on the failing run's time from the thread or app (CrawlSummary/scan id), not the ticket date. The 1–2 day pre-ticket window found nothing in 4 cases.
2. Match message text, not templateid (ids re-minted per release). URL field: `$d.url` (≤Jul) vs `$d.context.url` (Sep+).
3. Status codes are Info, so never filter by severity for blocks.
4. A login selector failure plus a 403/405 resource error on the same job means A1, not B2.
5. Avoid grouped regex alternation in `~` (returned 0 rows twice); use separate `~` terms joined by `||`.
