> Snapshot of the Claude doc https://claude.ai/artifact/V9EzQUegh7B3qDHmf2t3yV, exported 2026-11-03. Charts and diagrams live in the online doc.

# Site Scanner Issue Patterns

Nov 3, 2026 · @Aviv Ziv

## How to read this doc

The 279 Site Scanner tickets in the ground-truth sheet split into 8 issue families and 42 sub-issues. Families A–E are crawl, scan and platform incidents with log patterns. Families F–H are product, findings and account topics, which mostly leave no trace in the logs.

Each sub-issue has three parts:

1. **Log pattern**: what to search for in Coralogix, an example log line and how the pattern looks across one job.
2. **Why it works**: the mechanism that produces this log trace.
3. **Solutions from tickets**: what fixed it in the tickets, with ticket numbers.

Conventions for every query:

- Filter workers with `$d.resource.attributes.environment == 'production'`. One crawl or scan = `$d.resource.attributes['k8s.job.name']`.
- HTTP status lines are logged at INFO, so never filter by ERROR when looking for blocks.
- Match message text, not template ids (they change every release). In DataPrime `~ 'a|b'` is a literal substring, so use separate `~` terms joined by `||`.
- Judge by the share inside one job, not global counts. Anchor on the time of the failing run, not the ticket date.
- Detection grade per sub-issue: **detectable** (one signal), **rule** (a combination or timeline separates it), **ambiguous** (narrowed to 2–3 candidates), **invisible** (no log trace today).
- Example log lines use `example.com` and shortened ids in place of real customer values.

## A · Access blocked

The site, its WAF or its network stops the scanner from fetching pages (33 tickets). In the logs every A sub-issue looks like a run of bad HTTP statuses or timeouts inside one job; the shape of that run over time tells them apart.

[Diagram: schematic of per-job status sequences · shapes from production jobs, 2026-10-27 to 11-03 — see the online doc]

Group a job's `http status code is` lines and failure types by time: the row it resembles names the sub-issue.

### A1 · WAF / firewall hard block (13 tickets · rule)

**Log pattern.** In crawl-worker or scan-worker, 403/405 on at least half of the job's visited pages, often with only 1 page visited. Variants: `net::ERR_CONNECTION_RESET/REFUSED` on the page itself, or `OPEN_PAGE_TIMEOUT` on 80%+ of URLs at a flat rate (tarpit).

```
successfully visited 1 pages so far
http status code is: 403            (INFO)
[browser] [error] Failed to load resource: the server responded with a status of 403 ()
not including url in result url set. reason: final url not included in whitelist
```

```
source logs | filter $l.applicationname == 'site-scanner' && $d.resource.attributes.environment == 'production' && $d.message ~ 'http status code is: ' | extract $d.message into $d.x using regexp(e=/status code is: (?<code>[0-9]+)/) | groupby $d.resource.attributes['k8s.job.name'] as job, $d.x.code aggregate count() as n
```

**Why it works.** A WAF answers the scanner's requests with 403/405 or drops the connection. Site Scanner still counts a 403 page as visited and logs its status at INFO, so the block is visible only as the share of bad statuses per job. When it starts tells you the trigger: request 1–3 means a deny list, geo rule or user agent; after a run of 200s that never recovers means a reputation trip.

**Solutions from tickets.**

- Customer allowlists the 5 static NAT IPs (scan-pool-nat1–5) and support turns on static IP for crawl and scan in Retool: #1665 (back to 700+ pages), #3052 (245 pages), #3206, #1296.
- Customer adds a bot-manager rule or exception: #1493, and #3369 with a custom header (`X-Sky-Scannertool`) plus IP ranges.
- Custom login script that passes the protected entry first: #792.
- Temporary external scraper while the customer reviews: #952.
- No fix possible, recommend WFA or SDK: #3301.

### A2 · Bot challenge page (4 tickets · ambiguous)

**Log pattern.** A job where 202 is at least 30% of statuses from the first minute, and a URL that got 202 never later gets 200. A crawl that ends with 1 page and a non-200 seed.

```
http status code is: 202            (5,255 times in one job, with 4,220 × 429 and 2 × 200)
successfully visited: 1 urls
```

**Why it works.** Bot managers (AWS WAF, Akamai) answer with a "please wait" interstitial that returns 202 and needs JavaScript the crawler doesn't pass. **Blind spot:** a Cloudflare challenge returns 403, which looks exactly like A1 (#3420).

**Solutions from tickets.**

- Change the user agent in `puppeteer-args` for crawl and scan (`--user-agent=zendesk-bot` for a Zendesk-hosted site): #3420.
- Allowlist the NAT IPs, or a reCAPTCHA v2 bypass token: #2343, #2288.
- Third-party host that cannot allowlist: use WFA instead: #2450.

