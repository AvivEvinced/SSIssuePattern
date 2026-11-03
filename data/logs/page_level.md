# Area: page_level — per-page failures (crawl-worker, scan-worker, scrape-server/webapp)

Status: COMPLETE. Window: mainly 2026-11-02 (24h) plus a 7-day trend 2026-10-27..11-02. Today = 2026-11-03.

## Findings log

### Q1 (2026-11-02, 24h): top WARN/ERROR templates in crawl-worker / scan-worker / scrape-server / scrape-webapp
| subsystem | templateid | n/day | message |
|---|---|---|---|
| crawl-worker | 08e4a5d0-9b45-11f1-a536-52ef7929d954 | 79,563 | not handling request ... matching grouping <re> is full (benign cap) |
| crawl-worker | 08e48cee-9b45-11f1-a536-52ef7929d954 | 17,310 | got error while scraping (WARN, no detail field) |
| crawl-worker | 9b5233c6-9b48-11f1-bb8a-4206745c74cb | 17,285 | encountered error while running a function with timeout. retry count: 0 |
| crawl-worker | 9b5222f0-9b48-11f1-bb8a-4206745c74cb | 5,488 | all attempts to scrape url had failed |
| crawl-worker | a92c1eca-a74c-11f1-9144-fab0241da207 | 1,194 | content type: application/pdf doesn't match the: text/html,text/plain |
| crawl-worker | 08dde3d0-... | 637 | page language was not detected (benign) |
| scan-worker | 3f414be4-9c6f-11f1-a76b-3e8752cb6a06 | 292 | encountered error while running a function with timeout |
| scan-worker | 176460e2-aa26-11f1-9d21-6a0006e40ced | 283 | got error while scraping |
| scrape-server | 5096d944 / f3384b28 / 260b4872 | 240+75+15 | scan page <url> failed, scan id is <id>. last successful result file ... |
| scan-worker | f7d37ce4-9da6-11f1-ae80-52ba2897bbec (+ null) | 230+158 | got error while trying to upload file to cloud ... crawl.json |
| scan-worker | 78c19322-9bae-11f1-abaa-a23cf0bb44ce | 97 | got error while running plugin. is plugin mandatory: true |
| scan-worker | 0bc2dd8c-9b5c-11f1-a137-c2fc7991ad86 | 62 | error uploading file to bucket |
| scan-worker | 0d569b2a-9b5c-11f1-a137-c2fc7991ad86 | 59 | all attempts to scrape url had failed |
| scan-worker | e7b5fc88-aaf8-11f1-b655-422d8edb1526 | 57 | content type: application/pdf doesn't match |
| crawl-worker | (null) | 68 | got error while handling request - for url: <url> |
| scan-worker | 1f6c9f7a-c8b7-11f1-9690-06bc843f009c | 5 | got error while scraping net::ERR_CONNECTION_REFUSED at <url> (newer template: detail inline in message) |
| scrape-server | (null) | 2 | scan <id> has failed to run over kubernetes |

### Q2/Q3: where the structured detail lives
- crawl-worker "got error while scraping" (WARN) has NO detail; it is paired with the same `$d.context.request_id` as the ERROR records.
- **`$d.error.message`** is a JSON string:
  - on "all attempts to scrape url had failed": `{"type":"OPEN_PAGE_TIMEOUT","additionalInfo":{}}` -> the final error TYPE per URL
  - on "encountered error while running a function with timeout": `{"errorDescription":"Error. Function: gotoURL execution took more than 60000 miliseconds"}` -> per-attempt description
- One failed URL emits WARN scraping + ERROR timeout (per attempt) + ERROR all-attempts (final), all sharing request_id. Count **all-attempts** for failed URLs; never sum the three.

### Q4: final error TYPE (`$d.error.message` JSON `.type`) on "all attempts to scrape url had failed", 2026-11-02 (24h)
| subsystem | type | n | notes |
|---|---|---|---|
| crawl-worker | OPEN_PAGE_TIMEOUT | 5,475 | ~1 per request_id |
| scan-worker | OPEN_PAGE_TIMEOUT | 27 | |
| scan-worker | FAILED_TO_RUN_ENGINES | 20 | additionalInfo.stackTrace: `TypeError: Cannot read properties of undefined (reading 'checked')` (all www.pearson.com) |
| scan-worker | DNS_ERROR_COULD_NOT_FIND_URL | 12 | investing.capitalone.com (+1 crawl developer-support.capitalone.com) |
| crawl-worker | INTERNAL_ERROR | 10 | Scraper.ts:139 |
| crawl-worker | PAGE_INTERACTION_PLUGIN_ERROR | 4 | Scraper.ts:134, spectrum.net hosts (login/interaction -> B2/B4) |

