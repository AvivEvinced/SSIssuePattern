# Site Scanner: logging gaps for the backend team

**Source:** a support-ticket root-cause analysis (279 Zendesk tickets) plus live Coralogix research on the site-scanner, admin and front services (≈330 queries, Nov 2026; back-test May–Oct 2026).
**Goal:** let support and the automated investigator pinpoint the cause of a crawl or scan problem from the logs alone.
**Sub-issue ids** (A1, B3, …) refer to the root-cause taxonomy in `scripts/taxonomy.py`.

## P0 — security (fix first)

| # | Finding | Where | Ask |
|---|---|---|---|
| S1 | The page-interaction error JSON logs the **typed value in clear text** (`element.text`). A username was observed. A failing password step would log the password. | crawl-worker / scan-worker, "encountered error while running a function with timeout" → `$d.error.message` | Redact typed values for TYPE_TEXT steps; log only length or `***`. Purge existing logs per policy. |
| S2 | The full crawler/scan config is logged as `crawler config is: {…}`, **including login credentials**. This happens once per page in scan-worker (~100k lines a week). | crawl-worker, scan-worker | Remove credentials from the dump, or replace it with the credential-free summary in P1-6. |

## P1 — events that unlock several sub-issues

| # | Missing event | Unlocks | Suggested fields | Where |
|---|---|---|---|---|
| 1 | **Per-page document fingerprint** | A2 challenge, A3 soft block, C6 JS-only navigation, C5, A1 | page title, HTML bytes, DOM node count, **links extracted**, selected response headers (server, cf-ray, akamai/x-datadome, content-type) | crawl-worker, scan-worker (per visited page) |
| 2 | **End-of-job summary**, one structured line per crawl/scan, always emitted (including 0-page crawls) | A1, A2, A5, D1, C1, C2, C4, C6, E3 | jobId, propertyId, tenant, status, duration, visited / failed / filtered counts, **counts by document HTTP status**, by failure type, by reject reason; egress mode and IP, user agent sent | crawl-worker / scan-worker; or extend METRIC_EVENT CrawlSummary (today: status + totalUrlsCount only, DONE even when 0 URLs) |
| 3 | **Login outcome event** after the interaction script | B1 MFA, B2 selector, B3 credentials, B4 multi-step, B5 session, A1 on the login page | LOGIN_OK / LOGIN_FAILED, failed step index and type, **reason the element lookup failed** (missing / hidden / detached / timeout), post-submit landing URL path, HTTP status of the login-page navigation | PageInteractionPlugin |
| 4 | **Egress at job start** | A4 static IP | resolved useStaticIp, egress pool, **public egress IP**, node pool | crawl-worker, scan-worker |
| 5 | **Per-page status lines in the fast-pool crawl path** (useStaticIp=false crawls log no page statuses) | A1, A4, A5 | same "http status code is" line as the static path | crawl-worker fast path / link extractor |
| 6 | **Credential-free scope config line** at job start | C1, C2, C3, C7 | allowed domains, include/exclude regexes, language whitelist, page cap, grouping rules, mode (crawl/list), parallelism, speed tier, **user agent actually sent** (A6) | crawl-worker |
| 7 | **Which rule rejected a URL**: domain vs include-regex vs path (today the same text, "final url not included in whitelist", covers all of them) | C1 vs C2 | rule type + rule value | crawl-worker |

## P2 — precision and alerting

| # | Gap | Unlocks | Ask |
|---|---|---|---|
| 8 | Document HTTP 4xx/5xx is logged at **INFO**, and the blocked page counts as a success | A1, A5 alerting | Log non-2xx document status at WARN, or mark the page failed (failure type HTTP_STATUS) |
| 9 | "Job failed due to timeout/failure" carries no underlying cause | E3 vs E1 | Include the phase and the root exception |
| 10 | The 502/504 returned to the browser is not logged; slow calls appear only as "took N millis" | E5, F3 | Access log with status and latency per API call, with request_uri |
| 11 | The 300000 ms handleRequest cap line has no URL, request id or step | B4, D1 | Add url, request_id, current step |
| 12 | No network state at OPEN_PAGE_TIMEOUT | D1 vs tarpit block | Pending request count, last response status/time, bytes received |
| 13 | No session id per request; no warning when several workers log in at once | B5 | sessionId/podId per request; WARN on concurrent logins for one property |
| 14 | The next-run line has no time zone | E2 | Add the property time zone and the UTC value |
| 15 | Certificate errors are ignored silently | A9 | WARN when a certificate error is bypassed |
| 16 | Export row-limit rejection and Jira/ADO integration calls are not logged | F1, F4 | Log the rejection reason and the integration call outcome |

## Bugs noticed while reading the logs (for triage)

- `ScanResultExportPoller.onFailed()` logs "this reflects a … bug, please fix!" Failed exports are not reported to the user.
- Content-type check appears case-sensitive: "content type text/HTML; charset=utf-8 is not allowed" (110 in 7 days).
- `ENGINES_PLUGIN_ERROR` with ENOENT / ENOTEMPTY / zlib (~1,000 a week) looks like a race when the worker extracts the engine package. The customer page is not involved.
- The interaction plugin logs `element: X, exists: true` and then, 13–160 ms later, `No element found for selector: X`. The existence check is inconsistent with the action.
- A crawl with 0 URLs reports CrawlSummary status DONE, not FAILED.
- GCS 429 on repeated rewrites of the same `crawl.json` object (≈450 a day from 2 scans).