### A3 · Soft block (block page with HTTP 200) (3 tickets · invisible)

**Log pattern.** None today. The block page returns 200, so status lines, failure types and crawl counts all look normal. The only hints come from the scan output: identical issues on every page (landmark, H1) and blank screenshots.

**Why it works.** It doesn't; the logs hold no page title, body size or link count. Backend gap P1-1 (per-page fingerprint) would make it detectable.

**Solutions from tickets.**

- Customer allowlists the static IPs in the WAF or an Akamai network list exempt from bot scoring: #2374, #1192 (plus Evinced property settings, CS-2140).
- Ask the customer's security team to allowlist the user agent and IPs: #2077.

### A4 · Static egress IP not enabled (5 tickets · rule)

**Log pattern.** admin-server logs the crawl or scan request body with `"useStaticIp":false`, and its `id` equals the worker's `k8s.job.name`. The job also runs on a node pool not named `*-pool-stat*`. Combined with an A1 block, this means the customer allowlisted IPs the job never used.

```
admin-server  POST /api/crawls  {"id":"<job id>", … "useStaticIp":false …}
crawl-worker  k8s.node.name = gke-prod-mon-cluster-crawls-fast-pool-…
```

**Why it works.** Only the static pool leaves from the 5 NAT IPs. A property-level override or the fast tier sends traffic from random GCP IPs, which the customer's allowlist does not cover. **Blind spot:** static IP on, but the customer allowlisted other IPs; the egress IP is not logged.

**Solutions from tickets.**

- Enable static IP for crawler and scanner in Retool: #1387, #2400.
- Remove property-level overrides so the property inherits the tenant setting: #3083.
- Move the property off the fast tier to regular (static IPs): #3425.
- Evinced-side config fix so the crawler uses the pool: #233 (CS-1257).

### A5 · Rate limiting (HTTP 429) (3 tickets · rule)

**Log pattern.** 429 is at least 10% of the job's statuses. Front-loaded then fading means throttling; a steady \~50% means a hard limit. Often with `ERR_HTTP2_SERVER_REFUSED_STREAM` and page counts that swing between runs.

```
http status code is: 429            (22–58% of requests in #2914)
ERR_HTTP2_SERVER_REFUSED_STREAM
```

**Why it works.** The site limits requests per IP. A page that fails gives no outbound links, so discovery stalls and each run finds a different number of pages.

**Solutions from tickets.**

- Move the property to `speed-tier.slow` (one request at a time): #2914 (4,615 pages, 0 errors).
- Lower concurrency as a temporary fix, plus an Akamai bot exception: #1597.
- Stagger schedules of properties on the same site; enable static IPs and allowlist: #2914, #2185.

### A6 · Outdated browser user agent blocked (1 ticket · ambiguous)

**Log pattern.** A blocked job whose `crawler config is: {…}` line shows `--user-agent=…Chrome/65` or `HeadlessChrome/65 … EvincedBot`. The `browser was opened successfully. version: Chrome/126` line does not show the user agent actually sent.

**Why it works.** Bot managers block user agents older than recent Chrome. **Blind spot:** an old user agent doesn't change the block's shape, so only a re-run with a current one proves it. The config line also contains credentials: read only the user agent field.

**Solutions from tickets.**

- Update the property user agent to a modern Chrome in Retool: #3340 (50+ pages), with CS-2856 to update all properties.

### A7 · Geo-blocking (2 tickets · detectable)

**Log pattern.** The final URL after redirects, or the `url` in the interaction error, is an out-of-country page.

```
encountered error while running a function with timeout … {"url":"https://www.example.com/out-of-country.htm","message":"No element found for selector: #username"}
```

**Why it works.** The scanner leaves from US IPs; the site redirects non-local visitors away, so the expected page and its login fields never load.

**Solutions from tickets.**

- Enable static IPs and have the customer allowlist them at the edge: #2812 (Greece).
- Use the redirect target as seed with an exclude regex, or allowlist: #1566.

### A8 · Redirect loop (1 ticket · detectable)

**Log pattern.** `got error while scraping net::ERR_TOO_MANY_REDIRECTS at <url>`.

**Why it works.** The site answers the scanner's IPs with endless 302s (common on staging and auth gateways); the browser gives up.

**Solutions from tickets.**

- Customer confirms the correct URL and allowlists; closed without a fix in #2881.

### A9 · TLS / SSL certificate error (1 ticket · invisible)

**Log pattern.** None: the browser ignores certificate errors and logs nothing (backend gap P2-15).