No HTTP-status or cert types appeared as a final type on this day.

### Q5: per-attempt `errorDescription` on "encountered error while running a function with timeout" (24h)
| subsystem | errorDescription | n | distinct request_ids |
|---|---|---|---|
| crawl-worker | Function: gotoURL execution took more than **60000** miliseconds | 17,263 | 6,126 (~2.8 attempts/URL) |
| scan-worker | Function: gotoURL execution took more than **40000** miliseconds | 157 | 104 |
| scan-worker | (no errorDescription) | 127 | 61 |
| crawl-worker | (no errorDescription) | 60 | 20 |
| scan-worker | bound run ... 20000/30000/60000/90000/120000 ms | 21 | plugin/engine `run` timeouts |
| scan-worker | bound handleRequest execution took more than 300000 ms | 2 | whole-page hard cap (B4 / D1) |

Crawl gotoURL limit = 60 s, scan gotoURL limit = 40 s (the Zendesk-reported "40000" is the scan-side limit).

### Q6: concentration by host, final failures (24h)
OPEN_PAGE_TIMEOUT crawl-worker: www.aa.com 4,513 (82%), www.pearson.com 488, www.vrbo.com 231, www.ynet.co.il 211, www.moo.com 30. 
=> The daily volume is driven by a handful of properties. **Signal = share of a property's URLs that fail, not the absolute count.**
A whole host failing with OPEN_PAGE_TIMEOUT (aa.com, vrbo.com = Akamai-type bot managers) is the A1/A2 pattern (WAF tarpit / hang), not D1;
a few heavy URLs failing on an otherwise healthy host is D1.

### Q7: net::ERR_* (6h, 2026-11-02 06-12Z)
Almost all are `[browser] [error] Failed to load resource: net::ERR_<X>` console lines = **sub-resource** failures (ads, trackers, fonts), not the page:
ERR_FAILED crawl 9,810 / scan 6,885; ERR_HTTP2_PROTOCOL_ERROR scan 308; ERR_NAME_NOT_RESOLVED 54; ERR_CONNECTION_RESET 47; ERR_CONNECTION_CLOSED 10; ERR_TIMED_OUT 3; ERR_CACHE_MISS 3.
=> **benign noise** unless the URL in the line is the page URL itself. Page-level net errors appear instead inline in the newer scan-worker
template `got error while scraping net::ERR_CONNECTION_REFUSED at <url>` (1f6c9f7a-c8b7-11f1-9690-06bc843f009c, 5/day) and as final type DNS_ERROR_COULD_NOT_FIND_URL.
No net::ERR_CERT_* in this window (see Q-cert below).

### Q8/Q9: main-document HTTP status, `http status code is: <N>` (Info!)
templateids: crawl-worker `33948266-9cb5-11f1-92dd-be037f26c345`, scan-worker `f8cdaba4-9af1-11f1-a148-2267a7afc7c0` (+ `b9b9265a-9cf4-11f1-9545-4a96456cf580`).
6h (06-12Z) totals: 200: scan 5,878 / crawl 3,759; 403: crawl 553 / scan 115; 404: scan 217 / crawl 116; 429: crawl 104 / scan 53; 504: scan 35; 400: 11; 502: 4.
12h by host (00-12Z): **403 www.huntington.com crawl 538 + scan 104** (A1 WAF), 429 privacy/support.collegeboard.org ~135 + community.environicsanalytics.com 22 (A5),
404 www.pearson.com 264, www.kpbs.org 124, environicsanalytics.com 145 (C4 / stale seeds), 504 www.pearson.com 76, 500 www.skysports.com 72.
**Key: a non-200 is NOT an error in the scanner. It is logged at Info and the page is still "successful" and scanned (the block/404 page gets analysed),
so filtering on ERROR severity misses A1/A5/C4 entirely.** The per-property ratio of non-200 to 200 is the signal.

