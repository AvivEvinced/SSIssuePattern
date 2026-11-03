# access_auth — log research (families A, B, C1/C2/C4/C6)

Status: complete (26 queries). Windows: mostly 2026-10-27..11-03 (7d) and 2026-11-01/02 (6–12h).

## 1. "not including url in result url set" — all reasons (crawl-worker + scan-worker, 2026-10-27..11-03, 7 days, all envs)

Message format: `not including url in result url set. reason: <reason>`; URL is NOT in the message, it is in `$d.context.url`
(crawl-worker), job in `$d.resource.attributes['k8s.job.name']`. Severity Info. Templates are shared across reasons
(3396f2f8-9cb5-11f1-92dd-be037f26c345, 30b9ff5c-aaad-11f1-af66-ea6a85ee653a, f1a281ca-5437-11f1-81cb-367b02696c2b,
504112cc-3f87-34ad-ae7f-98c12531cd93 in crawl-worker; 309b8db6-d4eb-11f1-b35e-86881614271e, bf53e91a-b428-11f1-8c6c-8ea58dd96437 in scan-worker),
so group by an extracted reason, not by templateid.

| reason (crawl-worker unless noted) | 7d count | meaning / sub-issue |
|---|---|---|
| final url is included in ... (message truncated in the log itself; = blacklist) | 129,745 | blacklist hit (social-media default blacklist etc.) — mostly benign; C3/C1 only if the customer's exclude is too wide |
| final url was already visited. this is most likely due to a redirection | 57,791 (+741 scan-worker) | redirect collapses onto a visited URL; a burst in a single job = many URLs redirecting to the same page (C4 error/login redirect, A7 geo redirect, B5 session -> /login) |
| sanitized url was already visited | 17,843 | dedupe after normalisation (C5) — benign |
| content type application/pdf / image/* / audio / video / binary / font / text/calendar is not allowed | ~20.6k | benign content filter |
| **content type text/HTML; charset=utf-8 is not allowed** | 110 | suspected bug: content-type check is case-sensitive (allowedContentTypes = ["text/html","text/plain"]); a site sending `text/HTML` loses all pages -> 0-page crawl lookalike of C1/C6 |
| **final url not included in whitelist** | 4,819 (+58 truncated) | **C2** (redirect target outside whitelist) or C1 (include regex matching nothing) |
| max number of successful visits was reached | 2,279 | page cap — benign |
| language is not included in whitelist | 1,119 | languageWhitelist (locale filter) — C1 when it hits every page |
| matching grouping rule <regex> is full | ~1.9k | grouping maxSamples reached — C5 |

Notes:
- The logs carry BOTH environments: always filter `$d.resource.attributes.environment == 'production'` (dev crawls e.g. https://goo.com show up).
- C2/C1 signal = ratio, per k8s job, of "final url not included in whitelist" to "request was handled successfully"; a job whose only outcome is this reason is a C2/C1 0-page crawl.
- The scan-worker "crawler config is: {...}" line (Info) dumps the whole crawler/scanner config: seedUrls, whitelist, blacklist, languageWhitelist,
  allowedContentTypes, puppeteerArgs incl. `--user-agent=... Chrome/112.0.5615.49` (default UA), extraHeaders, openPageTimeoutSec, parallelNum,
  plus pubsubMessageMetadata with tenancyName/propertyName/propertyId/scanId. Key line for A2/A6/C1/C2 diagnosis (check the regexes against the final URL).
- k8s node name reveals the node pool: e.g. `gke-prod-mon-cluster-crawls-pool-stat-...` (static-IP pool?) — see section 2.

## 2. Infrastructure / egress (A4)

- 2026-11-02 00–06 UTC, production: ALL crawl-worker logs come from node pool `prod-mon-cluster-crawls-pool-stat*` (10 jobs) and all scan-worker
  from `prod-mon-cluster-scans-pool-stati*` (14 jobs). The "-stat"/"-static" pool name is the only egress hint in logs: field
  `$d.resource.attributes['k8s.node.name']`. No log line prints a public/egress IP ("public ip", "egress", "static ip", "use-static-ip": 0 hits).
- Fast tier: no `production_crawl_link_extractor` Cloud Function appears in gcp/logs (7d; only production_scan_result_joiner/indexer/sink and
  production_scan_failure_result_indexer). So a fast-tier crawl is visible in Coralogix only by ABSENCE of a crawl-worker k8s job for the crawl.
  A4 cannot be confirmed positively from logs; needs Retool flag (scan.use-static-ip / url-set.use-static-ip).

## 3. Per-URL failure lifecycle in crawl-worker (detail lives in sibling lines, NOT in structured fields)

"got error while scraping" (Warning, 08e48cee-9b45-11f1-a536-52ef7929d954) has no error fields at all (no errorDescription/errorType/code in this
service — the brief's hint applies elsewhere). The per-request story is reconstructed with `$d.context.request_id`:
```
browser was opened successfully. version: Chrome/126.0.6478.126        (d1d6dbd8-9c4f-11f1-8905-329537c5ee79)
going from url: about:blank to url: <url>                               (927a9d2a-a5dd-11f1-bc89-12ad895683e4)
timeout has passed, closing requests browser/page                       (d1e9f484-9c4f-11f1-8905-329537c5ee79)
encountered error while running a function with timeout. retry count: N (9b5233c6-9b48-11f1-bb8a-4206745c74cb, Error)
got error while scraping                                                (08e48cee-..., Warning)
got error while running scrape. retry count: 0..2                       (d2cb6716-9c4f-11f1-8905-329537c5ee79)
error going to url: <url> current url: <url>                            (927a9d2a-..., same template as "going from url")
all attempts to scrape url had failed                                   (9b5222f0-9b48-11f1-bb8a-4206745c74cb, Error)
CRAWL with id <crawlId> failed due to <REASON> - {json}                 (121523ec-9fa9-11f1-94dc-5ee20c2e67e1, Info)  <-- THE classifier line
failed to scrape url                                                    (d20e090a-9c4f-11f1-8905-329537c5ee79)
```
"error going to url: X current url: Y" — when Y != X it shows where the browser ended (redirect target: login, /500, geo page, challenge) -> A7/C4/B5.

### "<KIND> with id <id> failed due to <REASON>" — 2026-11-02 (1 day, production, crawl-worker)
| reason | n | jobs | maps to |
|---|---|---|---|
| OPEN_PAGE_TIMEOUT | 5,475 | 6 | A1/A5 (WAF tarpit / rate limit) or slow site (performance area); one job with ~all URLs = block |
| INTERNAL_ERROR {"details":"could not scrape page","error":{}} | 10 | 5 | unspecific |
| PAGE_INTERACTION_PLUGIN_ERROR {"error":{"url":..,"message":"No element found for selector: <sel>"}} | 2 | 2 | **B2** (also B4/A7 if redirect) |
| DNS_ERROR_COULD_NOT_FIND_URL | 1 | 1 | C4 (seed unreachable) |

### Same line, 7 days (10-27..11-03, all envs), both workers
CRAWL OPEN_PAGE_TIMEOUT 30,788 (60 jobs) · SCAN OPEN_PAGE_TIMEOUT 13,545 (34) · CRAWL "failed due to undefined" 4,435 (8 jobs — reason lost)
· SCAN PAGE_INTERACTION_PLUGIN_ERROR 560 (6; e.g. kiddom login form selector) · SCAN PLUGIN_TIMEOUT 421 (engine) · SCAN FAILED_TO_RUN_ENGINES 201
· CRAWL INTERNAL_ERROR 170 · DNS_ERROR_COULD_NOT_FIND_URL 25 crawl / 24 scan · CRAWL PAGE_INTERACTION_PLUGIN_ERROR 18.
**No HTTP/WAF-specific enum exists** — a block appears either as OPEN_PAGE_TIMEOUT or as a "successful" page whose status is 403.

## 4. HTTP status (A1/A5/A8/B5/C4)

Main-document status IS logged per visited page: `http status code is: <NNN>` (Info). Templates: crawl-worker 33948266-9cb5-11f1-92dd-be037f26c345 /
30b9ff5c-aaad-11f1-af66-ea6a85ee653a; scan-worker f8cdaba4-9af1-11f1-a148-2267a7afc7c0 / b9b9265a-9cf4-11f1-9545-4a96456cf580.
NB: in DataPrime `~` behaved as a literal substring match here; use `$d.message.matches(/regex/)` for regex.

7d production non-200 counts (jobs): crawl-worker **403 = 34,256 (68)**, **429 = 18,506 (28)**, 202 = 6,540 (5), 404 = 4,991 (138), 502 = 256, 500 = 141,
405 = 17, 401 = 1, 301/307 = 14; scan-worker 404 = 15,319 (219), **403 = 2,885 (60)**, **429 = 883 (18)**, 202 = 6,234 (10), 401 = 33, 405 = 25, 302 = 1.
- 403 in crawl dominates the access-block picture (A1). 429 concentrated in fewer jobs (A5).
- 202 in 5–10 jobs with thousands of hits: suspicious — Akamai/Cloudflare bot-manager interstitials often return 202 => A2 candidate (verify page title).
- 30x almost never logged (redirects are followed) => A8 (redirect loop) has no direct status signal; look for "net::ERR_TOO_MANY_REDIRECTS" instead.
- `[browser] [error] Failed to load resource: ... status of NNN` (scan-worker f8cca772-9af1-11f1-a148-2267a7afc7c0, crawl-worker d2ccaefa-9c4f-11f1-8905-329537c5ee79)
  is sub-resource noise (6h: 401 = 6,467 in scan-worker) — low value alone.

## 5. Browser version vs. user agent (A6, A2)

- `browser was opened successfully. version: Chrome/<v>` (crawl-worker d1d6dbd8-9c4f-11f1-8905-329537c5ee79): 7d production = 340,001 lines, 429 jobs,
  **one value only: Chrome/126.0.6478.126**. Not logged by scan-worker. So the real engine is 126 — the brief's "Chrome 65" is NOT the browser binary.
- BUT the **user-agent string sent to sites** comes from `puppeteerArgs --user-agent=...` in the config dump ("crawler config is: {...}" / "config is: {").
  Templates: scan-worker c49b4643-71cf-06eb-70bb-dbc7e92ed491 (logged per page, ~100k/7d), crawl-worker 83edd5b6-843e-19b1-184f-239783bf17d8,
  d1042a4e-9c4f-11f1-8905-329537c5ee79, 1b292592-9cb5-11f1-92dd-be037f26c345. 7d production distribution of extracted UA (scan-worker lines, approx):
  | UA | lines |
  |---|---|
  | Chrome/112.0.5615.49 (default) | ~73k |
  | **HeadlessChrome/65.0.3312.0 ... EvincedBot** | ~19k |
  | Chrome/112 + per-customer token (allowlist token appended) | ~6k |
  | **Chrome/65.0.3312.0 ... EvincedBot** | ~4.8k |
  | Chrome/112 ... EvincedBot | ~3.6k |
  | **Chrome/65 / HeadlessChrome/65 (no EvincedBot)** | ~2.5k |
  => roughly a quarter of scanned pages still announce **Chrome 65**, often literally "HeadlessChrome" — a direct bot-manager trigger (A6, A2).
  The UA is per property (puppeteer-args), so the investigator should extract it from the config line of the scan in question.
- `"extraHeaders":{...}` non-null on ~3k lines = custom header configured (A1 mitigation in place). Do not copy header values (may contain secrets).
- Crawl-worker config UA in the same window: Chrome/112 (~380 lines), Chrome/65 (~66), HeadlessChrome/65 EvincedBot (19).

## 6. Redirect landing pages: "final url after redirections" (A7, B1, B5, C2, C4)

`finished waiting for page to stabilize. final url after redirections: <url>` — scan-worker 3cef50ea-9bb9-11f1-a182-06d4ecb7c06e (also e64ae094-a926-11f1-a56c-46e5f8be24c8),
crawl-worker 1d7318a4-c266-11f1-9dcd-7aec34e59e18. Companion lines: `successfully scraped url. final url: <url>` (crawl 7fbfe1c2-a2fe-11f1-bf8c-e60b6925021c,
scan 3d008a68-9bb9-11f1-a182-06d4ecb7c06e), `request was handled successfully. actual url visited: <url>` (crawl 1d74cf3c-c266-11f1-9dcd-7aec34e59e18, scan d6f7d568-a5f0-11f1-a3cc-0662276c4449),
`current page url: <url>` (scan 349392ac-a425-11f1-9be2-82b781e81d95, crawl 357e1a06-9cb5-11f1-92dd-be037f26c345).
Examples from 2026-11-01/02 (production):
- ulta.com: 82 final-URL lines + 488 "current page url" lines landing on `/u/login?state=...` across 3 scan jobs => authenticated session lost / every page bounced to login (**B5**, or B3 if login never succeeded).
- sky.it: crawl pages land on `/login?forward=...` (B5 / unauthenticated pages behind login).
- **sky.de: PAGE_INTERACTION_PLUGIN_ERROR with error.url = `https://www.sky.de/out-of-country.html?orig=/login`** => clean **A7 geo-block** example (login page redirected to out-of-country page, then selector missing).
- zalando: PAGE_INTERACTION_PLUGIN_ERROR at `accounts.zalando.com/authenticate?...` (B2/B4).
- salesforce/booking: URLs with `g-recaptcha-response` params — benign, not challenges.
Method: per job, share of final URLs whose path matches /login|signin|auth|sso|mfa|otp|out-of-country|404|500|error/ ; > ~50% => B5/B1/A7/C4 depending on the path.

## 7. Login / user-interaction steps (B1–B4)

| line | templates | notes |
|---|---|---|
| `starting page interaction plugin` | scan 2caf0754-9b0d-11f1-90cd-469e155b207f, crawl d0d71a86-9c4f-11f1-8905-329537c5ee79 | a login/interaction is configured for this job |
| `element: <selector>, exists: true|false, in an iframe: true|false` | crawl def45d3e-9fa8-11f1-94dc-5ee20c2e67e1, scan 2cb02f12-9b0d-11f1-90cd-469e155b207f | `exists: false` => B2 before the hard error; `in an iframe: true` hints at modal/SSO (B4) |
| `typing text in element: <selector>` | scan d7acbbc2-a50f-11f1-a1dc-7ea94cb20793 (1,323/day, 19 jobs), crawl 1811f848-b015-11f1-a58e-e23eb70a2b10 (341/day) | TYPE_TEXT step (value not logged — good) |
| `clicking element: <selector>` | crawl 1813d168-b015-11f1-a58e-e23eb70a2b10, scan 505fe544-9c1e-11f1-b6f1-1e73d54c49b3 | CLICK_ELEMENT step |
| `got error while scraping No element found for selector: <sel>` | 08e48cee-9b45-11f1-a536-52ef7929d954 (+ scan e7d97f46-d37a-11f1-a774-0ebaa524c9d0) | **B2**; 2026-11-01: crawl 82 (4 jobs), scan ~150 (3 jobs) |
| `<KIND> with id .. failed due to PAGE_INTERACTION_PLUGIN_ERROR - {"error":{"url":..,"message":"No element found for selector: .."}}` | 121523ec-9fa9-11f1-94dc-5ee20c2e67e1 (scan also 12591faa-c995-11f1-a9ee-d6d342554398) | error.url tells WHERE the browser was: login page => B2; other page => A7/B1/B4 |
| `received message: {.. "loginConfiguration": .. }` / config dumps containing TYPE_TEXT/CLICK_ELEMENT | crawl 83edd5b6-..., scan c49b4643-... | interaction script in config. **Contains credentials — never copy.** |
- `bound handleRequest execution took more than 300000` : **0 hits on 2026-11-01** (only `bound run execution took more than 120000` = engine PLUGIN_TIMEOUT). B4 timeout signature not observed in window.
- No MFA/OTP-specific line exists; B1 only inferable from final URL path (/mfa, /otp, /challenge) after login. No "wrong password"/"login failed" text found (B3 has no direct signature; it looks like B5: everything lands on the login URL).
- `parallelNum` in the crawler config (e.g. 50 for demo.evinced.com) — with login configured, >1 is a B5 risk factor.

## 8. Challenge pages / net errors (A2, A8, A9, A5)

- Page titles are NOT logged anywhere: "Just a moment", "Attention Required", "Access Denied", "you have been blocked": 0 hits in crawl/scan workers (2026-11-01, 1 day).
  A2/A3 can't be detected by title; use proxies: status 202/403 on the document, 1-page crawls, or `[browser] [error]` lines referencing
  `challenges.cloudflare.com`, `captcha.awswaf.com` (seen: booking.com AWS WAF captcha assets, 1,394/day in 10 jobs), `recaptcha`.
- `got error while scraping <net error> at <url>` — the same template 08e48cee-... sometimes carries the Chrome net error inline:
  `net::ERR_TOO_MANY_REDIRECTS` (27/day, 3 jobs, e.g. evernorth.com) => **A8**; `net::ERR_HTTP2_PROTOCOL_ERROR` (12/day) => A1/A5 (WAF resetting streams).
- `[browser] [error] Failed to load resource: net::ERR_HTTP2_PROTOCOL_ERROR` 289 crawl / 199 scan per day (sub-resources).
- ERR_CERT_*: 0 hits in the day sampled (A9 not observed; ignoreHTTPSErrors=true and --ignore-certifcate-errors are set by default, which likely masks A9 entirely).

### "got error while scraping <detail>" — 7d production breakdown
84,378 crawl / 38,864 scan lines have NO detail (bare message — detail only via the per-request sequence, usually a timeout).
With inline detail: `No element found for selector` 1,683 scan (4 jobs) + 97 crawl (8 jobs) [B2]; `net::ERR_CONNECTION_RESET` 395 crawl (5 jobs) + 22 scan [A1 WAF reset];
`net::ERR_TOO_MANY_REDIRECTS` 36 crawl (4 jobs: moo.com, evernorth.com) + 3 scan (sky.de) [**A8**]; `net::ERR_HTTP2_PROTOCOL_ERROR` 27 crawl [A1/A5];
`net::ERR_CONNECTION_REFUSED` 22 scan + 12 crawl (1 job, hcamidwest.com) [A1 IP deny]; `net::ERR_TIMED_OUT` 4; `ERR_SOCKET_NOT_CONNECTED`/`ERR_CONNECTION_CLOSED`/`ERR_FAILED` 1 each;
`Execution context was destroyed, most likely because of a navigation` 312 crawl (16 jobs) [client-side redirect — e.g. login/geo JS redirect, A7/B5 weak];
`Protocol error (Page.navigate): Cannot navigate to invalid URL` 13 scan [C1/C4 bad seed]. No `net::ERR_CERT_*` (A9 masked by ignore-certificate flags).

## 9. Crawl size / 0–1-page crawls (A2, C1, C2, C6)

- Progress counter `successfully visited <N> pages so far` (crawl-worker 1212cbf6-9fa9-11f1-94dc-5ee20c2e67e1); max N per k8s job = pages visited.
  7d production distribution of crawl jobs by max N: **0–1: 49 jobs**, 2–5: 31, 6–50: 83, 51–500: 124, 500+: 102 (389 jobs).
  => ~13% of crawl jobs end with <=1 visited page (lower bound: a crawl that visits 0 pages may never print the counter).
- `filtered out: <N> urls` (crawl-worker d1042a4e-9c4f-11f1-8905-329537c5ee79 / 1b292592-9cb5-11f1-92dd-be037f26c345) — per-page count of discovered links dropped.
  A 1-page crawl with "filtered out: 0 urls" => no links discovered => **C6** (JS navigation) or A2/A3 (challenge page has no links);
  with large "filtered out" => C1/C2 (links found but all out of scope).
- scrape-server: `page <url> in scan <id> completed. <k> scan pages finished - waiting for <M> to be completed` (81c746f6-aa4a-11f1-ba0a-6686f8ca4618)
  and `METRIC_EVENT {... "eventType":"scan.page.complete","scanTotalUrls":"<M>" ...}` (fd1575d4-c328-11f1-8921-82f195532998) give the scan's total page count M.
  scanTotalUrls = 1 => scan of a 1-page crawl.
- Decision recipe for a 0/1-page crawl job:
  1. any `http status code is: 403|405|429|202` for the seed -> A1/A5/A2;
  2. `final url not included in whitelist` / `language is not included in whitelist` for the seed -> C2/C1;
  3. `failed due to DNS_ERROR_COULD_NOT_FIND_URL` or seed status 404 / final URL /404|/500 -> C4;
  4. `failed due to PAGE_INTERACTION_PLUGIN_ERROR` -> B2 (check error.url for A7/B1);
  5. status 200, no errors, `filtered out: 0 urls` -> C6 (or A3/A2 soft block — compare UA: HeadlessChrome/65?).

## Gaps (no log evidence found)
- **A3** soft block (200 + block page): no page title/DOM-size logging -> undetectable from logs except via 1-page crawl + 200.
- **A4** static IP: no egress IP printed; prod k8s crawls all ran on `*-pool-stat*` nodes; fast tier (production_crawl_link_extractor) not present in Coralogix.
- **A9** TLS: no ERR_CERT_* (certificate errors are ignored by default flags).
- **B1** MFA: no dedicated line; only final-URL path heuristics.
- **B3** stale credentials: no "login failed / wrong password" line; looks identical to B5 (pages land on login URL).
- **B4** `bound handleRequest execution took more than 300000`: 0 hits in the sampled day.
- Challenge-page titles ("Just a moment...", "Access Denied"): not logged.
