# disambig_access — can the per-job timeline separate A1 / A2 / A4 / A5 / A6 / D1?

Status: complete (19 Coralogix queries, window mostly 2026-10-27..11-03 production). Inputs: access_auth.md, page_level.md, backtest.md, validated.json.

## 1. Per-job status histogram + timeline (crawl-worker, production, 2026-10-27..11-03)

Query family: `http status code is: N` (Info) grouped by `k8s.job.name` x code, with min/max timestamp and 10-minute buckets.
40 jobs had >=59 lines of 403/429/202/405 in 7 days. Seven reconstructed in detail:

| job (host) | 200 | 403 | 429 | 202 | timeline shape | read as |
|---|---|---|---|---|---|---|
| 2df63642 (lenovo.com) | 3 | 878 | 0 | 0 | 2x200, 1x503, then 100% 403 within the first minute, to the end | **A1 hard block after ~3 requests** |
| 95b3a1f2 (sky.at) | 52 | 402 | 0 | 0 | 200s for ~2 min, then 403 for the rest | A1 (block trips after N requests) |
| cb160fdb (pbs.org) | 190 | 1,340 | 0 | 0 | 140x200 then 403 dominates (84%) | A1 (rate-triggered WAF, block sticks) |
| 489c88f2 (nvidia.com) | 1,219 | 3,993 | 0 | 0 | **waves**: 403 bursts (300-1,200 per 10 min) alternating with clean 200 windows (18:30-18:40, 19:40-20:00) | A1 rate-based WAF (Akamai) — 403 used as a rate-limit; operationally A5-like |
| 10a3d82b (des.wa.gov) | 4,913 | 26 | 813 | 0 | 429 = 64% in first 20 min, decays 165 -> 50 -> 0; then ~1,000 x 200 per 10 min | **A5 rate limit (429 ramp then recovers)** |
| 37ebce10 (booking.com) | 4,959 | 0 | 4,758 | 176 | 200 and 429 interleaved the whole run (~50/50) | A5 (sustained 429) |
| 8ffa9d66 (booking.com) | 2 | 0 | 4,220 | 5,255 | from minute 1: only 202 + 429, 2 x 200 total, for 1h50m | **A2 challenge (202 = AWS WAF captcha interstitial) + A5** |

Per-URL check (same 7 jobs): every URL is visited exactly once (max 2 lines per URL, `mixed` 200+bad URLs = 0 or 1).
=> **a blocked status is NOT retried and is never followed by a 200 for the same URL** — the "202 interstitial then 200"
sequence does not exist in crawl-worker; a 202 page is final for that URL. 403/429 pages count as visited pages.

## 2. User agent (config dump) vs block outcome — A6

One query joins, per crawl job, the UA from `config is: {... --user-agent=...}` with that job's status histogram
(production crawl-worker, 7 days, 499 jobs). "blocked" = 403/405/429/202 >= 50% of status lines.

| UA class (config) | jobs | no status line at all | >=50% blocked | some block | clean | any-block share (of jobs with status) |
|---|---|---|---|---|---|---|
| Chrome/112 default | 371 | 31 (8%) | 45 | 24 | 271 | 20% |
| Chrome/65 (not Headless) | 36 | 2 | 7 | 13 | 14 | **59%** |
| HeadlessChrome/65 (+/- EvincedBot) | 34 | **18 (53%)** | 0 | 0 | 16 | 0% |
| no config line | 22 | 1 | 1 | 4 | 16 | 24% |

Reading (corrected after drilling into the jobs):
- The 18 HeadlessChrome/65 "no status line" jobs are NOT blocked: they are salesforce/heroku/tableau/mulesoft crawls with
  25-74,000 `successfully visited` lines but zero `going from url` / `http status code` lines — a different crawler code path
  that does not log per-page status (logging gap, see below). HeadlessChrome/65 jobs that do log status (capitalone, discover
  family) are clean or tiny (1-5 pages; several capitalone seeds die with DNS_ERROR_COULD_NOT_FIND_URL).
- The Chrome/65 block excess is a **tenant confound**: 17 of the 20 blocked Chrome/65 jobs are collegeboard.org subdomains
  (Cloudflare 429, 20-65% of pages) plus booking.com (429) and pbs.org (403). Same tenants on Chrome/112 were not available to compare.
