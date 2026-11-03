"""Log-appearance tree: how a Site Scanner problem shows up in Coralogix.

Three layers, written for support engineers:
  L1  Stage   — where in the run it went wrong (a question a support person can answer from the UI/job state)
  L2  Symptom — what the logs say, in plain words
  L3  Pattern — the concrete log pattern (signature ids in data/logs/*.json) and the root-cause sub-issues it points to

Run: python3 scripts/logtree.py -> data/logtree.json (also merges signatures, validation and back-test results)
"""
import json, os, glob
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (id, title, plain-language question/description, [L2 ...])
# L2: (id, title, what it looks like, [L3 ...])
# L3: (id, title, pattern text, [sig_ids], [sub_ids], how to read it / next check)
TREE = [
 ("S1", "The run never started", "No crawl or scan job appears at the scheduled time, or the property shows no new run.", [
   ("S1.1", "Scheduler refused to create the run", "admin/front log 'failed to create entity for property' with a reason in error.message.", [
     ("S1.1a", "Licence expired or limit reached", "failed to create entity … + error.type LimitExceededException ('The license has expired')",
      ["scheduler_failed_to_create_entity", "limit_exceeded_license"], ["E4"], "Check the tenant licence / limit.running-scans-count in Retool."),
     ("S1.1b", "Property setup incomplete", "failed to create entity … + 'No URLs were supplied' / 'URL set not defined' / 'runner wait < 30s'",
      ["scheduler_failed_to_create_entity"], ["C7", "H3"], "Fix the property settings (seed list, runner wait)."),
     ("S1.1c", "Schedule points at a deleted property", "failed to create entity … + 'property not found'",
      ["scheduler_failed_to_create_entity"], ["H5"], "Clean up the orphan schedule; usually harmless."),
   ]),
   ("S1.2", "Schedule stuck or skipped", "The next-run time is in the past or repeats; a duplicate-job error repeats every ~7.5 min.", [
     ("S1.2a", "Same past slot keeps colliding", "duplicate key … key_type_constraint … JobEntity already exists — with a run time in the past, repeating",
      ["scheduler_duplicate_jobentity"], ["E2"], "Current-slot duplicates are a harmless race between two schedulers; a past slot that repeats = stuck schedule."),
     ("S1.2b", "Next run time looks wrong", "for property: <id>, the next schedule job time is: <time> — compare with the UI schedule",
      ["scheduler_next_run"], ["E2"], "No time zone in the line: compare with the property's configured time zone."),
   ]),
   ("S1.3", "Crawl request never reached the crawler", "admin/front 'Failed running create crawl request'; scrape-server DB pool errors.", [
     ("S1.3a", "Dispatch refused or timed out", "Failed running create crawl request for URL set … (+ scrape-server HikariPool Connection is not available)",
      ["crawl_dispatch_failed"], ["E3"], "Evinced-side. Re-run; escalate if several properties are affected."),
   ]),
 ]),
 ("S2", "The run started but the job died", "The job moved to FAILED, or stayed RUNNING until a timeout.", [
   ("S2.1", "Many customers failing at the same time", "Distinct tenants with errors per hour jumps far above the 0–5 baseline; worker log volume drops.", [
     ("S2.1a", "Platform incident", "aggregate: distinct tenants with ERROR per hour (chronic noise excluded); scan-worker volume drop",
      ["platform_incident_tenant_spread"], ["E1"], "Check status channel; tell the customer it is Evinced-side and re-run after the fix."),
   ]),
   ("S2.2", "Job failed on Evinced infrastructure", "Kubernetes job failure, job marked FAILED by the poller, or upload errors.", [
     ("S2.2a", "Worker pod failed", "kubernetes job failed … reason=BackoffLimitExceeded (name = scanId)",
      ["k8s_job_failed"], ["E3", "E1"], "Often out-of-memory on huge sites; check page count / heavy pages (D1)."),
     ("S2.2b", "Job timed out and was marked FAILED", "Sampling scan with ID=… passed its timeout, marking it as FAILED / job … changed state to: FAILED",
      ["scan_status_timeout_failed", "job_state_failed"], ["E3", "E1"], "Look at the same job's crawl/scan logs: was it stuck on blocked pages (S3) or idle?"),
     ("S2.2c", "Engine package failed to load on the worker", "ENGINES_PLUGIN_ERROR … ENOENT / ENOTEMPTY / zlib",
      ["engines_plugin_error_worker_fs"], ["E3"], "Evinced-side race on the worker; not the customer's page. New sub-issue candidate."),
     ("S2.2d", "Result upload throttled", "got error while trying to upload file to cloud … (GCS 429)",
      ["gcs_upload_rate_limited"], ["E3"], "Harmless if a later write succeeds; signal only when the scan ends incomplete."),
   ]),
 ]),
 ("S3", "The site did not serve the pages", "Pages came back with an error status, a network error, or never finished loading.", [
   ("S3.1", "The site answered with an error status", "'http status code is: N' — logged at INFO, so error-level filters miss it. Look at the share per job/host.", [
     ("S3.1a", "Mostly 403 / 405", "http status code is: 403|405 on most URLs of the job (often 1 page visited)",
      ["http_status_non200", "http_status_doc_non200"], ["A1", "A4", "A2", "A6"],
      "Blocked. Check: admin-server crawl request body useStaticIp=false or a non '*-pool-stat*' node pool → A4; 202 share ≥30% → A2; config-dump UA Chrome/65 → A6 candidate; else A1."),
     ("S3.1b", "Many 429", "http status code is: 429 across many URLs",
      ["http_status_non200", "http_status_doc_non200"], ["A5"], "Rate limited: move to speed-tier slow, check sibling properties scheduled at the same time."),
     ("S3.1c", "202 bursts", "http status code is: 202 on many URLs",
      ["http_status_doc_non200"], ["A2"], "Likely a bot-manager 'please wait' interstitial (unconfirmed)."),
     ("S3.1d", "401 on pages after login", "http status code is: 401 / browser 401 errors after a successful login step",
      ["http_status_doc_non200", "browser_resource_status"], ["B5"], "Session lost: check parallelism and whether logout URLs are crawled."),
     ("S3.1e", "Many 404 / redirect to an error page", "http status code is: 404, or final url … /404 /500",
      ["http_status_doc_non200", "final_url_login_or_error_landing"], ["C4"], "Seed or listed URLs are dead or redirect to an error page."),
   ]),
   ("S3.2", "Network-level error on the page itself", "'got error while scraping net::ERR_…' (not the [browser] sub-resource lines, which are background noise).", [
     ("S3.2a", "Connection reset / refused", "net::ERR_CONNECTION_RESET | ERR_CONNECTION_REFUSED at <url>",
      ["page_level_net_error_inline", "scrape_net_error_inline"], ["A1"], "Firewall dropping scanner traffic; allowlist the static IPs."),
     ("S3.2b", "Redirect loop", "net::ERR_TOO_MANY_REDIRECTS",
      ["page_level_net_error_inline", "scrape_net_error_inline"], ["A8"], "Customer-side redirect rule (often staging/auth gateways)."),
     ("S3.2c", "Host does not resolve", "failed due to DNS_ERROR_COULD_NOT_FIND_URL",
      ["final_type_misc", "page_failed_due_to_reason"], ["C4"], "Internal or mistyped host in the seed list."),
   ]),
   ("S3.3", "Pages never finished loading", "'all attempts to scrape url had failed' with type OPEN_PAGE_TIMEOUT (one line per failed URL).", [
     ("S3.3a", "Almost every URL of the host times out", "OPEN_PAGE_TIMEOUT on most URLs of one job",
      ["scrape_final_failure_by_type", "open_page_timeout", "page_failed_due_to_reason"], ["A1", "A5", "A2"],
      "Behaves like a tarpit/block: treat as S3.1a — check static IP and allowlisting."),
     ("S3.3b", "A few heavy URLs time out", "OPEN_PAGE_TIMEOUT or gotoURL > 40000/60000 ms on a handful of URLs",
      ["open_page_timeout", "goto_url_timeout"], ["D1"], "Exclude those URLs or raise timeouts. gotoURL lines are per attempt (~2.8/URL) — don't count them as failures."),
   ]),
   ("S3.4", "The browser landed somewhere unexpected", "'final url after redirections' or the interaction error url is another country/site page.", [
     ("S3.4a", "Geo redirect", "final url / error.url contains out-of-country (or a different country site)",
      ["interaction_landed_on_login_or_geo", "final_url_login_or_error_landing"], ["A7"], "Geo-blocking of US egress; customer must allowlist."),
   ]),
 ]),
 ("S4", "The scanner could not log in or stay logged in", "The property has a login; failures show in the page-interaction plugin.", [
   ("S4.1", "A login element was not found", "'No element found for selector: <sel>' with the url the browser was on.", [
     ("S4.1a", "Selector missing on the expected login page", "No element found for selector … + error.url = the login page; PAGE_INTERACTION_PLUGIN_ERROR",
      ["interaction_selector_not_found", "interaction_selector_missing"], ["B2"],
      "First check the same job for 403/405 (S3.1a) — a blocked login page also 'loses' the selector. Otherwise update the selector."),
     ("S4.1b", "Selector missing because the browser is on an MFA page", "No element found … + error.url / final url matches mfa|otp|challenge",
      ["interaction_selector_missing", "final_url_login_or_error_landing"], ["B1"], "MFA cannot be automated: test user without MFA or IP-based bypass."),
     ("S4.1c", "Invalid selector syntax", "'<sel>' is not a valid selector",
      ["interaction_selector_missing"], ["B2"], "Fix the selector syntax in the login config."),
   ]),
   ("S4.2", "The login step ran too long", "'bound handleRequest execution took more than 300000 ms'.", [
     ("S4.2a", "Multi-step login hit the hard cap", "Function: bound handleRequest execution took more than 300000 milliseconds",
      ["handle_request_hard_cap"], ["B4", "D1"], "Needs a backend Multiple Interactions script, or longer waits per step."),
   ]),
   ("S4.3", "Still on, or back on, the login page", "Judge per request and per pod (browser session), not per job: the login step itself logs the login URL as its final URL.", [
     ("S4.3a", "Login 'succeeded' but the browser never left the login route", "all steps + 'finished interacting with page successfully', then final URL still the login route on every request",
      ["final_url_login_or_error_landing", "interaction_steps"], ["B3"], "Wrong/expired password or lockout. Rule out a 403 on first load (A1) and an MFA screen on the same route (B1)."),
     ("S4.3b", "One browser session drops mid-crawl", "one pod logs in OK, then its later requests keep landing on the login URL while other pods succeed",
      ["final_url_login_or_error_landing", "interaction_landed_on_login_or_geo"], ["B5"], "Session lost: parallelism=1, exclude logout/session-check URLs, stagger schedules. Per-URL bounces in every pod = gated pages (C4)."),
   ]),
 ]),
 ("S5", "The crawl kept the wrong set of URLs", "Pages loaded fine, but the crawl ended with too few, too many, or the wrong URLs.", [
   ("S5.1", "URLs were rejected by the scope rules", "'not including url in result url set. reason: …' — most reasons are normal bookkeeping.", [
     ("S5.1a", "Seed rejected: final URL outside the whitelist", "reason: final url not included in whitelist — on the seed or on every URL of the job",
      ["not_included_whitelist"], ["C2", "C1"], "Seed redirects to another host/path: add it to the whitelist or use the final URL as seed."),
     ("S5.1b", "Every URL rejected by the language filter", "reason: language is not included in whitelist — on every URL",
      ["not_included_other_reasons"], ["C1"], "Locale filter doesn't match the site's language tags."),
     ("S5.1c", "Content type rejected (case bug)", "content type text/HTML; charset=utf-8 is not allowed",
      ["not_included_other_reasons"], ["C4"], "Likely a case-sensitivity bug in the content-type check — escalate."),
   ]),
   ("S5.2", "The crawl ended almost empty", "Use the end-of-job summary 'successfully visited: N urls' (or METRIC_EVENT CrawlSummary totalUrlsCount) — the progress counter is never printed for 0-page crawls.", [
     ("S5.2a", "Seed loaded, nothing followed, nothing filtered", "successfully visited: ≤1 urls, filtered out: 0 urls, seed 200, final URL = seed, no errors",
      ["crawl_visited_counter", "filtered_out_links"], ["C6", "A2", "A3"],
      "Either the page has no real links (JS navigation → List mode) or it is a challenge/block page served as 200."),
     ("S5.2b", "Seed blocked or rejected", "successfully visited: ≤1 urls plus a non-200 seed status (S3.1a) or the seed rejected by the whitelist (S5.1a)",
      ["crawl_visited_counter"], ["A1", "C2"], "Follow the branch the companion lines point to."),
   ]),
   ("S5.3", "The crawl hit a configured cap", "'matching grouping … is full' / 'max number of successful visits was reached' — background, by design.", [
     ("S5.3a", "Page or grouping cap reached", "not handling request … reason: max number of successful visits was reached | matching grouping … is full",
      ["benign_crawl_cap_grouping_full"], ["C5", "C3"], "Explains 'fewer pages than expected': raise maxPagesCount or loosen grouping rules."),
   ]),
   ("S5.4", "The property configuration itself is the clue", "The crawler logs its full config once per job ('crawler config is: {…}').", [
     ("S5.4a", "Old user agent / no custom header / wrong scope", "config is: { … --user-agent=…Chrome/65 … extraHeaders: null … whitelist … }",
      ["config_dump_user_agent"], ["A6", "A1", "C1", "C2"],
      "Context, not an error. Contains credentials — read only the fields you need, never paste it into a ticket."),
   ]),
 ]),
 ("S6", "Pages loaded but the analysis failed", "The page opened, but the accessibility engines or plugins errored.", [
   ("S6.1", "The engine crashed on the page", "'failed due to FAILED_TO_RUN_ENGINES' with a stack trace.", [
     ("S6.1a", "Engine error on specific DOMs", "{\"type\":\"FAILED_TO_RUN_ENGINES\", … stackTrace …}",
      ["engine_crash_failed_to_run_engines"], ["D2"], "Exclude the page as a workaround; open an engine bug with the URL and stack trace."),
   ]),
   ("S6.2", "A plugin step hung", "PLUGIN_TIMEOUT / 'bound run execution took more than'.", [
     ("S6.2a", "Plugin timeout on heavy pages", "failed due to PLUGIN_TIMEOUT | Function: bound run execution took more than N ms",
      ["plugin_run_timeout", "final_type_misc"], ["D1", "D2"], "Heavy page; same handling as S3.3b."),
   ]),
   ("S6.3", "The page changed while being analysed", "'Execution context was destroyed' / 'frame was detached'.", [
     ("S6.3a", "Navigation during analysis", "Execution context was destroyed, most likely because of a navigation",
      ["nav_instability_context_destroyed"], ["D3"], "Pop-ups or late redirects; findings may vary between runs."),
   ]),
 ]),
 ("S7", "Problems after the scan", "The scan finished, but results, exports, emails or the UI fail.", [
   ("S7.1", "The UI is slow or errors ('Error loading scan')", "Controller calls logged with durations; failures with the request URI.", [
     ("S7.1a", "Slow API call", "invocation of function (<Controller>.<method>) took N millis (WARNING > ~10 s)",
      ["api_slow_controller_call"], ["E5"], "Heavy View / huge property; simplify the View."),
     ("S7.1b", "API call failed", "invocation of function (…) failed (<Exception>: …) — NotFound (deleted scan/view), NPE, 5xx",
      ["api_controller_failed"], ["E5", "F3"], "NotFound = deleted object or stale link; other exceptions = product bug."),
   ]),
   ("S7.2", "Export or email not delivered", "Export poller and email sender log their failures.", [
     ("S7.2a", "Export generation failed", "failed to generate CSV|XLSX for scan … (poller timeout | poll request failed) / publish to queue …-csv failed",
      ["export_generation_failed", "csv_queue_publish_failed"], ["F1"], "Scan deleted or queue down; note the onFailed() bug hides the failure from the user."),
     ("S7.2b", "Completion email failed", "Failed to send (crawl|scan) completion email for …",
      ["completion_email_failed"], ["F1"], "Property deleted or SendGrid unavailable."),
   ]),
   ("S7.3", "Integration or MCP errors", "Only MCP leaves a trace in these services.", [
     ("S7.3a", "MCP caller rejected", "An invalid request caller ID was received: MCP",
      ["mcp_invalid_caller_id"], ["F4"], "Jira/ADO calls are not logged here at all."),
   ]),
 ]),
 ("S8", "No trace in the logs", "These problems are real but leave no distinctive log line today; diagnose them another way.", [
   ("S8.1", "Looks normal in the logs", "Status 200, no errors — the problem is in the page content or the UI.", [
     ("S8.1a", "Soft block (block page with 200)", "nothing: page title / DOM size are not logged",
      [], ["A3"], "Look at the scan's screenshots / issue spike on landmark & H1 rules."),
     ("S8.1b", "Static IP on, but the customer allowlisted other IPs", "nothing: the egress IP is not logged (useStaticIp=false IS visible — see S3.1a)",
      [], ["A4"], "Send the customer the NAT IP list and compare."),
     ("S8.1c", "TLS certificate error", "nothing: the browser ignores certificate errors",
      [], ["A9"], "Open the site in a browser and check the certificate."),
     ("S8.1d", "Grouping merges or splits pages", "nothing beyond page counts",
      [], ["C5"], "Review grouping rules against the URL list."),
     ("S8.1e", "UI, export semantics, findings, account questions", "nothing in server logs",
      [], ["F2", "F3", "G1", "G2", "G3", "G4", "H1", "H2", "H3", "H4"], "Handle from the product and the ticket text."),
   ]),
 ]),
]

