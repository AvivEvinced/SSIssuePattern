> Snapshot of the Claude doc https://claude.ai/artifact/FaxdnReL9zcz6cBeHjkm92, exported 2026-11-03. Charts and diagrams live in the online doc.

# Site Scanner Pattern Statistics

Nov 3, 2026 · @Aviv Ziv

Half of the 279 GT tickets are crawl, scan or platform incidents. Tested in the logs, the pattern named the right sub-issue for 15 of 37 testable tickets (41%) and at least the family for 24 (65%). In 30 days the patterns fired on about 680 production job-events, and only 4 of those became GT tickets.

## Method

- **Tickets:** 279 tickets from the “Site Scanner Ticket Classification” sheet, labelled from their full Zendesk threads into 8 families and 42 sub-issues (see the companion doc, Site Scanner Issue Patterns).
- **Detected vs missed:** each ticket created June–October 2026 whose sub-issue has a log pattern (49 tickets) was looked up in Coralogix around its failing run. *Detected* = the pattern fires and names the ticket's sub-issue. *Family only* = it fires but only narrows to the family or a look-alike group. *Missed* = the run was found and the pattern does not fire. *Not testable* = the run was not found, or the ticket has no log-side symptom.
- **Events without a ticket:** each pattern's rule run over all production jobs from 2026-09-27 to 10-27; an event is one matching crawl or scan job (other units are labelled). Tickets in that window: 10, of which 5 technical.
- **Limits:** logs before June 2026 are too thin to test; admin/front instrumentation was thinner in June–July; worker logs carry no tenant; the second annotator and the log searches were done by AI agents.

## 1. How common each issue is

Half of the 279 GT tickets (139) are crawl, scan or platform incidents (families A–E); the rest are UI, findings and account topics. Among incidents, three sub-issues carry 40 tickets: multi-step login needing configuration (B4, 15), WAF blocks (A1, 13) and platform outages (E1, 12).

[Chart: 279 tickets from the Site Scanner Ticket Classification sheet, Nov 2024 – Oct 2026 — see the online doc]

Counts are tickets customers raised over two years, not how often each problem happens in production; section 3 measures that from the logs.

## 2. Detected vs missed tickets

Of the 37 tickets that could be tested, the pattern named the right sub-issue for 15 (41%), named only the family for 9 (24%) and missed 13 (35%). Testable means the failing run was found in the logs; 12 of the 49 candidates were not testable (run not found, or a question with no log-side symptom). Tickets before June 2026 and sub-issues graded invisible were not tested.

[Chart: 49 GT tickets created Jun–Oct 2026, each looked up in Coralogix around its failing run — see the online doc]

The strongest patterns are WAF blocks (A1: 5 of 6 testable) and platform outages (E1: 5 of 6). Access look-alikes (A2, A6, A7) and login look-alikes (B4, B5) are found only at the family level, because no log line marks the specific cause.

| Ticket | Sub-issue | Outcome | What the logs showed |
| --- | --- | --- | --- |
| #2851 | A1 | missed | Internal site: DNS and go-to-URL errors, no 403, so the rules read C4 |
| #3083 | A4 | missed | Non-static node pool found, but Akamai served its block page with 200 |
| #2946 | B1 | missed | Run shows an identifier-first login failure (B4 shape), no MFA landing |
| #3241 | B1 | missed | Only public pages crawled; the MFA wall is not in the logs |
| #3198 | B2 | missed | Back-test found only a generic timeout (a later re-check found the selector error on another job) |
| #2889 | C3 | missed | No exclude-list surge; scope issue not visible (run match uncertain) |
| #2895 | C3 | missed | Pre-redirect page logged as 200; visible only if you know the expected URL |
| #2915 | C5 | missed | No fragment rejects; the missing parameter pages leave no trace |
| #3000 | D3 | missed | Hydration and script errors, but render state is not logged |
| #2979 | E1 | missed | UI-only outage; worker and API volumes stayed flat |
| #3315 | E3 | missed | Logs show an engine package failure on every page (D2-like), not a dispatch failure |
| #2901 | E5 | missed | July front-server had no 5xx or function-failure lines yet |
| #2780 | F1 | missed | June–July admin/front had no export-failure lines yet |
| #3420, #2450 | A2 | family | 403 and 1 page; no challenge marker, so A1 and A2 look the same |
| #2812 | A7 | family | Seed 403, no geo redirect logged: reads as A1 |
| #3340 | A6 | family | Seed blocked; the user agent actually sent is not logged |
| #2783 | C2 | family | Rejected hosts were inside allowed domains, so the rule says C1 |
| #2794 | B5 | family | Login wall visible, but one browser per job, so no sibling to compare |
| #2959, #3238 | B4 | family | Selector failures on the identity provider; B2 and B4 look the same |
| #3136 | F4 | family | MCP caller-ID rejections visible; Jira/ADO not logged |