**Why it works.** Not detectable today; open the site in a browser and check the certificate.

**Solutions from tickets.**

- Customer renews the certificate: #1283.

## B · Authentication & session

The scanner can't log in, or loses the session while crawling (32 tickets). All B patterns come from the page-interaction plugin. Read them per request (`$d.context.request_id`) and per pod (one browser session), not per job: the login step itself logs the login URL as its final URL, so counting login landings per job wrongly flags healthy jobs.

The interaction plugin logs each step, then either `finished interacting with page successfully` or an error whose JSON names the step type, the selector and the URL the browser was on:

```
starting page interaction plugin
typing text in element: #username
clicking element: button[type="submit"]
encountered error while running a function with timeout. retry count: 0
  {"url":"https://login.example.com/…","message":"No element found for selector: #password"}
failed due to PAGE_INTERACTION_PLUGIN_ERROR
```

[Diagram: decision order from the login disambiguation research · production jobs, 2026-10-27 to 11-03 — see the online doc]

Check for a block first: in #3301 the "missing selector" was a 405 on the login page.

### B1 · MFA / 2FA blocks login (5 tickets · ambiguous)

**Log pattern.** The request that clicked submit ends on a path containing `mfa`, `otp`, `2fa`, `verify`, `challenge` or `passcode`. Match the URL path only: OAuth `code_challenge=` query parameters give false hits.

**Why it works.** After the password step the site redirects to a second factor the scanner cannot complete, so every later page lands back on login. **Blind spot:** no live case was found in 7 days to confirm the rule, and a single-page-app MFA screen on the same route as login looks like B3.

**Solutions from tickets.** No ticket was fixed in place; MFA cannot be automated.

- Use a test user without 2FA, or add the post-login landing URL as seed: #1119, #2946.
- Allowlist the static IPs so the site skips the 2FA trigger for them: #2167.
- Use WFA or the Web SDK instead: #391. Customer refused to disable 2FA, site not onboarded: #3241.

### B2 · Login / interaction selector mismatch (6 tickets · rule)

**Log pattern.** An interaction error `No element found for selector: X` whose `url` is the expected login page, followed by `failed due to PAGE_INTERACTION_PLUGIN_ERROR`, with no 403/405 resource error on the login request. `'<sel>' is not a valid selector` means a malformed selector.

**Why it works.** The stored selector no longer matches the login form: the site changed, the selector was wrong from the start, or IDs are generated on every load. **Trap:** a blocked login page also "loses" the selector; in #3301 a 405 between `going to URL` and the first final URL showed it was really A1. Also, `element: X, exists: true` is unreliable: it was followed 13–160 ms later by `No element found` in all 5 failures examined.

**Solutions from tickets.**

- Replace with stable selectors (name, aria, data-\*, full CSS path): #2132, #2143, #2371.
- Customer updates the selectors in property settings: #243.
- Fix a hashed class selector and raise `timeoutSeconds` to 120: #3198 (5,000 pages).
- Product fix in the crawler for multi-step SSO: #1324 (CS-2257).

### B3 · Stale / invalid credentials (3 tickets · rule)

**Log pattern.** Every login step runs, the plugin reports `finished interacting with page successfully`, and about 20 s later the browser is still on the login route on every request. The job ends DONE with 1 page: the login page.

**Why it works.** The site rejects the password and re-shows the login form, which the plugin cannot tell from success. Rule out a 403 on first load (A1) and an MFA screen on the same route (B1).

**Solutions from tickets.**

- Update the password for both scanner and crawler (they were out of sync, causing repeated failed logins and an IP lockout): #1390, #1475.
- Remove a decommissioned site from scope: #1895.

### B4 · Multi-step / custom login flow needs configuration (15 tickets · ambiguous)

**Log pattern.** A partial step sequence on an identity provider: the username is typed, then the Continue click or the password field fails. The `bound handleRequest execution took more than 300000 milliseconds` cap is not specific (26 jobs had it, 7 of the top 10 with no login at all).

**Why it works.** Two-screen, modal and SSO logins need a backend Multiple Interactions script; the simple login form stops after the first screen. **Blind spot:** cannot separate "element missing" from "element not yet rendered" without a DOM capture or screenshot.

**Solutions from tickets.**

- Support builds a Multiple Interactions script on the backend (`scraper.user-interaction.configuration`) with clicks, waits and inputs: #571, #1607, #2058, #2959, #3238, #2290.
- Copy a working custom login to a new property: #1214.
- Extra wait after the final submit, `--disable-web-security` for CORS, a non-2FA account: #869.
- List mode with explicit URLs after login: #2153.
- Product fix: #199 (EW-5476).

