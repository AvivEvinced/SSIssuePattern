> Snapshot of the Claude doc https://claude.ai/artifact/3eQfy5rzzGRE975bQdD3nD, exported 2026-11-03. Charts and diagrams live in the online doc.

# Site Scanner Alert Verification

Nov 3, 2026 · @Aviv Ziv

## Purpose and how to verify

These 50 production runs from 2026-10-04 to 11-03 each triggered one of four candidate alert patterns, and none has a support ticket. Your verdict on each tells us whether an alert on that pattern would surface real problems customers haven't reported, or mostly noise.

Patterns and sample size:

| Pattern | What it flags | Examples |
| --- | --- | --- |
| A1/A2 Blocked by bot protection | Most pages of the run got 403/405, or a 202 challenge | 15 |
| A4 Static IP off and blocked | The run left from non-static IPs and was blocked | 10 |
| B2 Interaction selector failure | A login or page-interaction step could not find its element | 15 |
| B4 Multi-step login stops | The username step ran, the next identity-provider step failed | 10 |

For each example:

1. Open the **run** link (the crawl's URL set or the scan's URL status page) and the **property** link. Check what the customer sees: page count, failed pages, status codes, the screenshots of a few pages.
2. If needed, open the **settings** link: static IP, login configuration, include/exclude rules.
3. Optional: run the Coralogix query in the row's notes to see the log lines.
4. Set the **Verdict**: *Real issue* (the customer is affected and a fix exists or should be offered), *Harmless* (expected or irrelevant, e.g. a test property or a page that should be excluded), or *Unsure*. Add a line in **SE notes** on why, and on whether the suggested fix is right.

One example per property, chosen across tenants and dates. Each was checked against the ground-truth sheet and a Zendesk search on the site and property name. Log excerpts never include credentials.