## 3. Pattern events with no ticket

In 30 days (2026-09-27 to 10-27) the job-level patterns fired on 681 job-events across about 3,674 production jobs (1,299 crawls, 2,375 scans); only 4 match a GT ticket. Where a ticket exists, each ticket stands for 22 to 56 events of its pattern: WAF blocks 40 jobs on 21 sites for one ticket (#3369), static IP off 22 jobs for one (#3425), old user agent 50 for one (#3340), failed-every-page scans 56 for one (#3315).

**677 of the 681 job-events (99.4%) are not in any ticket.** The 4 with a ticket are one job each for A1, A4, A6 and the E3 variant; every other pattern had no ticket in the window. Counted in their own units, none of the other patterns' events were in a ticket either: 185 E3 property-days, 34 E4 properties, 15 C7 properties, 99 F1 scans and 482 E5 slow-call groups.

| Sub-issue | Events | In a ticket | Not in a ticket |
| --- | --- | --- | --- |
| E3 every page of a scan failed | 56 | 1 (#3315) | 55 |
| A6 blocked job with old user agent | 50 | 1 (#3340) | 49 |
| A1 WAF / firewall hard block | 40 | 1 (#3369) | 39 |
| A4 static IP off, blocked | 22 | 1 (#3425) | 21 |
| 15 other job-level patterns | 513 | 0 | 513 |
| **All job-level patterns** | **681** | **4** | **677** |

A job can match more than one pattern, so the number of distinct jobs not in a ticket is lower than 677; it was not de-duplicated.

[Chart: Coralogix, production site-scanner jobs, 2026-09-27 to 2026-10-27 — see the online doc]

Patterns counted in other units:

| Sub-issue | Unit | Events | Spread | Tickets in window |
| --- | --- | --- | --- | --- |
| E3 dispatch pair | property-days | 185 | 153 properties, 19 tenants | 0 |
| E4 licence / limit refused | properties | 34 | 11 tenants (most already failing before the window) | 0 |
| C7 no URLs / cap set to 1 | properties | 15 | 10 tenants (mostly standing config) | 0 |
| F1 export failed | scans | 99 | not measured | 0 |
| E5 slow API call | slow-call groups | 482 | 29 tenants (not joined to a 5xx) | 0 |
| E1 outage / E2 stuck schedule | incident-hours / properties | 0 / 0 | only the harmless scheduler race | 0 |

How to read the ratios:

- Many events are expected and harmless for the customer (a site's own 404s, a cap working as configured), so events per ticket is not a false-alarm rate. It shows how much an alert on each pattern would surface that nobody reported.
- Several counts are upper bounds because one check of the rule was not run: D1 (same URLs every run), E5 (join to a 5xx), B4 (step sequence), C4 and A8 (seed only), C2 (about 14 jobs redirect to a login provider, so they belong to B).
- \#3420 (A2) was caught by the A1 rule, not A2: a Cloudflare challenge returns 403.
- A6 is weak as a rule: jobs with old and current user agents are blocked at the same rate (about 20%).
- Worker logs carry no tenant, so job-level patterns count sites, not customers. A1, A2 and A5 use crawl-worker statuses only.