### B5 · Session lost mid-crawl (3 tickets · rule)

**Log pattern.** One pod (browser session) logs in fine, then its later requests keep landing on the login URL while other pods keep succeeding. If the same page families bounce to login in every pod and the next request succeeds again, those are gated pages, not session loss.

**Why it works.** Parallel browsers, crawling logout or session-check URLs, or two properties logging in at once invalidate the session for one browser.

**Solutions from tickets.**

- Set parallelism to 1 or the slow tier (single browser): #1818, #2794.
- Exclude logout, guest and session-check paths with regex: #1967, #2794.
- Split properties into authenticated and public: #1818, #2794. Feature request for mid-scan re-login: CS-2499.

## C · Crawl scope configuration

Pages load fine, but the property's settings produce the wrong set of URLs (30 tickets). Start from the end-of-job summary, which every crawl prints once, including 0-page crawls (the progress counter `successfully visited N pages so far` is never printed when nothing is visited):

```
successfully visited: 0 urls
failed to scrape: 0 urls
filtered out: 1 urls
allowed domains: {www.example.com}
finished waiting for page to stabilize. final url after redirections: https://corporate.example.net/
not including url in result url set. reason: final url not included in whitelist
```

The per-crawl `METRIC_EVENT` CrawlSummary in admin/front (status, totalUrlsCount; taskId = the crawl job name) gives the same count in one line. A 0-URL crawl reports status DONE, not FAILED.

[Diagram: decision order from the discovery disambiguation research · production crawls, 2026-11-01 to 11-02 — see the online doc]

In 2 days about 35 production crawls ended with 1 page and 59 with 0; C2 alone explained about 33 of them.

### C1 · Include regex matches nothing / invalid regex (4 tickets · rule)

**Log pattern.** `final url not included in whitelist` on the seed, while the seed's host IS listed in `allowed domains` (so the include regex or path rejected it). Or `language is not included in whitelist` on every URL of the job.

**Why it works.** The same reject text covers the domain list and the include regex; comparing the host with the `allowed domains` line tells them apart. **Blind spot:** the include regex itself is not in a safe log line.

**Solutions from tickets.**

- Correct the include regex to the real URL format (locale, path): #833, #2172.
- Escape slashes in the regex: #1648.
- Fixed over Slack: #301.

### C2 · Redirect target outside the domain whitelist (5 tickets · rule)

**Log pattern.** The seed's final URL is rejected with `final url not included in whitelist`, and its host is NOT in the job's `allowed domains` line. About 33 production jobs matched in 2 days (for example 14 state sites redirecting to one corporate host).

**Why it works.** The seed redirects (www vs non-www, a locale path, another domain) to a final URL the whitelist doesn't allow, so the only page is dropped and the crawl ends with 0 URLs.

**Solutions from tickets.**

- Add the redirect target's domain or www variant to the property domains: #926, #944.
- Add the redirect-target path to the include regex: #1638 (\~5K pages).
- Broaden include domain/regex to the final URLs, or switch to List mode: #2783, #910.

### C3 · Scope too broad / unexpected URLs (8 tickets · rule)

**Log pattern.** A very large crawl where more than 90% of fetched URLs are later rejected by the exclude list, or the page cap message `not handling request … max number of successful visits was reached`. Compare page counts between consecutive crawls of the same property.

**Why it works.** The include domain or regex is too wide, so the crawler fetches out-of-scope or locale pages before filtering. One property scraped 130k pages in 10.8 h, rejected 129,745 and ended with 0 URLs.

**Solutions from tickets.**

- Narrow the include regex or seed list: #1498, #1626, #2889 (CS-2728).
- Remove stale seeds and exclude junk paths such as `/banner`: #2895.
- Filter after the scan with a View: #1011. Explain a legitimate difference: #2222, #1612.

### C4 · Seed unreachable / soft-404 / error-page redirect (3 tickets · detectable)

**Log pattern.** `failed due to DNS_ERROR_COULD_NOT_FIND_URL` on the seed, a high share of `http status code is: 404`, or `final url after redirections: …/404` or `…/500`.

**Why it works.** The seed or listed URLs are dead, or redirect to the site's error page, which then gets scanned and skews issue counts and scores.

**Solutions from tickets.**

- Add a deeper, valid seed URL: #1737 (CS-2456).
- Remove stale URLs and exclude error-page paths: #1413, #1600 (feature request to skip pages that don't land on the expected URL).

### C5 · Grouping / URL-normalization rules (5 tickets · ambiguous)

**Log pattern.** The only rejects are `sanitized url was already visited` on `#fragment` URLs, often with PDF links. Other grouping problems leave only a page count lower than expected.