### Q10-Q12: scan-worker scraping / plugin errors (24h 2026-11-02)
| message | error detail ($d.error.message) | n | example host |
|---|---|---|---|
| got error while scraping (template 176460e2) | none on this record; detail on the sibling ERROR record with the same request_id | 287 | houstoncolon.com |
| got error while running plugin. is plugin mandatory: true (78c19322) | none; sibling record = `bound run execution took more than 90000 ms` | 94 | www.ulta.com/shop/all |
| got error while running plugin. is plugin mandatory: false | none | 7 | ulta.com |
| function with timeout -> `{"type":"FAILED_TO_RUN_ENGINES","additionalInfo":{"stackTrace":"TypeError: Cannot read properties of undefined (reading 'checked')..."}}` | | 60 (20 URLs) | www.pearson.com |
| function with timeout -> `DNS_ERROR_COULD_NOT_FIND_URL` | | 36 | investing.capitalone.com |
| function with timeout -> `{"type":"ENGINES_PLUGIN_ERROR","additionalInfo":{"details":"Error: ENOENT: no such file or directory, access '..."}}` | | 11 | pre-ap.collegeboard.org |
| ENGINES_PLUGIN_ERROR `ENOTEMPTY: directory not empty, rmdir '/usr...` | | 6 | public.websteronline.com |
| ENGINES_PLUGIN_ERROR `SyntaxError: Unexpected end of input` / `ZlibError: zlib: unexpected end of file` | | 5 | collegeboard.org |
| got error while scraping net::ERR_CONNECTION_REFUSED at <url> (inline) | same text in error.message | ~8 | HCA / methodist hospital sites |
| got error while scraping Navigating frame was detached / Attempted to use detached Frame | | ~6 | help.salesforce.com, spectrumsportsnet.com |
| Error during cleanup close ... Target.closeTarget: No target with given id found | | 6 | benign teardown |

Per-page chain on scan-worker (one request_id): `encountered error while running a function with timeout` (ERROR, carries detail) ->
`got error while running plugin. is plugin mandatory: true` (WARN) -> `got error while scraping` (WARN) -> `Error during cleanup close` (WARN, benign).
=> **Read the detail from the ERROR record; the WARN records are just echoes.**
- FAILED_TO_RUN_ENGINES with a JS TypeError = **D2** (engine crashes on a specific DOM).
- ENGINES_PLUGIN_ERROR with ENOENT/ENOTEMPTY/zlib/SyntaxError = engine-bundle file-system race on the worker (Evinced-side, E-family / product bug), NOT the customer page. A new sub-issue candidate ("engine package load/extract failure").
- bound run > 90000 ms on a heavy listing page (ulta /shop/all) = D1/D2 (engine time-out on a large DOM).
- ERR_CONNECTION_REFUSED / DNS_ERROR on a whole host = host down / wrong host (C4), or A1 if only from scanner IPs.
- detached frame = page navigated/reloaded itself during analysis (D3-like instability).

### Q13: scrape-server `scan page <url> failed, scan id is <scanId>. last successful result file ...` (24h)
templateids 5096d944-aaf3-11f1-b0c8-66b556bfe55a, f3384b28-a658-11f1-928d-6af2599809e5, 260b4872-a46d-11f1-a54b-e2b111e1b995. ~330/day; NO error detail on the record.
It is the per-page roll-up in the joiner: the page is dropped from the scan result and the previous result file is reused. Top: ulta.com (scan 25832a34, the same scan also logged
"has failed to run over kubernetes"), huntington.com **PDFs** (scan 2db743de), investing.capitalone.com (DNS), snr.bell.ca (login app), portal.ct.gov .zip.
~56/330 are document URLs (pdf/zip/doc), which is expected. To diagnose, join on the URL to scan-worker `all attempts to scrape url had failed` or the timeout records.

### Q14: content-type mismatches (24h)
`content type: <ct> doesn't match the: text/html,text/plain` (crawl a92c1eca-a74c-11f1-9144-fab0241da207, scan e7b5fc88-aaf8-11f1-b655-422d8edb1526):
crawl ~2.5k/day (application/pdf 862, image/png 180, image/webp 36, image/jpeg 31, zip 12, docx/pptx 12, mp4 3), scan ~114/day.
**Benign**: non-HTML links are skipped by design. Only relevant to a "PDFs not scanned" how-to (H4) or when the SEED itself is a PDF (C4).

### Q15: upload-to-cloud (24h)
`got error while trying to upload file to cloud. retry count: 0, local path: .../crawl.json, bucket: prod-mon-production, bucket path: prod-mon/tasks/<scanId>/results/crawl.json`
(f7d37ce4-9da6-11f1-ae80-52ba2897bbec + null) 388/day, plus `error uploading file to bucket` (0bc2dd8c-9b5c-11f1-a137-c2fc7991ad86) 62/day.
$d.error.message = `Retry limit exceeded - {"error":{"code":429,"message":"The object prod-mon-production/.../crawl.json exc[eeded the rate limit for object mutation]"}}`.
**Only 2 scans** (6756371c, 791ebd6c) produced all of it: GCS 1-write-per-second-per-object limit on crawl.json rewritten per page in big scans.
=> Evinced-side product bug (E3-ish). Probably harmless when a later write succeeds; signal if the scan then ends FAILED or has stale crawl.json. One screenshot upload failure (evinced-temp-screenshots-bucket).

