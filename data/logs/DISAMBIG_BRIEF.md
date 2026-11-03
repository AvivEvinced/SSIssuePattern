# Brief: can combinations of logs / the temporal flow inside one job pinpoint ambiguous sub-issues?

Read first: data/logs/LOGBRIEF.md (syntax + v2 working rules: write incrementally, ~30 query budget, halve window on timeout),
the SUB dict in scripts/taxonomy.py (sub-issue definitions), and the existing findings: data/logs/access_auth.md,
data/logs/page_level.md, data/logs/lifecycle_platform.md, data/logs/backtest.md, data/logs/validated.json (working queries).

Verified gotchas: `~ 'a|b'` is a LITERAL substring (use separate ~ with || or .matches(/re/)); HTTP status lines
"http status code is: N" are INFO; production filter for workers: $d.resource.attributes.environment == 'production';
one job = $d.resource.attributes['k8s.job.name'] (crawl/scan id); per-request id $d.context.request_id; page URL $d.context.url
(older logs: $d.url); error detail in $d.error.message (JSON string); template ids change per release — match message text.
admin/front: $d.context.property_id / scan_id are LAST 12 hex chars; $d.logger_name; $d.error.{type,message}.

Method: (1) find real production jobs that show the ambiguous signal (e.g. a job where most visits are 403); include the
back-test tickets where a known answer exists (see backtest.md). (2) For a handful of jobs reconstruct the ordered timeline
(choose $m.timestamp, message, url, status — limit ~60 rows, ordered) and compare the SEQUENCE and RATIOS between sub-issues:
e.g. does the block start at request 1 or after N successes? does a 202 precede 200s? which interaction step ran last before the
error, and what URL was the browser on? did the final URL after login equal the login URL? does the failure repeat for the same
URLs across runs? (3) Turn what separates them into a decision rule (ordered checks, each with a working DataPrime query) and
state how confident it is and on how many jobs it was checked. (4) Note every event you expected to find in logs but could not
(a "logging gap") — with what it should contain; these go to the backend team.

Output: data/logs/disambig_<group>.md and data/logs/disambig_<group>.json:
{ "group": "...", "subs": [...], "rules": [ {"step":1,"check":"plain words","query":"...","outcome_if_true":"→ A5","evidence":"n jobs / examples","confidence":"high|medium|low"} ],
  "still_ambiguous": [ {"subs":["A1","A4"],"why":"..."} ], "logging_gaps": [ {"missing_event":"...","needed_for":["A4"],"suggested_fields":"...","where":"service"} ],
  "examples": [ {"job":"...","host":"...","true_or_likely_sub":"...","timeline_summary":"..."} ] }
Never copy credentials, tokens, cookies, passwords or emails (the 'crawler config is:' dump contains credentials — read only the fields you need).
Final reply < 400 words.