**Why it works.** Grouping rules merge single-page-app routes (fragments) or query-parameter variants into one page, so distinct pages vanish.

**Solutions from tickets.**

- Grouping rules "as different pages" and untick "Ignoring URL fragments": #2154, #2144 (2K+ pages).
- Add parameter URLs to the seed list: #2915. Ignore sort/filter params but keep pagination: #3152.
- Product fix for `///` normalization: #594 (CS-1622).

### C6 · Non-link (JS) navigation (4 tickets · invisible)

**Log pattern.** None that is specific. The job shows seed 200, final URL = seed, `filtered out: 0`, `failed to scrape: 0`, no errors, 1 page. That is identical to a soft block (A3) or a bot page served as 200.

**Why it works.** Menus use `onclick`, `ng-click` or `javascript:void(0)` with no `href`, so the crawler finds nothing to follow. The link extractor logs that it ran but not how many links it found (backend gap P1-1).

**Solutions from tickets.**

- Switch to List mode or give an explicit seed list: #2234, #2757, #1813 (CS-2498).
- Still failing after login errors: #3232.

### C7 · List-mode misconfiguration (1 ticket · rule)

**Log pattern.** admin/front `failed to create entity for property …` with `No URLs were supplied` or `URL set not defined`; or `max number of successful visits was reached` with 1 page visited (page cap set to 1).

**Why it works.** The scheduler refuses a property with no URLs, and a cap of 1 stops the crawl after the seed.

**Solutions from tickets.**

- Switch to Crawl mode with a seed URL and domain: #1722.

## D · Page render & analysis engine

Individual pages time out, crash the analysis engine, or are analysed before they finish rendering (12 tickets). The per-URL outcome is one line, `all attempts to scrape url had failed` (or `CRAWL|SCAN with id … failed due to <TYPE>`), whose `$d.error.message` JSON carries the failure type. Count those, not the per-attempt `encountered error while running a function with timeout` lines (about 2.8 per URL).

### D1 · Heavy page load timeout (3 tickets · rule)

**Log pattern.** `OPEN_PAGE_TIMEOUT` or `Function: gotoURL execution took more than 60000 miliseconds` (crawl) / `40000` (scan) on 10% or fewer of a job's URLs, 200s continuing to the end of the job, and the same URLs failing in every run.

```
all attempts to scrape url had failed  {"type":"OPEN_PAGE_TIMEOUT", …}   url: https://www.example.com/stores/map
```

**Why it works.** Heavy pages (maps, product grids, very large DOMs) never reach the ready state within `waitForPageReadySeconds` or the navigation timeout. Low share + same URLs every run = the page itself. **Blind spot:** at 80%+ failing with a flat rate it is a tarpit block (A1); between 10% and 80% it stays ambiguous with A1/A5. If the failing URLs succeed in other runs, it's throttling.

**Solutions from tickets.**

- Exclude the slow URLs: #1793, engineering fix CS-2472.
- Lower max pages or sampling on heavy groups, raise `waitForPageReadySeconds` to 45–60: #3248 (CS-2833), #1755 (CS-2469).

### D2 · Analysis engine crash / limit (2 tickets · detectable)

**Log pattern.** `failed due to FAILED_TO_RUN_ENGINES` with a stack trace in `additionalInfo.stackTrace`.

```
{"type":"FAILED_TO_RUN_ENGINES","additionalInfo":{"stackTrace":"CircularEvValueError: Circular dependency detected while calculating: VisibilityLimitAppliedToChildren … EvincedEnginesPlugin.ts runAnalysis"}}
```

**Why it works.** The engine fails on specific DOMs (AMP lightbox circular visibility, \~21k elements). **Split off:** `ENGINES_PLUGIN_ERROR` with `ENOENT`/`ENOTEMPTY`/zlib (\~1,000 a week) is an Evinced-side race loading the engine package on the worker, not the customer's page.

**Solutions from tickets.**

- Exclude the page as a workaround: #3293 (CS-2845).
- Engine bug escalated to engineering: #2244.

### D3 · Incomplete render → findings variance (7 tickets · ambiguous)

**Log pattern.** Only one variant is visible: `Execution context was destroyed, most likely because of a navigation` on the page (navigation during analysis). Most D3 tickets show nothing in the logs.

**Why it works.** Pop-ups, late redirects or late JavaScript change the page while it is analysed, so findings and scores vary between runs. Render timing is not logged.

**Solutions from tickets.**

