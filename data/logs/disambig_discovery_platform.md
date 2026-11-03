# disambig — discovery_platform (C1/C2/C3/C5/C6 vs A2/A3/login; E1/E3/E5/F3)

Status: done (~22 queries). Window mainly 2026-11-01/02 production; Part 2 2026-10-20..11-02. Rules with queries: disambig_discovery_platform.json.

## Part 1 — 0–1-page crawls

### Q1–Q2 (2026-11-01..02, production crawl-worker): 35 jobs with max `successfully visited N pages so far` <= 1
Per-job aggregate (one query, `count_if` per signal; see rules JSON). Observations:
- `filtered out: N urls` is printed **exactly once per crawl job** (fo_lines = 1 on all 35) — it is a job-level total, not per page.
- In jobs with notincl > 0, `filtered` == count of `not including url in result url set` lines (e.g. vistaprint.fr 24/24, ga-nmsn 11/11).
- Three shapes:
  (a) **seed non-200** (12 jobs: sainsburys, natwest chatbot, sky helpforum, skyawardsfyc, verizon mycareer, comcastpreview x2, xfinityprepaid x2, philadelphia.comcast...): one `http status code is: <non-200>`, 0 not-included, filtered 0 → block/seed error family (A1/A2/C4), not C.
  (b) **seed 200 + links discovered but all dropped** (9 jobs: vistaprint.fr 24, ga-nmsn 11, ky/md/co newhire 3–4, dealernavigator, discover, capitalone x2, xfinity nowtv, collegeboard x2): s200 = notincl+1 → pages were fetched (status 200) and THEN excluded → C1/C2 (reason decides).
  (c) **seed 200, filtered 0, no other signal** (14 jobs: ulta, cportal.jazz, design.comcast, business.comcast, smartsimple x2, internet.xfinity, xfinity planbuilder, elleactive.hearst, boxtops qa, charterverify mock, dinersclubcash, applicationcenter.capitalone, ...): no link was even discovered → C6 vs A3/A2-200 vs login wall (indistinguishable without title/link-count).

### Q3: reason + non-200 histogram for shapes (a)/(b)
| job (seed) | signal | reading |
|---|---|---|
| sainsburys.co.uk, natwest askarchie, verizon mycareer, sky helpforum, xfinityprepaid x2, comcastpreview x2 | single `http status code is: 403` on seed, nothing else | A1/A2 block at request 1 (no successes before) |
| philadelphia.comcast.com | 503 on seed | A2 candidate (Cloudflare/Akamai challenges often 503) or E-side outage on customer site |
| skyawardsfyc.sky | 400 on seed | seed/WAF rejects request (A1/C4) |
| xfinity.com/nowtv | `final url not included in whitelist` url=www.**stg**.xfinity.com/now | **C2** (redirect to staging host) |
| apply.capitalone.com/fc/index.html#/... | `final url not included in whitelist` url=apply.capitalone.com/ | **C2** (path-scoped whitelist; seed redirects to root) |
| vistaprint.fr (24), collegeboard.org (1) | `max number of successful visits was reached` with max visited = 1 | **page cap = 1** in property config (C3/C5 family "page caps"; C7-like misconfig), not discovery failure |
| ga-nmsn.com (7 pdf + 4), mdnewhire/ky-newhire/co newhire (3–4 pdf), discover, dealernavigator, capitalone/coders | only `content type application/pdf` and `sanitized url was already visited` on `#/route` URLs | **C5/C6 SPA**: the only hrefs are PDFs and #fragment routes collapsed by "ignore fragments" → C5 (grouping) fix = untick ignore-fragments |
| ap.collegeboard.org | `final url was already visited` (/home redirect of seed) | single real page, redirect collapse; C6/A3 candidate |
No `language is not included in whitelist` and no regex reason among these 0–1-page jobs in this window; **C1 had no live example** in 2 days.

### Q4: seed final URL + interaction + browser errors for shape (c) and the two whitelist jobs
- **Correction to Q3**: for xfinity.com/nowtv and apply.capitalone.com the seed's `final url after redirections` equals the seed
  (no host change); the URL rejected as `final url not included in whitelist` is a *discovered link* (www.stg.xfinity.com/now,
  apply.capitalone.com/). So these are "page with 1 out-of-scope link" (C6-like thin page / benign), **not C2**. C2 requires the
  rejected URL == the seed's final URL (or host(final) != host(seed)).