### Q16: cert / TLS / redirects / HTTP2 (24h + 7d via templateid)
- **No net::ERR_CERT_* or ERR_SSL_* found** in 24h free text or in 7 days of the timeout templates. There is no CERT type in the final-type enum seen over 7 days. **A9: no log evidence in this window.**
- net::ERR_TOO_MANY_REDIRECTS inline in crawl-worker `got error while scraping net::ERR_TOO_MANY_REDIRECTS at <url>`: moo.com 18/day, denverbariatrics.com 15/7d -> **A8**.
- ERR_HTTP2_SERVER_REFUSED_STREAM only as [browser] sub-resource (ynet 6/day); page-level ERR_HTTP2_PROTOCOL_ERROR discover.com 18/7d (A1/A5-ish).
- net::ERR_CONNECTION_RESET page-level: telebec.com ~390/7d (WAF reset -> A1).

### Q17/Q18: 7-day trend of FINAL failure types (templateid-filtered, 2026-10-27..11-02)
| day | OPEN_PAGE_TIMEOUT | PAGE_INTERACTION_PLUGIN_ERROR | PLUGIN_TIMEOUT | FAILED_TO_RUN_ENGINES | INTERNAL_ERROR | DNS_ERROR |
|---|---|---|---|---|---|---|
| 10-27 | 2,023 | 0 | 17 | 1 | 5 | 2 |
| 10-28 | 4,698 | 509 | 0 | 2 | 48 | 0 |
| 10-29 | 116 | 2 | 0 | 0 | 0 | 0 |
| 10-30 | 14,328 | 0 | 287 | 6 | 55 | 1 |
| 10-31 | 33 | 0 | 8 | 0 | 1 | 1 |
| 11-01 | 7,380 | 61 | 108 | 172 | 61 | 27 |
| 11-02 | 5,502 | 2 | 0 | 20 | 10 | 13 |
Very bursty: it follows which big properties ran that day. 7-day top hosts: OPEN_PAGE_TIMEOUT www.tsn.ca 6,625, www.aa.com 4,513, www.pearson.com 4,348, www.nvidia.com 4,337, noovomoi.ca 2,085, superbet.gr 1,986,
noovo.info 1,362, napoleonsports.be 1,199, uat.totalwine.com 970, xfinity.com 884, bellmedia.ca 792, booking.com 788; PAGE_INTERACTION_PLUGIN_ERROR goldmansachs.com 508;
FAILED_TO_RUN_ENGINES salesforce.com 144 (`TypeError: Cannot read properties of null (reading 'value') at compute`); PLUGIN_TIMEOUT tsn.ca 175, noovo.info 116.
The full type enum seen: OPEN_PAGE_TIMEOUT, PAGE_INTERACTION_PLUGIN_ERROR, PLUGIN_TIMEOUT, FAILED_TO_RUN_ENGINES, INTERNAL_ERROR, DNS_ERROR_COULD_NOT_FIND_URL
(+ in per-attempt records: ENGINES_PLUGIN_ERROR, SCREENSHOT_PLUGIN_ERROR, LINK_EXTRACTION_PLUGIN_ERROR).

### Q19/Q20: per-attempt detail shapes, 7 days (non-gotoURL), templates 9b5233c6 / 3f414be4 / 23a24bcc
`$d.error.message` has 4 shapes:
1. `{"errorDescription":"Error. Function: <fn> execution took more than <ms> miliseconds"}`: fn = gotoURL (navigation, D1/A), bound run (plugin/engine step), bound handleRequest (5 min page cap), and **an empty function name** ("Function:  execution", 7,352 on scan-worker, mostly noovo.info, origin unknown; probably an anonymous wrapper such as page stabilisation, so treat it like D1).
2. `{"type":"<ENUM>","additionalInfo":{"stackTrace"|"details":...}}`: ENGINES_PLUGIN_ERROR 1,084 (collegeboard; ENOENT/ENOTEMPTY/zlib = worker FS race), FAILED_TO_RUN_ENGINES 649 (pearson, salesforce: D2), OPEN_PAGE_TIMEOUT 519, DNS_ERROR 132, SCREENSHOT_PLUGIN_ERROR 53 (huntington .txt file), LINK_EXTRACTION_PLUGIN_ERROR 20 (asurion).
3. `{"url":"<page url at failure time>","message":"<interaction error>"}`: **login/interaction steps (B-family)**. The url shows where the browser actually was:
   - `No element found for selector: .truste-close-button-img`, url=about:blank: 4,615 / 524 URLs (goldmansachs; a cookie-banner close interaction on every page). **B2** (interaction selector), and it is the cause of the 10-28 PAGE_INTERACTION_PLUGIN_ERROR burst.
   - `No element found for selector: #username` with url on a login/guest page: 299 / 61 URLs (crawl), `#maincontent ... login-form ... button` 172 (kiddom), `#name` 44: **B2** (login selector) or **B5** when the url is a /login or /guest page mid-crawl (cigna `/web/public/guest` 202, zalando `accounts.zalando.com/authenti...` 252: session lost or redirected to SSO, B5/B4).
   - url = `https://www.sky.de/out-of-country.htm`, 44: **A7 geo-block**.
   - `Protocol error (Page.navigate): Cannot navigate to invalid URL` 18: bad seed/interaction URL (C1/C4).
   - `Runtime.callFunctionOn timed out. Increase the 'protocolTimeout'` 2: D1 engine.