- => UA in the config is a **risk factor, not a discriminator**: an old UA does not change the shape of the status histogram,
  so A6 vs A1/A5 cannot be told apart from status data alone. The only decisive A6 evidence is an intervention:
  same property, UA switched to Chrome/112(+), block disappears (as in #3340: 10-09 seed fails, 10-14 after override 40+ pages).

## 3. A4 static egress IP — node pool IS logged per job

`$d.resource.attributes['k8s.node.name']` prefix, production, 2026-10-30..11-02 (3 days):

| subsystem | node pool | jobs | lines |
|---|---|---|---|
| crawl-worker | crawls-pool-stat* | 285 | 10.0M |
| crawl-worker | **crawls-fast-pool** | 8 | 0.95M |
| crawl-worker | (no node name) | 17 | 2.8M |
| scan-worker | scans-pool-stati* | 329 | 6.2M |
| scan-worker | **scans-node-pool-f / -de** (non-static) | 88 | 7.5M |
| scan-worker | (no node name) | 42 | 3.8M |

So the earlier finding "all prod jobs on *-stat pools" (6-hour sample) does not hold over 3 days: ~20% of scan jobs run on the
non-"stat" pool `scans-node-pool-*` (salesforce/heroku/tableau/mulesoft, portal.ct.gov, bellmedia/rds/tsn/noovomoi, superbet, cigna checkout).
These are almost never blocked (7-day: jud.ct.gov 32 bad / 786, tableau 15 / 4,888, all others ~0), i.e. those properties
don't need allowlisting. **Telling detail:** a scan of `api64.ipify.org` (an "what is my IP" page) ran on scans-node-pool —
someone checked the egress IP by hand, i.e. A4 is currently diagnosed manually. Also `prizm.environicsanalytics.com` (same
tenant as #3420) scanned on the non-static pool.
Rule: a blocked job (403/429 or OPEN_PAGE_TIMEOUT host-wide) whose `k8s.node.name` is NOT `*-pool-stat*` => **A4 candidate**
(the job egressed from a non-static IP); blocked on `*-pool-stat*` => A4 unlikely (unless the customer allowlisted the wrong IPs).
Confidence medium: pool name -> static NAT mapping is inferred from the name, not confirmed with infra. No crawl-worker job on
crawls-fast-pool logged an `http status code` line, so fast-pool crawls can't be checked by status.

### 3b. The static-IP flag IS logged (admin-server) — direct A4 check
admin-server `Sending POST request to http://<scrape-server>/api/crawls|/api/scans with body: {"id":"<jobId>", ... "useStaticIp":true|false, ...}`
(Info; body also holds puppeteerArgs and login config => extract only the flag, never print the body).
- `id` in the body == crawl-worker/scan-worker `k8s.job.name` (verified: cigna 5405cea2, salesforce 80e47079, heroku 6ae2a097, mulesoft 74b34e12).
- 7 days: `useStaticIp:false` on ~37 requests (salesforce family, tsn.ca, ctvnews, noovo.info, superbet.ro, chkout-my.cigna.com, 23 scans with no seed host parsed);
  1 day (11-01): true 192 / false 19.
- These false jobs are exactly the ones on `crawls-fast-pool` / `scans-node-pool` — and the false CRAWLS are the ones that log
  `successfully visited` but **no `going from url` / `http status code` lines** (the HeadlessChrome "no status" jobs of section 2).
  => useStaticIp=false routes the crawl to a different (fast-tier) code path that does not log per-page status.
=> **A4 rule: blocked job + `useStaticIp:false` in its admin-server request body (or node pool not `*-pool-stat*`) => A4.**
A4 failure mode "flag is true but customer allowlisted a different IP" stays invisible (no egress IP logged).

## 4. A2 challenge markers
- 202 is the only usable A2 signal. booking.com job 8ffa9d66: 5,255 x 202 + 4,220 x 429, 2 x 200 for 1h50m (AWS WAF challenge
  answers 202 with a JS interstitial). The "202 then 200 for the same URL" sequence never occurs (URLs are visited once).
- `[browser]` lines mentioning `awswaf` (AWS WAF SDK) appear in EVERY booking.com job (11-01: 20-38k lines/job), including
  jobs that are 50-100% status 200 => the SDK is loaded on normal pages; **an awswaf/perimeterx asset line is not proof of a challenge**.
  `challenges.cloudflare` / `/cdn-cgi/challenge` / `captcha-delivery` (DataDome): 0 lines on 11-01.
- A Cloudflare managed challenge answers **403** (cf. #3420 environicsanalytics: 403 + 1 page) => A2-Cloudflare is
  indistinguishable from A1 in logs (no page title / response header / body size logged).

## 5. OPEN_PAGE_TIMEOUT: tarpit block vs heavy pages (D1)

Per job (crawl-worker, production, 7d, >= 20 OPEN_PAGE_TIMEOUT): fail share = OPT / (OPT + status-200 lines).

| host (job) | OPT | 200 | fail share | tail | 30-min shape | read as |
|---|---|---|---|---|---|---|
| www.aa.com (3212d59a) | 4,513 | 366 | **92%** | OPT continue 58 min after last 200 | 199 ok first 30 min, then **flat ~210 OPT / 30 min, ok 0-14** for 10 h | **tarpit block after ~200 successes (A1, Akamai)** |
| www.ynet.co.il (8e12f178, 13948a6b) | 348 / 211 | 11 / 4 | 97-98% | OPT outlast last 200 (20 min) | — | block (A1) |
| uat.totalwine.com (2 jobs) | 885 / 85 | 197 / 39 | 69-82% | 200 continues to end | — | UAT behind allowlist? (A1/A4) |
| bnnbloomberg / cp24 / xfinity | 437 / 356 / 630 | 225 / 272 / 614 | 51-66% | 200 to end | — | ambiguous |
| www.pearson.com (e7c1503e) | 4,348 | 5,153 | 46% | 200 to end | oscillates 60-210 OPT vs 3-444 ok per 30 min for 16 h | intermittent throttling (A5-like tarpit) or slow site — ambiguous |
| nvidia.com (7 jobs) | 274-1,019 | 1,219-3,382 | 15-30% | 200 to end | + 403 waves (section 1) | A1 rate-based WAF |
| frontier.com (9c137d5b) | 112 | 5,074 | **2%** | 200 to end | OPT only in 2 bursts (40, 72) with steady ~800 ok / 30 min | **D1 / transient** |
| my-rewards.ca, moo.com, bell.ca, discover.com, totalwine.com | 22-67 | 529-17,683 | 0.4-7% | 200 to end | — | D1 (heavy pages) |

Facts that matter:
- "Failures start after a run of successes" is true for EVERY job: first OPT is ~195 s after the first status line in all 30+ jobs
  (that is just the timeout + retry duration). Useless as-is; what separates is **what happens after**: a block flips the
  job to a **saturated plateau** (~210 OPT / 30 min = every worker slot waiting on a timeout, 200s drop to ~0) and OPT outlast the last 200.
- Repetition across runs (same host, several jobs, 7d): nvidia 2,559 failing URLs, **955 (37%) succeeded in another run** -> the
  URL is not heavy, the crawler was throttled (block/rate-limit). ynet 481 failing URLs, 0 ever succeeded, 78 failed in both runs ->
  block. totalwine.com 39 failing URLs, 8 repeat, share 7% -> D1. aa.com: 1 run only (4,513 distinct URLs, each failing once).
- No URL is retried after OPEN_PAGE_TIMEOUT within a job (max 1 line/URL/job for aa.com; nvidia max 5 over 7 jobs).
- Jobs with `useStaticIp:false` (tsn.ca 4,670 OPT, noovomoi 1,374, noovo.info 768, bellmedia 351, salesforce 26) log OPT but **no status lines**,
  so the share can't be computed for them (fast-tier path) — use `successfully visited` count instead.

## 6. Decision rule (per k8s job; queries in disambig_access.json)

1. **A4 first** (cheap, decisive when it fires): admin-server request body for the job id has `"useStaticIp":false`, or the
   job's `k8s.node.name` is not `*-pool-stat*` (crawls-fast-pool, scans-node-pool) AND the customer says they allowlist our IPs -> **A4**. (medium-high; 37 false requests/7d, mapping verified on 4 job ids)
2. Status histogram of the job (`http status code is: N`):
   a. 202 >= 30% of status lines -> **A2** (AWS WAF / bot-manager JS challenge). (medium; 2 booking jobs)
   b. 429 >= 10% -> **A5**. Shape: 429 front-loaded and decaying to 0 = crawler throttled successfully (des.wa.gov);
      sustained ~50% = hard rate-limit (booking, collegeboard). (high for "is rate limiting"; 28 jobs/7d)
   c. 403/405 >= 50% -> **A1** (or A2-Cloudflare, see still-ambiguous). Sub-shape: blocked from request 1-3 (lenovo, starz.ca #2903, environics #3420)
      = IP/geo/UA deny; 200s first then 403 that never recovers (sky.at, pbs) = WAF reputation trip; alternating 403 waves (nvidia) =
      rate-based WAF rule -> advise slower crawl, like A5. (high; 45+ jobs)
3. If 1-2 point to a block, read the UA from the job's `config is: {` line: Chrome/65 or HeadlessChrome -> flag **A6 candidate**,
   recommend re-run with a current UA; confirm A6 only if the block disappears. (low as a discriminator; UA does not change the histogram shape)
4. OPEN_PAGE_TIMEOUT jobs: fail share = OPT/(OPT+200).
   - >= 80%, or the last 30+ min contain only OPT at a flat plateau (~parallelNum-bound) -> **A1 tarpit** (aa.com, ynet). (medium-high)
   - <= 10%, 200s continue to the end, failing URLs repeat across runs and never succeed -> **D1**. (medium)
   - 10-80% or failing URLs succeed in other runs -> throttling (A5/A1 rate-based) vs slow site: ambiguous; check whether OPT share
     drops when parallelNum is lowered. (low)
5. 1-page crawl with status 200 only and no block lines -> not this group (A3/C6, see access_auth.md).

## 7. Still ambiguous
- A1 vs A2 (Cloudflare managed challenge): both 403 + 1 page; no title/header/body-size logged (#3420 looked identical to A1).
- A1 vs A6: an old UA is visible, but it's a risk factor, not a discriminator (blocked Chrome/65 jobs are mostly the collegeboard tenant's 429s).
- A1 (rate-based WAF 403) vs A5: nvidia-style 403 waves behave like rate limiting but use 403.
- A4 "flag on, wrong IP allowlisted": invisible, no egress IP logged.
- Tarpit (A1/A5) vs D1 for mid fail shares 10-80% (pearson 46%, xfinity 51%).

## 8. Logging gaps (for the backend team)
- crawl/scan-worker per page: response headers subset (`server`, `cf-ray`, `x-amzn-waf-action`, `x-datadome`, `akamai-grn`), page `<title>`,
  body bytes -> separates A1 vs A2 vs A3 and names the vendor.
- crawl-worker per job: effective egress mode + public egress IP (`useStaticIp`, NAT IP) at job start -> A4 without admin logs.
- fast-tier crawl path (useStaticIp=false): no `going from url` / `http status code` lines -> per-page status needed.
- OPEN_PAGE_TIMEOUT payload: last network state (bytes received, TTFB, main-document status if any, number of pending requests) ->
  tarpit (0 bytes / no TTFB) vs heavy page (document 200, sub-resources pending) for D1.
- Per-job summary line at end of crawl: counts by status and by failure type, current concurrency/backoff -> one-line A1/A5/D1 triage.
- UA actually sent (from the browser, `navigator.userAgent`) at job start, next to `browser was opened successfully. version:`.

## 9. Examples
| job | host | sub (true/likely) | timeline |
|---|---|---|---|
| 2df63642 | lenovo.com | A1 | 2x200, 503, then 878x403 to end (10 min) |
| 95b3a1f2 | sky.at | A1 | 52x200 for ~2 min then 402x403 |
| cb160fdb | pbs.org | A1 | 140x200 then 84% 403 |
| 489c88f2 | nvidia.com | A1 (rate-based) | 403 waves of 300-1,200/10 min between clean 200 windows; + 603 OPT |
| 10a3d82b | des.wa.gov | A5 | 429 64% in first 20 min, decays to 0, then ~1,000x200/10 min |
| 37ebce10 | booking.com | A5 | 200/429 ~50/50 for 2 h (+176x202) |
| 8ffa9d66 | booking.com | A2 (+A5) | only 202 + 429 from minute 1, 2x200 total |
| 3212d59a | aa.com | A1 tarpit | 199x200 first 30 min, then ~210 OPT/30 min plateau for 10 h (92%) |
| 9c137d5b | frontier.com | D1 | 2% OPT in two short bursts, steady 200s |
| 80e47079 / ec3a73b0 | salesforce / tsn.ca | A4 indicator (useStaticIp=false) | fast-pool path, no status lines; tsn 4,670 OPT |
| backtest | starz.ca #2903, myprepaidcenter #3301 | A1 | 403 seed + 1 page; 405 on login then selector error |
| backtest | investor.capitalone.com #3340 | A6 | seed ERR_HTTP2_PROTOCOL_ERROR / timeouts; fine after UA override (only intervention reveals A6) |
| backtest | environicsanalytics #3420 | A2 | 403 + 1 page = A1 lookalike |
| backtest | NatWest #2185/#2914 | A5 | run outside log window; rule 2b would apply |