- Shape (c) splits by the seed's final URL:
  - final URL path contains login (`comcast.smartsimple.com/s_Login.jsp`, `comcastinnovationfund.smartsimple.com/s_Login.jsp`,
    `applicationcenter.capitalone.com/login`) and **no** interaction lines → **login wall without login configured** (B-family / C6 lookalike).
  - interaction ran (`typing text in element: #login_txtUsername` → `#login_txtPassword` → `clicking element: #login_btnLogin`) and
    final URL still `…#/login` (cportal.jazz-fusion.net) → **login failure** (B2/B3), crawl ends at 1 page without any error line.
  - ulta.com: login interaction ran, then **137** `not handling request … max number of successful visits was reached` → links exist; page cap = 1.
  - remaining (design.comcast, business.comcast/support/home, internet.xfinity [browser 403 on a resource], xfinity planbuilder, elleactive.hearst.it,
    qa.boxtops4education [browser 405], mock.charterverify, dinersclubcash) → seed 200, final URL = seed, filtered 0, no error:
    **C6 vs A3 vs A2-200 cannot be separated**. A browser-level 403/405 on a sub-resource (internet.xfinity, boxtops) tilts toward A2/A3 (bot manager script).

### Q5–Q7: 0-visit jobs and a true whitelist case (2026-10-20..11-01)
- **No production crawl job lacks the `successfully visited` counter** (2026-11-01..02): every job prints at least 1 → "0 pages" crawls show as maxv=1 (the seed counts even when it 403s).
- Jobs with maxv<=3 and a whitelist reject (12 days): 6 — xfinity nowtv (10-25), discover personalloans, discover bank, app.marq.com
  (rejected = login.microsoftonline.com SSO), bellmedia x2 (rejected = identification.bell.ca / account.bellmedia.ca/login).
  → a whitelist reject whose URL is an IdP/login page is a **login/SSO redirect (B4/B5)**, not C2.
- **Full timeline, job 9020c59c (xfinity, 2026-10-25 10:01:52–10:02:15, 22 s)**:
  `received message: {"used_plugins":["LinkExtractorPlugin"]…` → `detected user agent: … Chrome/112` → **`allowed domains: {xfinity.com,stg.xfinity.com}`** →
  two seeds queued (`going from url: about:blank to url: https://www.xfinity.com/nowtv` and `… https://www.stg.xfinity.com/now`) →
  seed1: `final url after redirections: …/nowtv` · `http status code is: 200` · `detected language: en` · `running plugin LinkExtractorPlugin` ·
  `successfully scraped url` · `[blacklist] dropping blacklisted discovered url: facebook…` · `request was handled successfully` · `successfully visited 1 pages so far` →
  seed2: final url stg…/now · 200 · `not including url in result url set. reason: final url not included in whitelist` →
  `finished handling all requests` → **job summary lines: `successfully visited: 1 urls` / `failed to scrape: 0 urls` / `filtered out: 1 urls`** → `crawler finished running successfully`.
  Note stg.xfinity.com **is** in `allowed domains` yet was rejected → the reject came from the include regex/path whitelist, i.e. **C1-type**, not a domain (C2) problem.
  So the reason text "final url not included in whitelist" covers BOTH domain whitelist (C2) and include-regex (C1); the `allowed domains:` line separates them.
- No count of links extracted per page; LinkExtractorPlugin only logs "running plugin". Only discovered links that are DROPPED are logged (`[blacklist] dropping…`, `not including url…`).

### Q8: shape-(c) full message inventory (design.comcast cd4a3e61, qa.boxtops4education 569ef768)
Both jobs: `allowed domains: {<seed host>}` → seed → final url = seed → `http status code is: 200` → `detected language: en(-us)` →
`running plugin LinkExtractorPlugin` (~0.1 s) → `successfully scraped url` → `successfully visited 1 pages so far` → `finished handling all requests` →
`efficiency coefficient is: 1` → `successfully visited: 1 urls` / `failed to scrape: 0 urls` / `filtered out: 0 urls`. **Nothing else** — no link count,
no page title, no DOM/HTML size, no "no links found" warning. boxtops additionally has `[browser] [error] … status of 405` on a sub-resource (bot-manager beacon?).
→ C6 / A3 / A2-with-200 / genuinely single-page site are **identical in logs**.

