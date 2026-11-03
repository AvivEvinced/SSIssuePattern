"""Hand-graded log detectability per root-cause sub-issue, after the disambiguation research
(data/logs/disambig_*.md|json). Writes data/detectability.json.

grade:
  detect      – a log signal identifies the sub-issue on its own (single pattern or one simple ratio)
  rule        – visible but shared with look-alikes; a combination / temporal rule separates it (rule refs below)
  partial     – a rule narrows it to 2–3 candidates; residual ambiguity remains
  invisible   – nothing in today's logs distinguishes it
"""
import json, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

D = {
 # ---- detect directly
 "E2": ("detect", "Duplicate JobEntity key with a past run time repeating every ~7.5 min; next-run line vs UI.", "", "Time zone missing from next-run line (timezone variant invisible)."),
 "E4": ("detect", "failed to create entity … + LimitExceededException ('license has expired' / limit).", "", ""),
 "F1": ("detect", "failed to generate CSV|XLSX … (poller timeout / poll request failed); publish to …-csv failed; completion email failed.", "", "Row-limit (10k) rejection not logged."),
 "A7": ("detect", "Interaction error url or seed final URL on out-of-country / unavailable page.", "", ""),
 "A8": ("detect", "net::ERR_TOO_MANY_REDIRECTS on the page.", "", ""),
 "C4": ("detect", "DNS_ERROR_COULD_NOT_FIND_URL on seed; high 404 share; final url …/404|/500.", "", ""),
 "D2": ("detect", "failed due to FAILED_TO_RUN_ENGINES with stack trace (page URL).", "", "Worker-side ENGINES_PLUGIN_ERROR (ENOENT) must be split off as Evinced-side."),
 "E3": ("detect", "Pair 'Failing URL set … due to job timeout/failure' + 'Failed running create crawl request' for one property after a scheduler tick; k8s BackoffLimitExceeded.", "", "Underlying cause of 'job timeout/failure' not logged."),
 # ---- separable with a combination / temporal rule
 "A5": ("rule", "Per-job status histogram: 429 share ≥ 10% (front-loaded & decaying = throttle; sustained = hard limit).", "access R3", "Rate-based WAF rules that answer 403 in waves look like A1."),
 "A2": ("partial", "Per-job histogram: 202 share ≥ 30% from the first minute (bot-manager interstitial).", "access R2; discovery R1", "Cloudflare challenge returns 403 → identical to A1 (#3420)."),
 "A1": ("rule", "403/405 share ≥ 50%; onset at request 1–3 (deny list) vs after N 200s never recovering (reputation trip); OPEN_PAGE_TIMEOUT share ≥ 80% at a flat plateau (tarpit).", "access R4, R6", "vs A2-Cloudflare, vs A4 when the flag is on but wrong IPs allowlisted."),
 "A4": ("rule", "admin-server request body useStaticIp=false for the job (id = k8s job name) or job on a non '*-pool-stat*' node pool, combined with a block.", "access R1", "Flag on but customer allowlisted other IPs: egress IP not logged."),
 "A6": ("partial", "Blocked job whose config dump user agent is Chrome/65 or HeadlessChrome.", "access R5", "An old UA does not change the block's shape; confirmed only by a re-run with a current UA."),
 "D1": ("rule", "OPEN_PAGE_TIMEOUT share ≤ 10%, 200s continue to the end, the same URLs fail in every run.", "access R7", "Shares between 10% and 80% stay ambiguous with A1/A5."),
 "B2": ("rule", "Interaction error 'No element found for selector: X' with error.url = login page, AND no 403/405 resource error on the login request; 'is not a valid selector' = malformed.", "login R1–R3", "exists:true is unreliable; vs B4 on identifier-first IdPs."),
 "B3": ("rule", "All login steps run, 'finished interacting with page successfully', but the browser is still on the login route ~20 s later on every request.", "login R5", "SPA MFA screens sharing the login route look the same (B1)."),
 "B5": ("rule", "Per pod (browser session): first request logs in OK, later requests of the same pod keep landing on the login URL while other pods succeed.", "login R7", "With one pod there is no sibling to compare; per-URL bounces = gated pages (C4)."),
 "B1": ("partial", "Request that clicked submit ends on a path with mfa|otp|2fa|verify|challenge (path only, not query string).", "login R6", "Rule defined but no live case found in 7 days; SPA MFA on the same route is invisible."),
 "B4": ("partial", "Partial step sequence: username typed, then the Continue/next step fails on the identity provider.", "login R4", "Cannot separate 'element missing' from 'element not yet rendered' (needs DOM/screenshot); 300000 ms cap is not specific."),
 "C2": ("rule", "Seed final URL rejected as 'final url not included in whitelist' AND its host is NOT in the job's 'allowed domains: {…}' line.", "discovery R4", ""),
 "C1": ("rule", "Same rejection text but the host IS in 'allowed domains' (regex/path rejected); or 'language is not included in whitelist' on every URL.", "discovery R5", "The include regex itself is not logged in a safe line."),
 "C3": ("rule", "Huge crawl with > 90% of fetched URLs rejected by the exclude list after fetching; page cap 'max visits reached'.", "discovery R6, R9", ""),
 "C7": ("rule", "failed to create entity … 'No URLs were supplied' / 'URL set not defined'; 'max visits reached' with visited = 1 (cap set to 1).", "discovery R6", ""),
 "E1": ("rule", "Distinct tenants with FAILED / dispatch failures per hour ≥ ~5, or a collapse in worker log volume.", "discovery R10", "Threshold calibrated on one quiet week and one outage."),
 "E5": ("rule", "front-server 5xx with request_uri joined by operation_id to 'invocation of function … took > 10 s' or NotFound (deleted scan).", "discovery R12", "502/504 returned by the gateway is not logged."),
 "F3": ("partial", "Same join as E5 but with a product exception (NullPointerException etc.).", "discovery R12", "Pure front-end bugs and UI confusion never reach the server."),
 "C5": ("partial", "Only rejects are 'sanitized url was already visited' on #fragment URLs (SPA routes collapsed).", "discovery R7", "Other grouping problems leave only page counts."),
 "D3": ("partial", "'Execution context was destroyed' on the page (navigation during analysis).", "", "Most D3 tickets are findings that vary with render timing — not logged."),
 "F4": ("partial", "MCP: 'invalid request caller ID: MCP'.", "", "Jira / Azure DevOps calls are not logged in these services."),
 # ---- invisible
 "A3": ("invisible", "", "discovery R8", "Block page served with 200: no title, body size or link count logged — identical to C6."),
 "C6": ("invisible", "", "discovery R8", "Seed 200, no links followed, nothing filtered — identical to A3 / A2-with-200."),
 "A9": ("invisible", "", "", "Browser ignores certificate errors; nothing logged."),
 "F2": ("invisible", "", "", "Export semantics, not a failure."),
 "G1": ("invisible", "", "", "Findings accuracy is in scan results, not logs."), "G2": ("invisible", "", "", "Same as G1."),
 "G3": ("invisible", "", "", "Score/severity config; engine version change is the only hint."), "G4": ("invisible", "", "", "Request, not a failure."),
 "H1": ("invisible", "", "", "Account/permission requests (licence expiry is E4)."), "H2": ("invisible", "", "", "Questions."),
 "H3": ("invisible", "", "", "Admin tasks."), "H4": ("invisible", "", "", "Feature requests / how-to."), "H5": ("invisible", "", "", "Noise / out of scope."),
}

if __name__ == "__main__":
    tax = json.load(open(f"{R}/data/taxonomy.json"))
    subs = {s["id"]: s for f in tax["families"] for s in f["subs"]}
    assert set(D) == set(subs), set(subs) ^ set(D)
    out = [{"id": k, "name": subs[k]["name"], "tickets": subs[k]["count"], "grade": g, "signal": sig, "rules": rules, "residual": res}
           for k, (g, sig, rules, res) in D.items()]
    json.dump(out, open(f"{R}/data/detectability.json", "w"), indent=1)
    import collections
    c = collections.Counter(o["grade"] for o in out); t = collections.Counter()
    for o in out: t[o["grade"]] += o["tickets"]
    print(dict(c), dict(t))
