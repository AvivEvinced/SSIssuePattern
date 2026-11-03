# Lifecycle & platform (families E, F) — log research

Scope: admin/admin-server, front/front-server, site-scanner front-webapp / admin-webapp / csv-worker / scrape-server.
Status: complete (2026-11-03). ~25 Coralogix queries.

## 1. Key structural discovery (JVM services admin/front/*-webapp)
- Records carry structured MDC in `$d.context`: `scan_id`, `property_id`, `job_id`, `tenant_id`, `tenant_name`,
  `property_name`, `user_id`, `operation_id`, `client` (UI / MCP / API ...). **IDs are truncated to the LAST 12 hex chars
  of the UUID** (e.g. scanId `8e66ad07-...-4c1e5573edc5` -> `$d.context.scan_id == '4c1e5573edc5'`).
- `$d.logger_name` (e.g. `c.e.p.service.scan.ScanService`) is structured too — good for filtering by component.
- `$m.templateid` is NOT stable for these services: the same message gets a different templateid per subsystem /
  deploy (e.g. "state changed" has >10 ids). Filter by logger_name + message regex instead of templateid.
- admin-server/front-server and admin-webapp/front-webapp all run the same lifecycle code (any of them may log a
  given job's transitions) — always query all four.

## 2. Top WARN/ERROR in scope (2026-11-02, 24h)
| count/day | subsystem | message |
|---|---|---|
| ~24k (all 4 svcs) | admin/front server+webapp | `failed to create entity for property with id: X. continuing to the next property` (background, per-property, recurs every cycle) |
| 5.3k | admin-server | `invocation of function (AdminUserToTenantController.list) took 32496 millis.` (internal admin, slow) |
| ~2.6k | all 4 | `SQL Error: 0, SQLState: 23505` + `duplicate key ... "key_type_constraint" Detail: Key (..)=(<propertyId><jobId><nextRunTime>, JobEntity) already exists.` + `Application exception overridden by commit exception` |
| ~1.9k | admin/front-webapp | `poll request failed - will retry at next poll interval` |
| 564 | front-server | `invocation of function (ProductExportService.checkReportExists) took ~32s` |
| 323+ | front-server/webapp | `controller rejected request with client error` / 37 `controller request failed with server error` |
| ~300 | front | `TokenController.generateAccessToken failed (NotFoundException:Service account not found)` (API/MCP auth) |
| ~330 | scrape-server | `scan page <url> failed, scan id is <id>. last successful result file ...` |
| ~100 | front-server | `ScanPagesController.overview took 13s`, `ScanController.get took 13s` |
| ~85 | admin/front-webapp | `failed to generate CSV for scan X for owner Y (poller timeout|poll request failed)` + `Failed handling sample failure of SCAN_RESULT_EXPORT task ... ScanResultExportPoller.onFailed() bug` |
| 49 | front-server | `An invalid request caller ID was received: MCP` |
| 12 | admin-server | `ERROR: deadlock detected` (Postgres) |

## 3. Reconstructing one job's timeline (verified on a real scan, 2026-11-02)
Filter by the 12-char suffix of propertyId (or scanId / jobId) — the MDC context follows the job **into scrape-server**:
```
source logs | filter $d.context.property_id == '<last12 of propertyId>'      // or $d.context.scan_id / job_id
| filter $d.logger_name ~ 'ScanService|JobService|JobPoller|JobScheduler|UrlSetService|CrawlService|JobMessageListener|AppCommunicatorUtils|ScanResultExport|Email'
     || $m.severity == WARNING || $m.severity == ERROR
| choose $m.timestamp, $l.subsystemname, $d.logger_name, $d.context.scan_id, $d.context.job_id, substr($d.message:string,0,250) as msg
| orderby $m.timestamp asc
```
Observed happy-path sequence for a SCAN job (front-server → scrape-server):
1. `JobService` "a new job was created: <jobId>" → "job with id: X, changed state to: RUNNING and phase WAITING_FOR_SCAN"
2. `JobPublisher` "publishing a new job message" → `JobPoller` "a new job was created X. property id: P, job type is: SCAN" / "a new poll was created for job id"
3. `JobMessageListener$JobMessageHandler` "handling a job message" → "starting scan. property id: P, job id: J, scan id: S"
4. `TenantDomainService` "[blacklist] denied domains ..." (tenant/system blocked domains) → `CreateScanRequestConfigurationHelper` deniedUrlPatterns
5. `AppCommunicatorUtils` "Sending POST request to http://<scrape-server>/api/scans" → "Request finished successfully after N millis" (**dispatch hop; failure here = E3**)
6. `ScanService` (front) "Successfully created a scan with ID=S" → "Scan with ID=S state changed from NEW to RUNNING" → JobService phase RUNNING_SCAN
7. scrape-server `c.evinced.scan.service.ScanService`: "Changed scan S state from NEW to READY_TO_RUN" → "Creating worker messages" → "Creating worker job" →
   `KubernetesJobTransformer` → "Successfully created job for scan: S. Monitoring its status" → "state from READY_TO_RUN to RUNNING"
8. scrape-server polling: "polling scan with id S. Kubernetes job state: {"status":"RUNNING","totalPodsCount":6,"runningPodsCount":1,"succeededPodsCount":0,"failedPodsCount":0}" (k8s job health!)
9. `PageAnalysisResultListener` "scan S page analysis <url> completed" per page; front "Scan with ID=S state changed from RUNNING to INGESTING" → "GENERATING_CSV to DONE"
10. URL-set (crawl) jobs: "URL set with ID=U state changed from NEW to RUNNING / RUNNING to DONE"; METRIC_EVENT JSON lines
   (`eventType: CrawlSummary|ScanSummary`, status, totalUrlsCount, totalSuccessUrls, totalFailedUrls, totalIssues) summarise each run.
Next-run: `for property: <propertyId>, the next schedule job time is: 2026-11-09T13:00` (JobScheduler, Info, logged per run).

## 4. The structured error object: `$d.error.{type,message,stack_trace}`
Every JVM ERROR/WARN with an exception carries `$d.error.type` (Java class) and `$d.error.message` — **the real cause is
here, not in $d.message** (which is often a generic wrapper). Workhorse:
```
source logs | filter ($l.applicationname=='admin'||$l.applicationname=='front'||$l.subsystemname=='admin-webapp'||$l.subsystemname=='front-webapp'||$l.subsystemname=='scrape-server'||$l.subsystemname=='csv-worker') && $d.error.type != null
| groupby $l.subsystemname, $d.error.type, substr($d.error.message:string,0,120) as emsg aggregate count() as n, any_value(substr($d.message:string,0,160)) as sample | orderby n desc
```
Also `$d.context.client` tells WHO triggered: `JobScheduler` (scheduled run), `UI`, `MCP`, API... and `$d.context.job_time` = the scheduled fire time.

### 4a. "failed to create entity for property with id: X. continuing to the next property" = scheduler couldn't start a scheduled run
The scheduler loops properties; per-property failure reasons (24h, 2026-11-02, all 4 services):
| error.type | error.message | n/day | sub-issue |
|---|---|---|---|
| LimitExceededException | The license has expired. To upgrade your account please contact us at support@... | ~15k | **E4** (licence) |
| LimitExceededException | No license exists. Please create a trial license... (on TokenController.generateAccessToken) | 36 | E4 / F4 (API/MCP token) |
| InvalidInputException | No URLs were supplied | ~4.8k | config (property seeds empty) — not E |
| InvalidInputException | Property URL set is not defined | ~2.3k | config |
| InvalidInputException | Scan must have at least one URL | ~2.1k | config / crawl found 0 URLs |
| InvalidInputException | The time the runner waits before it starts must be less than 30 seconds | ~480 | config validation drift (settings saved before rule) |
| NotFoundException | property not found for propertyId: X | ~1k | deleted property still scheduled (E2-ish orphan schedule) |
These repeat every scheduler cycle for the same property — **background noise unless the ticket's propertyId appears**.
To check a ticket: filter `$d.context.property_id == '<last12>' && $d.message ~ 'failed to create entity'` and read `$d.error.message`.

### 4b. Crawl dispatch failure = "Failed running create crawl request for URL set with ID=U" (UrlSetService, ERROR)
Low volume (~5/day). Seen cause: `$d.error.message = "Job failed due to timeout/failure"` from `JobPoller.onTimedOut` — the
job sat ~24h (context.job_time 2026-11-01T13:30 -> failed 2026-11-02T13:31) and the poller timed it out; then
`JobService "job with id: J, changed state to: FAILED and phase FAILED"`. So this message wraps both real POST refusals (E3,
e.g. scrape-server pool exhaustion in Zendesk) and 24h job timeouts — **read $d.error.message to tell them apart**.

## 5. "duplicate key ... key_type_constraint ... (<propertyId><jobId><runAt>, JobEntity) already exists" — YES, a scheduler symptom (two flavours)
Always `$d.context.client == 'JobScheduler'`, logger `o.h.e.jdbc.spi.SqlExceptionHelper`, preceded by `SQL Error: 0, SQLState: 23505`
and followed by `Application exception overridden by commit exception` (JsonMappingException on UrlSetDiscoveryConfigurationEntity).
The key = propertyId(36) + jobId(36) + scheduled run time `yyyy-MM-ddTHH:mm`. Extract it:
```
... | extract $d.message into $d.dk using regexp(e=/=\((?<ids>[0-9a-f-]{72})(?<runat>\d{4}-\d\d-\d\dT\d\d:\d\d), JobEntity/)
| groupby $l.subsystemname, $d.dk.runat aggregate count() as n, distinct_count($d.dk.ids) as jobs
```
1. **Benign replica race** (admin-server + front-server): runAt == the current slot (e.g. 2026-11-02T10:00 logged at 10:00:03),
   ~1–19 keys per slot, ~164/day per service. Both services run JobScheduler; the loser hits the unique key. The run still happens.
2. **Stuck schedule (real E2 signal)** (site-scanner admin-webapp/front-webapp): runAt is in the PAST (2025-07-21T07:00,
   2025-12-11T08:00, 2025-12-14T08:00, 2025-12-17T11:30, 2026-02-15T01:00) and the same key repeats **192×/day (every 7.5 min)**
   — next-run never advances, so that property's scheduled scans silently stop. 14 properties affected on 2026-11-02.
   Rule: `runAt < now - 1h` ⇒ stuck schedule; check the ticket property's key.

## 6. "Error loading scan" — slow/failed API calls (E5 / F3)
### 6a. Durations: `c.e.c.l.f.FunctionLogger` logs EVERY controller call
`invocation of function (<Controller>.<method>) took N millis.` (Info; **WARNING when > ~10 s**), and
`invocation of function (X) failed (<ExceptionType>:<msg>) after N millis. (args: ...)` (Error). Parse:
```
source logs | filter ($l.subsystemname=='front-server'||$l.subsystemname=='front-webapp') && $d.logger_name=='c.e.c.l.f.FunctionLogger'
  && ($d.message ~ 'ViewsController'||$d.message ~ 'ScanController'||$d.message ~ 'ScanPagesController'||$d.message ~ 'ScanIssuesController'||$d.message ~ 'PropertyOverview')
| extract $d.message into $d.fx using regexp(e=/\((?<fn>[A-Za-z]+\.[A-Za-z]+)\) (?<what>took|failed)/)
| extract $d.message into $d.fm using regexp(e=/(?<ms>[0-9]+) millis/)
| groupby $d.fx.fn, $d.fx.what, $m.severity aggregate count() as n, avg($d.fm.ms:number) as avgms, max($d.fm.ms:number) as mx
```
(nested named groups + `percentile(0.99, x)` arg order: fraction first.) 6h sample 2026-11-02 12–18Z front-server:
| fn | n | avg ms | max ms | WARN (>10s) |
|---|---|---|---|---|
| ScanController.list | 5466 | 86 | 50047 | 23 (avg 23.7 s) |
| ScanPagesController.overview | 159 | 2.0 s | 18.7 s | 16 |
| ScanIssuesController.overview | 161 | 1.5 s | 20.9 s | 16 |
| ScanController.get | 134 | 0.9 s | 13.0 s | 2 |
| ScanPagesController.list | 56 | 2.7 s | 7.0 s | 0 |
| ViewsController.list | 341 | 26 | 234 | 0 (3 failed, NotFound) |
Front-end request timeout likely ~10–30 s → WARN rows on ScanPages/ScanIssues/ScanController are the backend-timeout ("Error loading scan") signal; group them by `$d.context.tenant_name` / scan_id.
Also: `ProductExportService.checkReportExists took ~32 s` (564/day) and admin `AdminUserToTenantController.list took 32 s` (5.3k/day, internal).

### 6b. 4xx/5xx: `c.e.c.web.api.RestExceptionHandler`
`controller rejected request with client error` (4xx) / `controller request failed with server error` (5xx) +
`An internal error occurred and the response is altered to the default error message. Original message was: ...`.
Detail in `$d.context.request_uri` (e.g. `uri=/api/property-overview`), `$d.error.type`, `$d.error.message`, `$d.error.stack_trace`, `$d.context.tenant_name`.
Day 2026-11-02:
- 35× 5xx NullPointerException on `/api/property-overview` for ONE tenant, stack `PagesEnricherStrategy.mapPropertyViewToScanIdsAndPageFilter` → dashboard/overview fails for a tenant whose property view references something missing (**E5 view-config / F3 dashboard not loading**).
- 4xx NotFound "Scan could not be found" / "Scan X not found" on `/api/scans/<id>`, `/api/scan-results/<id>` (deleted scan, E5 scan_deleted_not_found); one leaks as 5xx (javassist.NotFoundException — bug).
- 4xx "could not find view" (ViewsController.get), "Property could not be found" on `/api/views`, `/api/properties/<id>` (stale links / deleted property).
- 4xx on `/api/service-accounts/<id>` (+ TokenController.generateAccessToken): "Service account not found" (~300/day, 2 SAs hammering), LimitExceededException "No license exists" / "license has expired" → API/MCP token issues (**F4 / E4**).

**DataPrime gotcha (important for all patterns):** `$d.message ~ 'a|b'` is a *substring/free-text* match, NOT regex — alternations
and `(?i)` silently match nothing. Use `matches($d.message:string, /regex/)` (regex literal) for alternation.

## 7. Exports (F1), completion emails (F1), integrations (F4) — 2026-11-02, 24h
- **ScanResultExportService** (CSV and XLSX): `failed to generate CSV|XLSX for scan <scanId> for owner <ownerId> (poller timeout)` and
  `(... poll request failed)`; error.type InternalException "Scan <id> not found" → export requested for a scan that no longer
  exists keeps polling until timeout. Companion: `PollTaskRunnerService` "Failed handling sample failure of SCAN_RESULT_EXPORT task
  with ID=T - this reflects a ScanResultExportPoller.onFailed() bug, please fix!" and `ScanResultExportPoller` "poll request failed -
  will retry at next poll interval" (NullPointerException "get(...) must not be null", ~1.8k/day, single owner — a stuck poll loop).
- `ScanIssuesController.exportIssues failed (ConflictException: Export for this scan and filter already running)` — user re-clicked export.
- `ProductExportService.checkReportExists took 16–32 s` (564/day, WARN) — slow export status check (F1/E5).
- **Emails**: `CrawlCompletionEmailListener` "Failed to send crawl completion email for urlSetId=U" (error NotFoundException
  "Didn't find property P for mail to user X" → property deleted) + `UrlSetService` "CrawlCompletionEmailListener failed processing
  URL set state changed (RUNNING -> DONE) event" (UnexpectedRollbackException). `ScanCompletionEmailListener` "Failed to send scan
  completion email for scanId=S" with NoHttpResponseException "api.sendgrid.com:443 failed to respond" → **SendGrid outage/transient** (F1).
- **MCP**: `c.e.f.context.OperationContextFilter` WARN "An invalid request caller ID was received: MCP" (49+8/day) — MCP client sends
  a caller-id header the server doesn't accept (F4 mcp_auth); plus TokenController.generateAccessToken "Service account not found" /
  LimitExceededException (no licence) for API/MCP tokens.
- Jira / ADO: nothing in 24h (see §8 for wider search).

## 8. Infra / dispatch failure lines (14 days, 2026-10-20 → 11-03)
**Environment note:** production customer traffic is on `admin/admin-server` + `front/front-server` (48 tenants scanning in 14 d).
`site-scanner/{admin,front,scrape}-webapp` see only ~3 tenants ("Site Scanner QA UI", "Evinced Dev Team", one customer owner) —
looks like a secondary/test deployment. Weight webapp-only signals (stuck JobEntity keys, export poll loops) accordingly.

| line | logger / subsystem | 14-day volume | meaning |
|---|---|---|---|
| `kubernetes job failed - see job for more details Job(... name=<scanId> ... reason=BackoffLimitExceeded ...)` | KubernetesJobStateTransformer, scrape-server (ERROR) | 10 (5 tenants, 5 days) | worker k8s job (job name == **scanId**) exhausted pod retries → scan fails (E1/E3; worker crash/OOM) |
| `kubernetes job is in an unknown state Job(...)` | same, WARN, scrape-server/scrape-webapp | 13 + 21 | k8s job with BackoffLimitExceeded/CompletionsReached not mapped → may leave scan RUNNING until timeout |
| `polling scan with id S. Kubernetes job state: {"status":..,"failedPodsCount":N}` | scrape-server ScanService Info | per poll | failedPodsCount>0 = workers crashing |
| `Sampling scan with ID=S for its status passed its timeout, marking it as FAILED` | c.e.p.service.scan.ScanService (ERROR) admin/front | ~5 in 14 d | scan stuck (no status) until scan timeout → RUNNING→FAILED (E3; stuck scan) |
| `Scan ingesting state for S not found` | ScanService WARN | 11 | ingest phase lost its state record (E3) |
| `Failed running create crawl request for URL set with ID=U` | UrlSetService ERROR | ~5/day | crawl dispatch failed / timed out (E3) |
| `HikariPool-1 - Failed to validate connection ... (This connection has been closed.)` | PoolBase WARN, all JVM | ~100 | DB connection recycled — benign unless burst; "Connection is not available" (pool exhaustion, E3/E1) **not seen** in window |
| `publish to queue <id>-csv failed (attempt N): Connection refused. retrying` → `Could not publish message to queue: <id>-csv after 12 attempts / 120000ms` | CsvGenerationRabbitCommunicator | 11 + 23 | RabbitMQ unreachable → CSV export never generated (F1, infra) |

Jira / Azure DevOps: no WARN/ERROR lines in 3 days in any in-scope service (see §9).

## 9. Log SCHEMA CHANGED between June and autumn 2026 — patterns must handle both
- **Old (verified 2026-06-29):** JVM records have NO `$d.message`/`$d.logger_name`/`$d.context`; the whole line is plain text in
  `$d.body`: `2026-06-29 13:54:44,284 [ERROR] [Thread-..] [opId=..] [jobId=..] [client=UI|JobScheduler|API] [scanId=..] [userId=..]
  [jobTime=..] [urlSetId=..] [tenancyId=..] [tenancyName=bell media] [CrawlService.kt:NN] <text>` and stack-trace lines arrive as
  separate ERROR records (`\tat com.evinced...`).
- **New (Nov 2026):** `$d.message` + `$d.logger_name` + `$d.context.*` (12-char ids) + `$d.error.{type,message,stack_trace}`.
- Portable form: `create $d.txt from firstNonNull($d.message:string, $d.body:string)` then match on `$d.txt`, and tenant =
  `firstNonNull($d.context.tenant_name:string, <regex tenancyName=(...)\] on $d.txt>)`.

## 10. Platform-wide incident detector (E1) — validated on the 2026-06-29 outage (tickets #2751/#2752/#2755, 11:00–15:00Z)
```
source logs
| filter ($l.applicationname == 'admin' || $l.applicationname == 'front' || $l.subsystemname == 'scrape-server') && ($m.severity == ERROR || $m.severity == CRITICAL)
| create $d.txt from firstNonNull($d.message:string, $d.body:string)
| filter !($d.txt ~ 'failed to create entity for property') && !($d.txt ~ 'duplicate key') && !($d.txt ~ 'SQLState')
      && !($d.txt ~ 'overridden by commit') && !($d.txt ~ 'service-accounts')
| extract $d.txt into $d.mdc using regexp(e=/tenancyName=(?<tenant>[^\]]+)\]/)
| groupby roundTime($m.timestamp, 1h) as hour
  aggregate count() as errors, distinct_count(firstNonNull($d.context.tenant_name:string, $d.mdc.tenant:string)) as tenants,
            any_value(substr($d.txt,0,200)) as sample
| orderby hour asc
```
Result 2026-06-29 (distinct tenants with ERROR per hour): baseline 0–5 → **14 at 10:00Z, 9 at 11:00Z** (first ticket 11:00Z)
→ back to 1–6 → **32 at 18:00Z** (backlog of JobScheduler jobs failing: `[client=JobScheduler] [jobTime=2026-06-29T00:00]`).
Raw error COUNT barely moves (≈450–800/h, dominated by chronic noise) — **the distinct-tenant count is the signal**.
Rule of thumb: tenants_with_errors ≥ 3× the 24h median (and ≥ 8) in one hour ⇒ platform incident (E1); then look at `sample`
and at `kubernetes job failed`, `passed its timeout`, `Failed running create crawl request`, Rabbit/Hikari lines in that hour.
Complementary: same groupby over `state changed from \w+ to FAILED` / `changed state to: FAILED` lines (distinct scans failing).

## 11. Sub-issues with NO / weak log evidence
- **F4 Jira / ADO**: zero runtime lines in front/admin (7 d); only a DB migration filename mentions jira. Integration calls are
  probably made client-side or by a service outside scope → not diagnosable from these logs. MCP has a weak signal (§7).
- **F2 export count semantics**, **F3 UI confusion** (sorting, stale filters, Edge): no server-side trace by nature; F3 only via
  5xx/NPE on `/api/property-overview` etc.
- **E2 timezone bug**: next-run lines exist but carry no timezone; need comparison with property settings (not in logs).
- **E4 concurrent-scan limit**: only licence-expired / no-licence LimitExceededException observed; no "concurrent" limit text in sample.
- **F1 10k-row Excel limit / "max allowed issues"**: no matching line in 1–3 day windows (may be enforced client-side or rare).
- "HikariPool-1 - Connection is not available" (scrape-server pool exhaustion, E3) not seen in the 14-day window (only benign
  "Failed to validate connection").