- Suppress the pop-up with a cookie (login-with-cookies or a Multiple Interactions step): #731.
- Customer fixes late-inserted content (for example add alt text when the pixel is created): #2131.
- Explain the transient finding and score impact: #1604, #1992. Engineering fix for screenshots: #827 (CS-1843). Flag CSS-less renders: #3284 (CS-2848).

## E · Evinced platform & infra

Backend, scheduler, pipeline or limits on Evinced's side (32 tickets). admin, front and the webapps log structured fields: `$d.context.property_id` and `scan_id` (the last 12 hex characters of the UUID), `$d.logger_name`, and `$d.error.type` / `$d.error.message`. Filter on `property_id` to see one job end to end:

```
JobScheduler  for property: <id>, the next schedule job time is: 2026-11-01T06:30
JobService    POST scrape-server /api/scans             (dispatch)
ScanService   Scan with ID=<id> state changed from NEW to READY_TO_RUN → RUNNING
              → INGESTING → GENERATING_CSV → DONE
```

Where the chain stops tells you the sub-issue.

[Diagram: job lifecycle from admin/front logs · lifecycle research, 2026-10-20 to 11-03 — see the online doc]

### E1 · Platform outage / infra incident (12 tickets · rule)

**Log pattern.** An aggregate, not a message: the number of distinct tenants with FAILED or dispatch-failure lines per hour, with chronic background errors excluded. Baseline 0–3; the 2026-06-29 outage reached 14 tenants at 10:00Z (first ticket 11:00Z) and 32 at 18:00Z. A collapse in scan-worker log volume is the other sign (395k a day down to \~5k on 06-26 and 06-28).

**Why it works.** An Evinced-side incident hits many tenants at once; a customer-side problem hits one. The raw error count barely moved during the outage, so the tenant count is the signal.

**Solutions from tickets.** All 12 were fixed on Evinced's side; support confirmed and re-ran.

- Infra patch, then rerun failed scans: #639, #685, #2751, #2752, #2755, #2760, #2764.
- Same-day fix by the site scanner team: #1711, #1869, #1988. Exports sent by hand meanwhile: #2979.
- User migration fix: #917 (CS-1861).

### E2 · Scheduler bug (missed / wrong next run) (7 tickets · detectable)

**Log pattern.** `duplicate key value violates unique constraint "key_type_constraint" … JobEntity already exists` with a run time in the past, repeating every \~7.5 minutes. Or the next-run line disagreeing with the UI schedule.

**Why it works.** The key is property + job + scheduled time. A current-slot duplicate is a harmless race between two schedulers; a past slot that keeps colliding is a stuck schedule that never runs. **Blind spot:** the timezone variant is invisible because the next-run line has no time zone.

**Solutions from tickets.**

- Scheduling calculation fix deployed 2026-01-08, then manual reruns: #1396, #1399, #1404, #1421 (CS-2332).
- Next-run date bug fixed: #1378, #1381 (CS-2318).

### E3 · Pipeline dispatch / state-machine failure (5 tickets · detectable)

**Log pattern.** For one property, right after a :00 or :30 scheduler tick, with no worker activity:

```
Failing URL set <id> due to job timeout/failure
Failed running create crawl request for URL set with ID=<id>
scrape-server  HikariPool-1 - Connection is not available, request timed out after 30000ms (total=10, active=10, waiting=7)
```

Also `kubernetes job failed … reason=BackoffLimitExceeded` and `Sampling scan with ID=… passed its timeout, marking it as FAILED`.

**Why it works.** The crawl-to-scan hand-off fails on Evinced's side (DB pool exhausted, regression, timeout). About 20 properties had this pair in 14 days. **Blind spot:** the cause behind "job timeout/failure" is not logged.

**Solutions from tickets.** All engineering fixes, then a fresh run:

- \#3228 (CS-2821), #1618 regression (CS-2404), #1557 (CS-2401), #3315 (CS-2843), #87 (EW-4617).

### E4 · Tenant limits reached (2 tickets · detectable)

**Log pattern.** `failed to create entity for property with id: <id>` with `$d.error.type` LimitExceededException (`The license has expired`, or `Scan could not be created because the limit of concurrently running scans has been reached`).

**Why it works.** The scheduler refuses to start a run when the licence or the concurrent-scan limit is hit. About 15k a day are licence-expired refusals on lapsed tenants, so filter by the ticket's tenant.

**Solutions from tickets.**

- Raise `limit.running-scans-count` (5 to 10) in Retool and rerun: #2192.
- Limit raised internally: #149.

### E5 · Backend query error / timeout ("Error loading scan") (6 tickets · rule)

**Log pattern.** front-server records a 5xx with `$d.context.request_uri` (`uri=/api/…`), which joins by operation id to:

```
invocation of function (ScanController.list) took 50123 millis.          (WARNING above ~10 s)
invocation of function (ScanController.get) failed (NotFoundException:Scan could not be found)
```

**Why it works.** Heavy Views (large regexes), deleted scans or slow queries make the UI call fail or time out. A product exception such as NullPointerException points to F3 instead. **Blind spot:** the 502/504 the browser gets from the gateway is not logged.

**Solutions from tickets.**

- Simplify or rebuild heavy Views, split properties: #1918 (CS-2514), #1051.
- Engineering fix: #975 (CS-1915), #2901.
- Clear cache or use incognito: #1019. Deleted scan explained: #953.

## F · Product UI, export & integrations

Non-crawl product defects and reporting behaviour (47 tickets). Exports leave clear logs; UI and integration problems mostly don't.

### F1 · Export failure (10 tickets · detectable)

**Log pattern.** In admin-webapp, front-webapp or csv-worker:

```
failed to generate CSV for scan <id> for owner <id> (poller timeout)
failed to generate CSV for scan <id> for owner <id> (poll request failed)
publish to queue <id>-csv failed (attempt 3): Connection refused
Failed to send crawl completion email for urlSetId=<id>
```

**Why it works.** The export poller and email sender log each failure. Poller timeouts usually mean the scan was deleted; queue refusals mean exports were never generated. **Blind spots:** a bug in `ScanResultExportPoller.onFailed()` hides the failure from the user, and the 10k-row Excel rejection is not logged.

**Solutions from tickets.**

- Engineering fixes: #1727 (CS-2446), #2274 (CS-2413), #2780 (next day).
- Over 10k rows: filter in the UI or use CSV export; support runs backend exports with raised limits and shares split zips: #1352, #3270.
- Email quarantined by the customer's spam filter: safelist the Evinced sender, #558, #1056.
- File format: change the list separator for Italian Excel, #726; rename the download to .zip, #1602.

### F2 · Export count semantics (5 tickets · invisible)

**Log pattern.** None: nothing fails. The export has one row per issue × component (and per language version), so it holds more rows than the UI's issue count and Issue IDs repeat.

**Why it works.** Not a failure, so nothing is logged.

**Solutions from tickets.**

- Explain the row model; dedupe on Issue ID in Excel to match the platform count: #1476, #3370, #1336, #676.
- Scope to one language or per-language Views: #2960.

### F3 · UI bug / UI confusion (22 tickets · ambiguous)

**Log pattern.** Only server-side bugs show: a front-server failure joined to a product exception, for example a NullPointerException on `/api/property-overview` (35 times for one tenant), or `Content-Type 'application/x-www-form-urlencoded' is not supported` when saving from Edge. Pure front-end bugs and UI confusion leave nothing.

**Why it works.** The function logger records every controller failure with its exception; front-end rendering and user misunderstanding never reach the server.

**Solutions from tickets.**

