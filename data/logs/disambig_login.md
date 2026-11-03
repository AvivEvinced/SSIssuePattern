# Disambiguation: login group (B1–B5, + A1 trap)

Status: complete (30 Coralogix queries, 2026-11-03). Windows: 2026-11-01..02 for live jobs, 7 days for B1/B4 scans, ticket dates for back-tests.

**Bottom line:** the unit of analysis must be the *request_id* (and the pod = browser session), not the job. Counting login-URL landings per job (old heuristic) over-calls B5: in scan-worker the login step itself logs `final url after redirections: <login URL>`.

## Sources / prior findings
- access_auth.md §6–7, page_level.md Q19/Q20, backtest.md (#2371, #3198, #3301).

## Q1 (2026-11-02, 24h): jobs with interaction steps (production crawl/scan workers)
19 jobs; step counts per job (start/type/click/missing/nofound):
- community.environicsanalytics.com crawl e9b16aea, ecb7428c: 4 req each, start+type x2+click; request url = `/auth/v3/mfa/manage?locale=en-us` -> **B1 candidate** (MFA page shows as page URL). Scan 204faf99: 1 req on `/auth/v3/signin`.
- spectrum crawl 2c241337 (mail3.spectrum.net, 18 start / 18 type / 8 nofound, 2 req), ec749f2e (ondemand.spectrum.net, 9 start/9 click/4 nofound, 1 req), b3984da6 (spectrumcommunitysolutions.net, 9/9/9 + 4 nofound) -> retried login with selector failure (B2 candidates).
- ulta scan 77d15816: 146 req, start/type x2/click per page (login is re-run per scanned page in scan-worker); ulta scan 25832a34 21 req; ulta crawls 3c04feb4, 4b39170c 1 req.
- snr.bell.ca scans (8e66ad07, e87505a5, f1534046) and crawls; informaticacloud scan 1e217977; cportal.jazz-fusion.net (#/login hash); mail.twcbc.com.
Observation: scan-worker runs the login interaction once per page (start per request_id); crawl-worker runs it once per job (1 request) unless retried.

## Q2: final-URL landings per job (same 24h)
login-like vs normal final URLs: ulta scan 77d15816 login 150 / normal 1452; ulta scan 25832a34 37/99; ulta crawl 3c04feb4 11 (guestservices — false positive of 'guest' regex)/124;
spectrum crawl 2c241337 login 18 (id.spectrum.net/login, 2 urls) / normal 0; ec749f2e and b3984da6 normal only (landing = seed); snr.bell.ca scan e87505a5 13 `/Login/` / 40;
environics crawl e9b16aea 10 `/auth/v3/signin` / 31 (`/auth/v3/password/forgot`, etc.); 204faf99 2 signin / 9 (`/auth/v3/register`).

## Q3 KEY FINDING: in scan-worker the login step itself produces a `final url after redirections: <login URL>` line
Timeline ulta scan 77d15816, request bfa7b063 (page /brand/bdy), 2026-11-02 13:22:39–13:24:31:
1. `starting page interaction plugin` → `current page url: about:blank`
2. `final url after redirections: https://www.ulta.com/u/login?state=…` (40 s later — the login page opening)
3. `element: #username, exists: true` → `typing text in element: #username` → `element: #password, exists: true` → `typing text in element: #password` → `element: form > div > button, exists: true` → `clicking element: form > div > button`
4. `current page url: /u/login?...` (still on login 0.7 s after click — normal, the POST is in flight)
5. 59 s later: `final url after redirections: https://www.ulta.com/brand/bdy` + `http status code is: 200` → page scanned OK.
Later requests in the same pod (dermal-elixir, hawthorne, …) show NO interaction start: login runs once per browser/session, then
pages reuse the cookies. 146 interaction starts vs 150 login landings in 77d15816 ⇒ almost every `/u/login` landing is the **login step itself, not session loss**.
⇒ Counting login-URL final URLs per job (the access_auth.md §6 heuristic) **over-calls B5**. Must look per request_id: the LAST final URL of the request.

## Q4: per-request classification (the right unit) — 10 jobs, 2026-11-02
Per request_id: lg = # login-like final URLs, nm = # other final URLs, st = interaction started.
Classes: `login_step_then_target` (st>0, lg>0, nm>0 = healthy login), `ended_on_login_after_interaction` (st>0, nm=0: login did not get through),
`ended_on_login_no_interaction` (reused session, bounced to login), `normal`.
| job | host | normal | login_step_then_target | ended_on_login_after_interaction | ended_on_login_no_interaction |
|---|---|---|---|---|---|
| 77d15816 scan | ulta.com | 1309 | 146 | 0 | 0 |
| 25832a34 scan | ulta.com | 80 | 21 | 1 | 1 |
| 8e66ad07 scan | snr.bell.ca | 34 | 6 | 0 | 18 |
| e87505a5 scan | snr.bell.ca | 35 | 5 | 0 | 8 |
| f1534046 scan | snr.bell.ca | 61 | 7 | 0 | 1 |
| 2c241337 crawl | spectrum (mail3) | 0 | 0 | 2 | 0 |
| e9b16aea crawl | environicsanalytics | 29 | 2 | 2 | 4 |
| ecb7428c crawl | environicsanalytics | 2 | 3 | 1 | 1 |
| 204faf99 scan | environicsanalytics | 9 | 0 | 1 | 0 |
| 1e217977 scan | informaticacloud | 188 | 0 | 0 | 0 |
⇒ ulta 77d15816 (the "/u/login landing" job family) is **healthy** — not B5.

## Q5: snr.bell.ca scan 8e66ad07 ordered timeline (58 requests, 6 pods)
Each pod: 1st request runs the login (lg=1,nm=1,st=1), then ~8–10 pages reuse the session. Requests that end on `/Login/` are interleaved
with successes and are always the same URL families (`folder_contents.jsp?folder=USER_*`, `AUTO_ATTENDANT_PROFILE`, `.../Auto_Attendant/Modify`),
in every pod; the next request after a bounce succeeds again without re-login.
⇒ **Not session loss**: the session survives; specific pages redirect to login (permission/role-gated pages for this user — looks like C4/scope
"page redirects to login", or a login-gated sub-app). B5 shape would be: after the first bounce, all later requests of that pod/session bounce too.

## Q6: environicsanalytics crawl e9b16aea timeline (2026-11-02 ~07:32 UTC)
- 4 `starting page interaction plugin` within 64 ms on 4 different request_ids ⇒ **4 parallel logins** (parallelism > 1 with login = B5 risk factor, visible directly in logs).
- Each: final url `/auth/v3/signin?...` → `element: #\:Rpdp8m\:--input, exists: true` → type → `#\:R51dp8m\:--input` type → `.ddxPWc` click.
  Selectors are React `useId` ids (`:R…:`) and a hashed class — B2 risk (they will change on a site release), but here they all exist.
- 21 s after click: 2 requests land on `/hc/en-us…`, `/hc/fr-ca` (login OK, 200); 1 lands on `/auth/v3/signin?role=end_user` (200) = **login did not get through for that worker** while siblings succeeded at the same second ⇒ not a wrong password (B3 would fail on all workers); consistent with concurrent-session conflict (B5) or bot-check (Zendesk, cf. #3420 A2).
- Afterwards discovered links include `/auth/v3/mfa/manage` (that is only a *link* being crawled, request url, not a post-login landing). **No final URL after the password step contained mfa/otp/challenge** ⇒ no B1 positive here.
- Also 403 on `/auth/v3/register`, 404 on a footer link (benign).

## Q7–Q8: spectrum crawls (2c241337 mail3.spectrum.net; b3984da6 spectrumcommunitysolutions.net) — B2 dynamic id, step-level view
2c241337 (parallelNum 25, 2 seeds → 2 parallel login attempts, each retried 3× × 3 rounds = 18 attempts):
`going to URL: https://mail3.spectrum.net/` → `completed. current url: https://id.spectrum.net/login?...` (≈10 s) → `element: #kite-label-input-3, exists: true` →
`typing text in element: #kite-label-input-3` → **28 ms later** `encountered error while running a function with timeout. retry count: N` with error.url = id.spectrum.net/login →
after 3 retries `got error while scraping No element found for selector: #kite-label-input-3` → `all attempts to scrape url had failed` (PAGE_INTERACTION_PLUGIN_ERROR, Scraper.ts:134). 0 pages crawled.
b3984da6: seed page → `clicking element: #login-button > button` → redirect to id.spectrum.net/login → `element: #kite-label-input-4, exists: true` → typing → same failure on `#kite-label-input-4`.
Reading: the failing selector is the SAME one that "exists: true" a few ms before. `kite-label-input-N` is a per-render generated id (N differs per page: 3 vs 4); the
element is re-rendered/detached between the existence check and the type action ⇒ **B2 (generated/unstable id)**. Browser was on the login URL (error.url) and never left it.
Last completed step = TYPE_TEXT on field 1; failure at the very first field ⇒ not B3 (credentials never submitted), not B4 (no click/2nd page reached).

## Q9–Q11: back-test #3301 (A1, bell.myprepaidcenter.com, crawl 601e87c1, 2026-09-25 15:18 UTC) — full ordered timeline
(other runs: 4c509f58 09-30 09:05, 9928fce5 / e68d2eb8 09-16)
1. `starting page interaction plugin` → `going to URL: https://bell.myprepaidcenter.com/login/user`
2. **+180 ms `[browser] [error] Failed to load resource: the server responded with a status of 405 ()`** (DataDome)
3. +10 s `final url after redirections: …/login/user` (same URL — no redirect), `current page url: …/login/user`
4. `element: #usernameText, exists: true` → `typing text in element: #usernameText` → +13 ms `encountered error while running a function with timeout`
   error = `{"url":".../login/user","message":"No element found for selector: #usernameText","element":{"type":"TYPE_TEXT",...}}` ×3 retries
5. `got error while scraping No element found for selector: #usernameText` → 3 scrape retries (31 s apart) → `all attempts to scrape url had failed` (PAGE_INTERACTION_PLUGIN_ERROR)
   → `CRAWL with id … failed due to PAGE_INTERACTION_PLUGIN_ERROR` → `successfully visited: 0 urls`, `failed to scrape: 1 urls`. No `http status code is:` line at all on the interaction page.
**The step shape is identical to the spectrum B2 case** (exists:true → type → "No element found" on the same selector, browser stuck on login URL).
The only separating line is the `[browser] … status of 405/403` between `going to URL` and `final url after redirections`.

## Q12: browser 4xx resource lines on the 2026-11-02 login jobs (A1 trap check)
spectrum 2c241337 / b3984da6 / ec749f2e: **none** ⇒ selector failure is B2, not A1. ulta 25832a34: 404×12, 422×1; snr.bell.ca: 404×3; environics e9b16aea: 404×8, 400×4 (4 req), 403×2 (1 req, /auth/v3/register).
A 404 on sub-resources is background noise; the A1 trap signal is a **403/405 on the login request itself** (same request_id, between `going to URL` and `final url after redirections`).

## Q13–Q16: back-test #3198 (B2 Chick-fil-A stale CLICK_ELEMENT) — NOT quiet after all
The previous back-test filtered on `context.url ~ 'order.chick-fil-a'`, but interaction lines carry the **seed** URL (www.chick-fil-a.com) as context.url,
so it looked at the wrong jobs. Searching the message for `order.chick-fil-a.com/location` finds crawl jobs **770c499d** (2026-09-03 15:56) and **8717415b** (15:58).
Timeline 770c499d (3 parallel attempts × 3 retries):
`starting page interaction plugin` → `going to URL: https://order.chick-fil-a.com/location` → final url = same → `element: #input-1, exists: true` → `typing text in element: #input-1` →
`sleeping 10 seconds` → `element: #location-panel-nearest > div.sc-jCAZBj.sc-kCDvBi.gKfGms.ZWyam > form > div > button, exists: true` → `clicking element: …` →
+157 ms error `{"url":"https://order.chick-fil-a.com/location","message":"No element found for selector: #location-panel-nearest > div.sc-jCAZBj…","element":{"type":"CLICK_ELEMENT",…}}`
×3 → `got error while scraping No element found for selector: …` → `all attempts to scrape url had failed` (PAGE_INTERACTION_PLUGIN_ERROR) →
`CRAWL with id 770c499d… failed due to PAGE_INTERACTION_PLUGIN_ERROR` → `successfully visited: 0 urls`. No 403/405.
⇒ #3198 **is** attributable: last step = CLICK_ELEMENT with a styled-components hash class, browser on /location. Upgrade back-test to YES.
**Recurring pattern (4/4 selector failures: #3198, #3301, spectrum ×2): the log says `element: X, exists: true` and a few ms later the action fails with
`No element found for selector: X`.** The `exists:` probe is not the same check as the action's lookup (visibility/actionability or re-render) — `exists: true` must not be read as "selector OK".

## Q17: cigna / zalando landings, 7 days (2026-10-27..11-03)
| job | sub | host | login-like final URL | n / reqs | normal final URLs |
|---|---|---|---|---|---|
| 634a92b2 | crawl | my.cigna.com | `/web/public/guest` | 96 / 25 | 0 |
| 4f19e263 | crawl | demo-my.cigna.com | `/web/public/guest` | 149 / 39 | 0 |
| 27bed93b | scan | chkout-my.cigna.com | `/web/public/guest` | 9 / 8 | 6 |
| 55e32fbd | scan | chkout-my.cigna.com | `/web/public/guest` | 14 / 10 | 95 |
| bedcf775 | scan | zalando | `accounts.zalando.com/authenticate` | 243 / 27 | 0 |
| ca8b7ff9 | crawl | en.zalando.de | `accounts.zalando.com/authenticate` | 9 / 1 | 0 |
(several other cigna jobs: normal only.) Ratio "login landings with 0 normal" = login never got through (B2/B4/A1/B3); "a few login landings among many normal" in scan-worker = mostly the login step itself (see ulta).

## Q18–Q19: zalando crawl ca8b7ff9 (2026-11-01 10:31 UTC) — two-step login, fails at step 2 of the configured script
`going to URL: https://zalando.de/login` → `[browser] … status of 400` ×2 per attempt → final url `accounts.zalando.com/authenticate?...` →
`element: #username, exists: true` → `typing text in element: #username` → `sleeping 20 seconds` →
`element: #theme-wrapper > main > section:nth-child(2) > form > button, exists: true` → `clicking element: …` → +18 ms error, error.url = /authenticate,
`No element found for selector: #theme-wrapper > main > section:nth-child(2) > form > button` ×9 → PAGE_INTERACTION_PLUGIN_ERROR → CRAWL failed, 0 pages.
Reading: identifier-first (username → Continue → password) flow = **B4 shape**, failing on the positional `nth-child` "Continue" button = **B2**; the 400 resource errors
(Akamai sensor?) leave an **A1** possibility. Last completed step = TYPE_TEXT username; failed = CLICK (continue); password step never reached.
Not distinguishable from logs alone which of B2/B4/A1 is root — needs a screenshot/DOM dump at failure (logging gap).

## Q20: cigna crawl 634a92b2 (2026-11-01 10:01 UTC, 25 seed URLs) — the 300000 ms cap appears, but as a *consequence*
Per request (25 req): `starting page interaction plugin` → `going to URL: https://my.cigna.com/web/public/guest` (this IS the configured login page) →
**+32 s** final url = same `/web/public/guest` → **+40 s** `element: #username, exists: true` → `typing text in element: #username` → +60 ms
`No element found for selector: #username` (TYPE_TEXT, error.url = /web/public/guest) ×3 → `got error while scraping No element found…` →
`bound run execution took more than 120000` ×4 → **`bound handleRequest execution took more than 300000 miliseconds` ×25 (one per request)** → `failed to scrape: 25 urls`, `successfully visited: 0 urls`.
⇒ the cigna `/web/public/guest` landing is **the login page, not a session-loss target**; the failure is at the first TYPE_TEXT (B2 / slow SPA render), and every request
runs the full login again (each seed URL logs in on its own, 119 interaction starts for 25 req). The 300000 ms cap here = "retries of a failing login exhausted the
per-request budget", so it is **not specific to B4**: it shows up whenever the login step is slow (32 s stabilize + 40 s wait) and keeps failing.
⚠ SECURITY: the interaction error JSON (`error.message.element.text`) contains the TYPE_TEXT **value** (here a username). If the password field fails, the password
would be logged in clear text. Logging gap / bug for backend: redact `element.text` in interaction errors. (Value not copied here.)

## Q21–Q22: `bound handleRequest execution took more than 300000` (B4 signature in taxonomy), 7 days
26 jobs (top: cigna 4f19e263 41, scan 8f53dbf6 40, crawl 3864e67f 39, cigna 634a92b2 25, scan 2626f95f 22 …). Records carry **no context.url/request_id**.
Of the top 10, only 3 have a login interaction (cigna ×2: selector failure + slow login page; ulta scan 1b9c5bcd: login OK). The rest are heavy, login-less
sites (huntington, cp24, bnnbloomberg, tsn.ca 30k pages, pearson) = D1 page-weight. ⇒ **300000 ms is not a B4 marker**; with login it means "the login step
kept failing/slow until the per-request budget ran out". No job showed a *partial* multi-step sequence that stopped without an error (a B4 tell would be:
last step logged = a CLICK that should navigate, then the next configured element never logged) — zalando is the closest (see Q18).

## Q23–Q24: B1 search — final URL path containing mfa/otp/2fa/verify/challenge/step-up/passcode, 7 days
First pass (regex over whole URL) is dominated by OAuth query params (`code_challenge=` on id.spectrum.net/login, zalando, xfinity) — **must match the path only**.
Path-only: `enrollnow.net/<lang>/verify-login` (crawl a00b1cce, ca06e674: member pages → /verify-login), `account.booking.com/step-up-auth` (from a booking confirmation
deep link), plus content pages (asurion "passcode", nvidia "challenges", blog tag /mfa/).
## Q25: enrollnow a00b1cce — no interaction configured; 17 pages succeed, then member pages (`/member-home`, `/message-center`, `/contact-information`) land on `/verify-login`
(70 req) interleaved with successes. Login-less crawl hitting gated pages = scope/C4, **not B1, not B5**.
⇒ **No B1 instance in 7 days of logs**: no job where the request that ran the password step (st>0, click logged) ended on an MFA/OTP path.

## Q26: per-request classification over ALL production jobs, 2026-11-01 00–12 UTC
Classes per request_id: `selector_fail` (interaction + No element found), `submitted_still_on_login` (interaction ran incl. a click, no selector error, every
final URL of the request is a login URL), `login_ok` (interaction + a non-login final URL), `bounced_no_login` (no interaction on that request, only login landings).
- `selector_fail`: cigna 634a92b2 (21 req).
- **`submitted_still_on_login`** (B3 shape): dealernavigator.com scan 2e285067 + crawl 997debb0; cigna chkout scan 27bed93b (1 of 8 req; the other 7: 6 bounced, 1 ok).
- `bounced_no_login` is dominated by **login-less** crawls following links to login pages (salesforce blogs, heroku /sso, argos/booking/expedia sign-in links,
  paieb.com/enrollnow.net `/verify-login`, maximus b2clogin, frontier). Must be gated on "job has interaction" before it means B5.
- evernorth scan 33a804f5: 5 login_ok + 8 bounced to `p.universal.login.evernorth.com/u/login/identifier` = the only B5-shaped candidate in the window (order not checked — budget).

## Q27: dealernavigator scan 2e285067 (2026-11-01 05:24 UTC) — the B3 shape, end to end
`starting page interaction plugin` → `going to URL: https://dealernavigator.com` → `[browser] … status of 403` ×4 (+1 s) + `[UserSessionService] checkUserSession: Error` →
final url `https://dealernavigator.com/idp/dealers/login/#/idp/dealers/login/?authCorrelationId=…` (+24 s) → `element: #userName, exists: true` → typing →
`sleeping 0.5 seconds` → `element: #password, exists: true` → typing → `element: #signIn, exists: true` → `clicking element: #signIn` → `sleeping 20 seconds` →
**`finished interacting with page successfully`** → `http status code is: 200` → engines run on … the login page (`analysis client was injected … /idp/dealers/login`,
focus plugin finds `#userNameDN-IDP-TEXT-FIELD`, `#passwordDN-IDP-TEXT-FIELD`, `#signInDN-IDP-BUTTON`) → `successfully scraped url. final url: …/idp/dealers/login…` → `successfully visited 1 pages so far` → job DONE, 1 page.
⇒ Every step succeeded, the submit was clicked, the interaction reported success, and the browser is **still on the login route 20 s later** = B3 shape
(wrong/expired password, or account locked). Same shape would be produced by A1 (403s on the first load!) or B1 if the MFA prompt renders on the same SPA route.
New marker: **`finished interacting with page successfully`** = interaction ended without exception; it is the anchor for "what URL was the browser on after submit".
Also: the scan "succeeds" (DONE, 1 page = the login page) — B3 is a **quiet** failure, like a 0/1-page crawl.

## Q28: evernorth scan 33a804f5 (2026-11-01 10:00 UTC) — clean B5 shape, per pod
5 pods each log in once (st=1, `finished interacting with page successfully`, 2 non-login final URLs, 200). Afterwards 4 pods keep scanning
`demo.app.evernorth.com/consumer/...` pages fine (all 200), but **pod `-grk8c`: after its successful login, every later request (5/5) lands on
`p.universal.login.evernorth.com/u/login/identifier`** (status still 200), while the sibling pods succeed on neighbouring URLs at the same minute.
⇒ session lost in one worker (B5). Signature: per pod (= browser session), sequence `login_ok → normal … → login, login, login …` (sticky), status 200 (no 401 logged).
Contrast snr.bell.ca (Q5): bounces are per-URL-family in every pod and **not sticky** (the next request succeeds) ⇒ gated pages, not B5.

---------------------------------------------------------------------
# Answers to the brief's questions
1. **Which step ran last before failure, and where was the browser?** Fully recoverable from crawl/scan-worker Info lines grouped by request_id ordered by time:
   `starting page interaction plugin` → `going to URL: <login url>` → `final url after redirections` / `current page url` → per step `element: X, exists: …` + `typing text in element: X` / `clicking element: X` / `sleeping N seconds`
   → either `finished interacting with page successfully` or `encountered error while running a function with timeout` whose `error.message` JSON has `url` (browser URL at failure), `message`, `element.type` (TYPE_TEXT/CLICK_ELEMENT) and `elementSelector`.
2. **B3 vs B5 — separable: yes (medium confidence).** B3 = on the request that ran the interaction, all steps + `finished interacting with page successfully`, and the *following* final URL is still the login URL (dealernavigator). Every request of every pod fails the same way; the job ends DONE with 1 page (the login page). B5 = the interaction request reached a non-login page (login OK), later requests of the **same pod** become login landings and stay that way (evernorth pod -grk8c), while other pods keep succeeding. Per-URL (non-sticky) bounces in all pods = gated pages (snr.bell.ca), not B5.
3. **Does MFA show as final URL after the password step (B1)?** Not observed: 0 cases in 7 days where the request that clicked submit ended on an mfa/otp/verify/challenge **path**. Path-only matching is mandatory (OAuth `code_challenge=` query params cause false positives). B1 would currently appear as the B3 shape (SPA MFA screens often keep the login route).
4. **B4: partial step sequence or the 300000 ms cap?** The cap is not B4-specific (26 jobs/7d, mostly login-less heavy sites; with login it is the result of a slow failing login, cigna). The usable B4 tell is a *partial sequence*: identifier-first flows (username → Continue → password) failing at the Continue click or at a password field that does not exist yet (zalando). It cannot be separated from B2 without a DOM/screenshot at failure.
5. **A1 trap (#3301):** the step trace of an A1-blocked login is identical to B2 (`exists: true` → action → `No element found` on the same selector). The only separator is `[browser] [error] Failed to load resource … status of 403/405` on the interaction request **between `going to URL` and the first `final url after redirections`**. Spectrum/Chick-fil-A have none; myprepaidcenter has 405; zalando has 400 (unclear); dealernavigator has 403 (so even the B3 example is A1-suspect).

# Decision rules (ordered)
| step | check | → | confidence |
|---|---|---|---|
| 0 | Job has `starting page interaction plugin`? If not, login landings = scope/gated pages (C4), not B. | gate | high |
| 1 | Interaction request has 403/405 `Failed to load resource` before the first final URL (same request_id), or `net::ERR_*` reset | A1 (not B2) | medium-high (1 back-test + contrast with 2 B2 jobs) |
| 2 | `Failed to execute 'querySelector' … is not a valid selector` in error.message | B2 (malformed) | high (#2371) |
| 3 | `No element found for selector: X` with error.url = login/interaction page; X looks generated (`:R…:`, `kite-label-input-N`, `sc-xxxx`, `nth-child`) | B2 (stale/dynamic) | high (#3198, spectrum ×2, cigna) |
| 4 | Failure at the 2nd step of an identifier-first flow (username typed, Continue click / password field missing), error.url is the IdP | B4 (or B2) | low |
| 5 | Interaction ended `finished interacting with page successfully`, the request's next final URL is still a login path, in all pods | B3 (or B1 / A1) | medium (1–2 jobs) |
| 6 | Request after submit ends on /mfa /otp /verify /challenge /step-up **path** | B1 | unverified (0 cases) |
| 7 | Pod: login_ok, then later requests of the same pod land on login and stay there; other pods fine | B5 | medium (1 job; ulta/cigna/snr re-classified as not-B5) |
| 8 | `bound handleRequest … 300000` | only "budget exhausted"; read with steps 1–5 | low for B4 |

# Still ambiguous
- B3 vs B1 vs A1 when the browser stays on the login route after a "successful" interaction (dealernavigator: 403s on load, SPA route).
- B2 vs B4 vs A1 on identifier-first IdPs (zalando: 400s + positional selector + 2-step flow).
- B5 vs gated pages if only one pod is active (no sibling pods to compare) — look at stickiness.

# Logging gaps (for backend)
1. Post-submit landing: after the last CLICK of the login script, log `login finished. url before: X, url after: Y, title, cookies set count, http status of the navigation` — needed for B1/B3/B5.
2. On interaction failure: DOM snippet / screenshot path + whether the element was found-but-not-visible vs not-in-DOM — the `exists: true` probe disagrees with the action lookup in 5/5 failures (B2/B4/A1).
3. `error.message.element.text` contains the typed value (username seen; password possible) — **redact** (security).
4. `bound handleRequest … 300000` lines have no context.url / request_id — add them.
5. Per-request "session state": is this request reusing a logged-in browser (pod/session id), and a `session check` result — needed for B5.
6. Login-page HTTP status: `http status code is:` is not logged for the interaction navigation (#3301) — add it (A1 vs B2).
7. Concurrent logins: log `parallelNum` + "login already running in N workers" (environics: 4 logins within 64 ms; spectrum parallelNum 25).