### Q9: METRIC_EVENT records (2026-11-02 00–12h)
`METRIC_EVENT: {json}` lines exist in admin-server/front-server (production) and admin-webapp/front-webapp (development/QA — filter `"environment.name":"production"`):
- **CrawlSummary** (~35/12h prod): taskId (= urlSetId = crawl-worker k8s.job.name), propertyId, propertyName, tenancyName/Id, status (DONE/FAILED),
  **totalUrlsCount**, jobId, opId, client (JobScheduler/API/UI), jobTime, userId, scanId (crawl+scan). One line per crawl → the per-job summary.
  No reason/visited/filtered/failed counts, no seed or final URL.
- **ScanSummary**: propertyId, scanId, status, totalSuccessUrls, totalFailedUrls, totalIssues, totalCriticalIssues, creationTimestamp, client, jobTime.
- scrape-server `scan.page.complete` (22k/12h): per page state, requestedUrl, scanTotalUrls, tenant. `scan.page.ingestion.elastic.complete`: totalUrls.
- Example: Capital One `applynow.capitalone.com` CrawlSummary status DONE **totalUrlsCount 0** → a 0-URL crawl is reported as DONE (not FAILED).

### Q10–Q11: CrawlSummary totalUrlsCount=0 → **the validated "visited counter" query misses every 0-page crawl**
- Production CrawlSummary 11-01..02 with totalUrlsCount <= 1 or status != DONE: **>= 60 rows (limit hit), almost all `DONE` with totalUrlsCount 0**
  (comcast regional sites, xfinity, capitalone, cigna, sky, subway, PSAT, Zalando...). Only one FAILED (Salesforce "Developer - All Except Docs").
- Joined on taskId = crawl-worker k8s.job.name: these jobs **never print `successfully visited N pages so far`** (it is only printed after a
  successful visit). They do print the end-of-job summary `successfully visited: 0 urls` / `failed to scrape: F urls` / `filtered out: N urls`.
  The validated `crawl_visited_counter` query (regex `visited (\d+) pages`) yields null for them → **0-page crawls were invisible in Q1 and in access_auth.md §9**.
  Use the summary line (or CrawlSummary) instead.
| taskId | property | allowed domains | summary v/f/fo | other | reading |
|---|---|---|---|---|---|
| 3864eaf1 | military.xfinity.com | {military.xfinity.com} | 0/0/1 | seed 200, 1 not-included | seed itself rejected → C1/C2 |
| 420e3d9e | applynow.capitalone.com | {capitalone.com} | 0/0/1 | seed 200, 1 not-included | seed rejected → C1/C2 |
| 7c6bdd4b | "wowtv.de/hilfe with Reggex" | {wowtv.de} | 0/0/6 | 6×200, 6 not-included | **C1** (include regex) |
| cb558b2f | tinseltownholiday.com | {tinseltownholiday.com} | 0/1/0 | no status line | seed failed to load (C4/A1/DNS) |
| 634a92b2 | my.cigna.com | {my.cigna.com} | 0/25/0 | no status line | every page failed (login/interaction or block) |
| be8ebcce | www.subway.com - en-us | {subway.com} | 0/0/0 | 6×200 + 3 non-200 | redirects/locale — see Q12 |
| b1af4368 | Developer - All Except Docs (Salesforce) | {developer.salesforce.com} | no summary | 675k lines, 130k not-included, FAILED | **C3 scope blow-up → job timed out** |