def load():
    sigs = {}
    for f in ("page_level", "access_auth", "lifecycle_platform"):
        for s in json.load(open(f"{R}/data/logs/{f}.json")):
            s["file"] = f; sigs[s["sig_id"]] = s
    val = {}
    p = f"{R}/data/logs/validated.json"
    if os.path.exists(p):
        for v in json.load(open(p)): val[v["sig_id"]] = v
    bt = json.load(open(f"{R}/data/logs/backtest.json"))
    return sigs, val, bt

if __name__ == "__main__":
    sigs, val, bt = load()
    missing = sorted({s for _, _, _, l2 in TREE for _, _, _, l3 in l2 for *_, ss, _, _ in l3 for s in ss} - set(sigs))
    assert not missing, missing
    out = []
    for sid, title, desc, l2 in TREE:
        out.append({"id": sid, "title": title, "desc": desc, "children": [
            {"id": i2, "title": t2, "desc": d2, "children": [
                {"id": i3, "title": t3, "pattern": pat, "sigs": ss, "subs": subs, "next": nxt,
                 "validated": [val.get(s, {}).get("status", "not_run") for s in ss]}
                for i3, t3, pat, ss, subs, nxt in l3]}
            for i2, t2, d2, l3 in l2]})
    used = {s for n in out for c in n["children"] for l in c["children"] for s in l["sigs"]}
    json.dump({"tree": out, "signatures": list(sigs.values()), "validated": list(val.values()), "backtest": bt,
               "unused_sigs": sorted(set(sigs) - used)}, open(f"{R}/data/logtree.json", "w"), indent=1)
    leaves = [l for n in out for c in n["children"] for l in c["children"]]
    print("L1", len(out), "L2", sum(len(n["children"]) for n in out), "L3", len(leaves), "sigs used", len(used), "of", len(sigs))
    print("unused:", sorted(set(sigs) - used))