4. Plain puppeteer text: `net::ERR_CONNECTION_RESET at <url>` (telebec 391: A1), `net::ERR_TOO_MANY_REDIRECTS at` (A8), `net::ERR_HTTP2_PROTOCOL_ERROR at` (discover 18), `Execution context was destroyed, most likely because of a navigation` 271 (booking.com: self-navigating page, D3), `Navigating frame was detached` 13, `Cannot read properties of undefined (reading ...)` 141 crawl (collegeboard, INTERNAL_ERROR-like product bug).

## Sub-issue mapping summary
| sub-issue | page-level evidence | strength |
|---|---|---|
| A1 WAF block | `http status code is: 403` (Info) host-wide; net::ERR_CONNECTION_RESET page-level; host-wide OPEN_PAGE_TIMEOUT | high (403), medium (timeouts) |
| A2 challenge | host-wide OPEN_PAGE_TIMEOUT / 200 + 1 page; not distinguishable in these logs alone | low |
| A5 rate limit | `http status code is: 429` (collegeboard, environics) | high |
| A7 geo | interaction error url = .../out-of-country.htm | high (when present) |
| A8 redirect loop | net::ERR_TOO_MANY_REDIRECTS at <url> | high |
| A9 TLS cert | **none found** (24h text + 7d templates) | no evidence |
| B2 selector | `{"url":..,"message":"No element found for selector: X"}`; PAGE_INTERACTION_PLUGIN_ERROR | high |
| B4/B5 | url in that JSON = login/guest/SSO page; bound handleRequest > 300000 | medium |
| C1/C4 seed | DNS_ERROR_COULD_NOT_FIND_URL; 404 on seed; Cannot navigate to invalid URL; ERR_CONNECTION_REFUSED | medium-high |
| D1 heavy page | gotoURL > 60000 (crawl) / 40000 (scan) for a minority of a host's URLs; PLUGIN_TIMEOUT; bound run > N | medium |
| D2 engine crash | FAILED_TO_RUN_ENGINES + TypeError stackTrace | high |
| D3 instability | Execution context was destroyed / detached frame | low-medium |
| E-family (Evinced-side) | ENGINES_PLUGIN_ERROR ENOENT/ENOTEMPTY/zlib; INTERNAL_ERROR; GCS 429 crawl.json upload | medium (new sub-issue candidate) |

## Benign background noise (ignore unless the ticket's host dominates)
- `not handling request ... matching grouping <re> is full` / `max number of successful visits was reached` (crawl cap): ~80k/day.
- `[browser] [error] Failed to load resource: net::ERR_*` / `status of 4xx`: sub-resources, ~17k per 6h.
- `content type: <non-html> doesn't match the: text/html,text/plain`: ~2.6k/day.
- `page language was not detected`: ~1k/day.
- `Error during cleanup close ... No target with given id found`: teardown.
- `got error while scraping` (WARN, no detail) and `got error while running plugin` (WARN): echoes of the ERROR record; count the ERROR record instead.
- `encountered error while running a function with timeout` is per attempt; it is only a failure if `all attempts to scrape url had failed` follows for the same request_id.
- `http status code is: 404` scattered over many hosts.

## Open questions
- Origin of `Function:  execution took more than` (empty function name), 7.3k/7d on scan-worker.
- The scrape-server `scan page failed` record carries no reason; join on scanId + url to scan-worker records.
- No net::ERR_CERT evidence; a longer window (or a known A9 ticket date) is needed to confirm how A9 appears (probably type INTERNAL_ERROR or a puppeteer `net::ERR_CERT_... at <url>` in shape 4).

Status: COMPLETE (about 25 queries).