### Q12: all production 0-visit crawls (summary `successfully visited: 0 urls`), 2026-11-01..02 — **~59 jobs** (vs 35 jobs with exactly 1)
One aggregate per job: summary visited/failed/filtered, reason counts, statuses, `allowed domains`, seed `final url after redirections`, `failed due to`.
| bucket | n | signature | examples | sub-issue |
|---|---|---|---|---|
| seed redirects to a host NOT in `allowed domains`; wl = filtered = 1; 1×200 | **~33** | final host ∉ allowed | 14 `<state>.comcast.com` → corporate.comcast.com/stories/local/<state>/; effectv.com → comcastadvertising.com; wingslax.com → nll.com; wellsfargocenterphilly.com → xfinitymobilearena.com; comcastseasonal → xfinity.com/seasonal; skynewsinternational → skynewsdistribution.sky; skyaccessibility.sky → sky.com/help; military.xfinity → www.xfinity.com; la-newhire; capitalonesupplierdiversitysummit → capitaloneenvisionsummit.com; productionservices.sky → skypostproduction.sky (136 rejects) | **C2** (high) |
| final host ∈ allowed but still `final url not included in whitelist` | 4–5 | include regex / path rejects the seed | satsuite.collegeboard.org/in-school-assessments (x2 PSAT), healthcare4mi.com/en, capitalone.com/credit-cards (allowed {capitalone.com}), williamsinn.com gallery (2) | **C1** (medium: needs regex to confirm; subdomain semantics of allowed list unverified) |
| same as above but final URL is `/unavailable` | 1 | wowtv.de "with Reggex" → www.wowtv.de/unavailable (6 rejects) | geo/availability page → **A7** masquerading as C1 |
| final URL is an IdP/login (id.bluemovie.com/…/auth) + wl reject | 1 | bluemovie.com | **B4/B5** login redirect, not C2 |
| `failed due to DNS_ERROR_COULD_NOT_FIND_URL` | 6 | blueface, tinseltownholiday, rtds-wiki (internal), focus.cloud.capitalone, investing.capitalone, developer.capitalone (+51 PDF content-type rejects) | **C4** seed unreachable / A1 private host |
| `failed due to PAGE_INTERACTION_PLUGIN_ERROR` | 5 | zalando (accounts.zalando.com/authenticate), mail3.spectrum (id.spectrum.net/login), accredo (#/en/login), ondemand.spectrum, spectrumcommunitysolutions | **B2** (login) |
| failed N>0, final URL `/web/public/guest`, no status line | 2 | my.cigna.com (25), demo-my.cigna.com (41) | session/login wall (B5) |
| `failed due to OPEN_PAGE_TIMEOUT` | 3 | poladarchive.comcast, (es-)apply.internetessentials | D1/A1 tarpit |
| INTERNAL_ERROR | 1 | cmcsa.com | ? |
| 200s + non-200s, 0 visited, 0 filtered, 0 failed | 1 | subway.com en-us | unexplained (counter mismatch) |
**Answer to "does the combination separate C1/C2/C6/A2-A3?"** — yes for C2 vs C1 vs C4 vs B2 at 0 visits (allowed-domains line + final URL + reason);
**no** for C6 vs A3 vs A2-with-200 at 1 visit (identical message inventory). A2/A1 with non-200 seed are separable by the status line.

### Q13: "too many pages" example — Salesforce "Developer - All Except Docs" (b1af4368), CrawlSummary FAILED, totalUrlsCount 0
- Runs ~10.8 h (2026-11-01 ~05:40 → 16:33 UTC), **HTTP-mode crawler** (`sending HTTP request to url:` 131k, not the browser path) with a
  **different progress template: `crawling page. visited 83320 pages so far`** (the validated counter regex `visited (\d+) pages` matches it, but the summary lines never came).
- 130k `successfully scraped url` vs 129,745 `not including url … reason: final url is included in [blacklist]` and only 793 `request was handled successfully`
  → the crawler fetches every page and drops 99% **after** fetching (exclude regex applied post-fetch); 868 `got error while trying to upload file to cloud`.
- Ends FAILED with 0 URLs (timeout) → **C3 scope too broad** (include = whole developer.salesforce.com, exclude "docs" only post-filter). Rule: blacklist-reject ratio > 90% and visited counter > 10k → C3.
- C5 (grouping) signal = `sanitized url was already visited` share; seen on SPA fragment sites (ga-nmsn, dealernavigator, discover) — only a few lines, medium confidence.

## Part 2 — E1 vs E3 vs E5 vs F3

### P1: hourly spread of failure lines (admin-server + front-server, 2026-10-27..11-02)
Lines: `Scan|URL set … state changed from X to FAILED`, `job … changed state to: FAILED`, `Failed running create crawl request`, `passed its timeout`, `HikariPool`.
**Max distinct tenants in any hour = 3** (2026-10-28 10:00: capitalone-sdk-testing ×5, Progressive, Zalando at 10:31); 0 Hikari lines all week.
→ baseline for E1: ≤3 tenants/hour with failures. The June E1 outage (backtest.md) showed as a worker-volume collapse, not as a message pattern.

### P2–P4: what the 10-28 10:01 burst was
- Pair per URL set, same millisecond: `Failing URL set <id> due to job timeout/failure` (Info) → `Failed running create crawl request for URL set with ID=<id>`
  (Error, `RuntimeException: Job failed due to timeout/failure`, client=JobScheduler). No crawl-worker or scrape-server line for that URL set,
  and no ERROR on scrape-server in 09:55–10:10 (only SQLState 23505 duplicate-key noise + slow `checkReportExists`).
  → it is the scheduler failing the *previous* job of that property (its job timed out / never finished) at the next tick: a **per-property chain stop (E3)**, not an outage.
- 14 days: ~20 properties, each 1–2 occurrences (Progressive, Zalando, Cigna, Sky UK, Salesforce, Deloitte Canada, Charter, capitalone-sdk-testing×3 props...), always a few
  minutes after a :00/:30 schedule tick.

### P5–P8: UI/API failures (front-server, 2026-11-02)
- `RestExceptionHandler` "controller request failed with server error" (5xx) carries `$d.context.request_uri` as **`uri=/api/...`** (prefix "uri=") and
  `operation_id`, which joins to the `FunctionLogger` line `invocation of function (<Controller.method>) failed (<Exception>) after N millis. (args: …)`.
- 5xx 24h: **NullPointerException ×35, 1 tenant (bell media), `uri=/api/property-overview`, PropertyOverviewController.list,
  stack `PagesEnricherStrategy.mapPropertyViewToScanIdsAndPageFilter(PagesEnricherStrategy.kt:42)`** → product bug (**F3**, user sees "Error loading" = E5 symptom).
  `javassist.NotFoundException Scan <id> not found` ×2 → deleted scan (E5 `scan_deleted_not_found`). 4xx dominated by `Service account not found` (317, noise).
- Slow calls: FunctionLogger `took N millis` is logged at **Warning when N > 10 000** (Info below): ProductExportController.checkReportExists up to 66.7 s (282, 1 tenant),
  ScanController.list up to 50 s (2 tenants), ScanIssues/ScanComponents/ScanPages overview ~20 s, PropertyOverviewController.list 27 s → **E5 timeout** candidates
  (front 502 likely at ~60 s; the 502 itself is not logged by front-server).

## Decision rule (ordered) — details + queries in the JSON
0. List small crawls by the **end-of-job summary** `successfully visited: N urls` (or CrawlSummary totalUrlsCount), never by the progress counter.
1. Seed non-200 only → A1/A2/A5 (503/202 lean A2). 
2. `failed due to DNS_ERROR…` → C4; OPEN_PAGE_TIMEOUT → D1/A1.
3. PAGE_INTERACTION_PLUGIN_ERROR, or interaction ran and final URL still /login|/auth|/guest → B2/B3/B5.
4. Whitelist reject on the seed's final URL whose host ∉ `allowed domains` → **C2** (IdP host → B4/B5).
5. Whitelist reject with host ∈ allowed domains, or `language is not included` → **C1** (final URL /unavailable → A7).
6. `max number of successful visits was reached` with visited 1 → page cap = 1 (config).
7. Only PDF + `sanitized url was already visited` on #routes → C5/C6 SPA.
8. Seed 200, final = seed, filtered 0, no errors → **C6 / A3 / A2 unresolved** (sub-resource 403/405 leans A2/A3).
9. >10k visits with >90% `final url is included in` (blacklist) rejects, FAILED → C3.
10. ≥~5 tenants/hour failing (baseline ≤3) or worker-volume collapse → E1.
11. One property: `Failing URL set … due to job timeout/failure` + `Failed running create crawl request`, or Hikari at run time → E3.
12. RestExceptionHandler 5xx (`request_uri` = `uri=/api/…`) + FunctionLogger `failed (<Exception>)`: NPE/IllegalArgument → F3; `took N millis` Warning (>10 s) or NotFound scan → E5.

## Logging gaps (for backend)
- No count of links extracted per page; no page title / HTML size / DOM size → C6 vs A3 vs A2 cannot be separated.
- Reject reason doesn't say WHICH rule (domain vs include regex vs language) → C1 vs C2 needs the allowed-domains line by hand; include regex only in the credential-bearing config dump.
- The progress counter skips 0-visit crawls; CrawlSummary has only status + totalUrlsCount (no visited/failed/filtered/top reason/seed final URL).
- `Job failed due to timeout/failure` hides the underlying cause (E3 vs E1).
- No API status/latency access log for 502/504 → E5 is detected only by slow `took N millis` warnings.