- Front-end or backend fix by engineering: #1993 and #2128 (save without a time zone, CS-2543), #2139 (CS-2584), #2245 (CS-2602), #3121 (CS-2785), #1639, #1348, #915, #867, #1420, #186.
- Workaround: another browser (#260, #1340), clear cache and re-login (#2756), a View that filters out a URL (#2801).
- Explain: deprecated compare-scans beta (#863, #1994), sort order (#1068), stale View selection (#1952).

### F4 · Integration issue (Jira / ADO / MCP) (10 tickets · ambiguous)

**Log pattern.** Only MCP leaves a trace: `An invalid request caller ID was received: MCP` and token failures. Jira and Azure DevOps calls are not logged in these services; the ADO errors came from the customer side (`TF401322`, `WorkItemUnauthorizedRuleBypassException`, CORS/401).

**Why it works.** Integration calls run outside the logged services (backend gap P2-16).

**Solutions from tickets.**

- Engineering fixes: ADO rules toggle and reduced OAuth scopes #1554 (CS-2426), ADO formatting #1976 (CS-2526) and #2052, Jira reporter field #203 (CS-1256), MCP login #3136.
- On-prem Jira is unsupported: feature request CS-2702, CSV export as a workaround (#2800); customer declined setup (#1806).
- Feature request for collections in MCP: #3219 (CS-2801).

## G · Findings accuracy & scoring

Whether issues, severities and scores are right (30 tickets). None of these leave a log trace: findings live in scan results, not service logs. Diagnose from the scan's issues, screenshots and the engine version.

### G1 · Confirmed engine false positive (11 tickets · invisible)

**Log pattern.** None. The only related signal is an engine version change between two scans of the same property.

**Why it works.** A rule misfires on a specific DOM (contrast on gradients or opacity, text spacing, a rule bug); the engine logs no per-finding detail.

**Solutions from tickets.**

- Engine fix in a release: #3072 (CS-2776), #3059 and #3195 (CS-2800), #1267, #159 (suppression added in Site Scanner and WFA), #247.
- Turn off Needs Review / Best Practice for the property: #1632 (CS-2457).
- Revert a severity mapping; customer sets initial opacity to 0: #818 (CS-1885).
- Explain, offer masking: #473, #1682. Not reproducible: #694.

### G2 · Disputed finding: true positive (8 tickets · invisible)

**Log pattern.** None.

**Why it works.** The finding is correct; nothing failed.

**Solutions from tickets.**

- Explain with the element and the WCAG rule: #545, #732, #1014, #1129, #1663.
- Suggest the fix (`alt=""`, `aria-hidden`, a library patch): #750, #1574.
- Closed after the finding stopped appearing: #2998.

### G3 · Score / severity / WCAG configuration (9 tickets · invisible)

**Log pattern.** None; check the engine version and the property's `enginesConfiguration`.

**Why it works.** Score and severity follow the formula (score = 0.99^(damage / successful pages) × 100), the engine version and the WCAG scope; none of that is logged per scan.

**Solutions from tickets.**

- Explain the formula, Needs Review and baselines: #371, #730, #1732, #2178, #2392.
- Scope WCAG version through property config (`AXE_CONFIG runOnly`, `ENABLE_AXE_OPT_IN: false`) or remove the restriction: #2797, #3068.
- Disable Needs Review and Best Practice for the tenant: #2576.
- Engine fix for a severity change: #3283 (CS-2834).

### G4 · Suppression / masking request (2 tickets · invisible)

**Log pattern.** None: a request, not a failure.

**Why it works.** There is no in-product dismiss, so customers ask support.

**Solutions from tickets.**

- Support adds a validation skip for the component on matching URLs, plus a feature request for admin-configurable skips: #3151.
- Deferred: #2875.

## H · Account, requests & noise

Non-incident tickets (63). None have a log pattern; the one exception is licence expiry, which shows as E4.

### H1 · Access & licence (10 tickets · invisible)

**Log pattern.** None for permissions. An expired licence shows as `failed to create entity … LimitExceededException ('The license has expired')` (see E4).

**Why it works.** Roles and user membership are account data, not runtime events.

**Solutions from tickets.**

- Add the user to the tenant in Retool (`add_user_to_tenant`): #709. Enable platform access per user, then re-login: #1370.
- Extend the licence and resend the invitation: #2152.
- Point to the customer's own admin or account team: #599, #2107, #3051.

### H2 · Access setup questions (IPs / headers) (9 tickets · invisible)

**Log pattern.** None: these are questions before any failure.

**Why it works.** Not an incident.

**Solutions from tickets.**

- Configure a customer-supplied header on scanner traffic, plus static IPs: #454 (`x-px-access-token`, CS-1464), #515, #3009.
- Explain the 5 static NAT IPs (Evinced's, shared, on GCP) and Evinced domains: #2824, #3255, #1138.
- Basic auth is unsupported; a custom header is the workaround: #3327.

### H3 · Config / admin task (11 tickets · invisible)

**Log pattern.** None.

**Why it works.** Support performs a task; nothing failed.

**Solutions from tickets.**

- Create a tenant and admins: #1054. Restore an archived property: #3231. Create a property: #3177.
- Viewport per property in the DB (CS-2590): #2072. iframes toggle: #3463. Schedule changes: #1116.
- Who created a property, from the backend: #1902. Archive via the property menu: #2397.

### H4 · Feature request / how-to (13 tickets · invisible)

**Log pattern.** None.

**Why it works.** Product questions and requests.

**Solutions from tickets.**

- File a feature request: #501, #646, #1175, #1662, #1802, #1812, #2059.
- Explain the feature: #710, #1027, #1094, #1392, #1698. Where the crawler found a URL (engineering trace, CS-1589): #561.

### H5 · Out of scope / noise (20 tickets · invisible)

**Log pattern.** None. This bucket holds WFA bugs, sales questions, duplicates, empty requests and tickets whose cause was never recorded.

**Why it works.** Not a Site Scanner runtime issue, or no evidence in the thread.

**Solutions from tickets.**

- Route to the right team (WFA fixes #1364, #2235, #2584; sales #3053; account #2241).
- Close duplicates and empty requests: #2001, #2062, #2289, #3099.
- Cause never recorded (resolved over Slack, in a meeting, or closed for age): #447, #583, #959, #2168. A List-mode workaround: #1033.
