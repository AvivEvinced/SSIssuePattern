# Brief for per-batch ticket analysis

Context: Evinced "Site Scanner" (crawls a customer "property" = set of seed URLs/regex/login config, then scans pages for a11y issues).
Ground-truth top-level classes (from the GT sheet):
 1 = Scan/crawl failure (not 0 pages)   2 = 0 pages   3 = Successful scan with failed pages
 4 = Crawl irregularities (page count low/inconsistent/wrong URLs)   5 = Other (UI, exports, config questions, FPs, access, etc.)
Goal: split each class into SUB-ISSUES by the underlying MECHANISM (root cause) and/or SOLUTION, so that later we can
build Coralogix log patterns that detect each sub-issue, and an agent ("the investigator") can suggest the fix.

Tools: `cd /home/user/SSIssuePattern && python3 scripts/dump_ticket.py <id> [maxchars]` prints one ticket's thread
(INTERNAL notes are support-engineer notes and often contain log lines from admin-server/crawler, Jira keys, Slack links,
root-cause discussions — read them carefully). Raw JSON is in data/zendesk/<id>.json if you need the full text.
Read EVERY ticket in your batch. Do not read other batches.

SECURITY: threads contain passwords/tokens/customer credentials. NEVER copy credentials, passwords, auth headers,
cookies, tokens or personal emails/phones into your output.

Output: write a JSON array to data/analysis/<batch>.json, one object per ticket:
{
 "ticket": "#1234", "gt_class": "1", "client": "...",
 "summary": "1-2 sentence what the customer saw",
 "sub_issue": "short snake_case label for the mechanism, e.g. bot_protection_cloudflare_403, login_flow_failed, robots_txt_disallow, regex_excludes_all, scan_stuck_infra, scheduler_missed_run, ...",
 "mechanism": "root cause as established in the thread (say 'unknown' if never established)",
 "resolution": "what fixed it / what support did (config change, IP whitelist, custom header, bug fix + Jira key, workaround, no fix)",
 "resolution_type": "one of: customer_config_change | evinced_config_change | customer_side_whitelist | product_bug_fix | infra_fix | workaround | explanation_only | feature_request | unresolved",
 "log_signals": ["verbatim or near-verbatim log/error strings, state transitions, HTTP codes, service names, logger class names (e.g. ScanService.kt), field names like scanId/propertyId — anything usable as a Coralogix query; [] if none"],
 "ui_signals": ["error text the customer saw in UI/email, e.g. 'Error loading scan', 'no URL to scan'"],
 "jira": ["EW-1234", ...],
 "detectable_in_logs": "yes | maybe | no  (could a log pattern plausibly detect this?)",
 "gt_class_doubt": "empty, or a short note if the thread suggests the GT class is wrong (e.g. ticket isn't site-scanner, or is really class 2 not 1)"
}
Then, at the end of your final reply (not the file), give: (a) the list of distinct sub_issue labels you used with counts and a one-line
definition each, (b) the most useful recurring log signatures you saw. Keep the final reply under 600 words.
Reuse labels consistently; prefer mechanism-level labels over symptom labels.