# Primary log leaf per sub-issue: where a ticket of this sub-issue SHOWS UP in the logs
# (the symptom location, not the root cause). Used for the ticket heatmap.
PRIMARY = {
 "A1": "S3.1a", "A2": "S3.1a", "A3": "S8.1a", "A4": "S3.1a", "A5": "S3.1b", "A6": "S3.1a", "A7": "S3.4a", "A8": "S3.2b", "A9": "S8.1c",
 "B1": "S4.1b", "B2": "S4.1a", "B3": "S4.3a", "B4": "S4.2a", "B5": "S4.3b",
 "C1": "S5.1a", "C2": "S5.1a", "C3": "S5.3a", "C4": "S3.1e", "C5": "S8.1d", "C6": "S5.2a", "C7": "S1.1b",
 "D1": "S3.3b", "D2": "S6.1a", "D3": "S6.3a",
 "E1": "S2.1a", "E2": "S1.2a", "E3": "S2.2b", "E4": "S1.1a", "E5": "S7.1a",
 "F1": "S7.2a", "F2": "S8.1e", "F3": "S8.1e", "F4": "S8.1e",
 "G1": "S8.1e", "G2": "S8.1e", "G3": "S8.1e", "G4": "S8.1e",
 "H1": "S8.1e", "H2": "S8.1e", "H3": "S8.1e", "H4": "S8.1e", "H5": "S8.1e",
}
