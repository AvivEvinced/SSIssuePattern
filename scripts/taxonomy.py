"""Canonical Site Scanner issue taxonomy.

Level 1 = Issue family (root-cause domain), Level 2 = Sub-issue (mechanism + fix path).
RAW maps the per-ticket labels produced in data/analysis/c*.json to a sub-issue id.
Run: python3 scripts/taxonomy.py  -> writes data/taxonomy.json and data/ticket_labels.csv
"""
import csv, glob, json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# id: (family, name, definition, typical fix, log/UI signature, detectability)
SUB = {
 # ---------------- A. ACCESS: the site blocks or can't be reached by the scanner
 "A1": ("A", "WAF / firewall hard block", "Customer WAF or firewall (Cloudflare, Akamai, DataDome, PerimeterX, IP deny) rejects scanner requests with 403/405 or an 'Access denied' page.",
        "Customer allowlists the 5 static NAT IPs (scan-pool-nat1..5) and/or Evinced adds an agreed custom header; enable static IP on the property.",
        "http status code is: 403|405 · [browser] Failed to load resource: ... status of 403 · OPEN_PAGE_TIMEOUT · 'Access denied'", "yes"),
 "A2": ("A", "Bot challenge page (Cloudflare / reCAPTCHA)", "An interstitial JS or CAPTCHA challenge is served, so the crawl finds ~1 page and the scan analyses the challenge page.",
        "Custom user agent via puppeteer-args (--user-agent=...), custom header or IP allowlist; reCAPTCHA v2 bypass token.",
        "1 discovered page · page title 'Just a moment...' / 'Sorry, you have been blocked' · reCAPTCHA iframe", "yes"),
 "A3": ("A", "Soft block (block page with HTTP 200)", "The WAF returns a block or error page with status 200 (or empty <html>), so the page is counted as successful and the block page itself is scanned.",
        "Same as A1, but it has to be detected from content: same title or small DOM across many pages, spike of landmark/H1 issues.",
        "No HTTP error · empty HTML / blank screenshot · 'Access Denied' / 'We can't load this page' in content", "maybe"),
 "A4": ("A", "Static egress IP not enabled", "Customer allowlisted the NAT IPs, but the property or tenant isn't using them (flag off, property override, or fast tier on Cloud Functions), so traffic comes from random GCP IPs.",
        "Support turns on scan.use-static-ip / url-set.use-static-ip (Retool); move off the fast tier.",
        "Crawler public IP not in scan-pool-nat1..5 · production_crawl_link_extractor (fast tier) · property override use-static-ip=false", "yes"),
 "A5": ("A", "Rate limiting (HTTP 429)", "The site rate-limits the crawler; failed pages yield no outbound links, so discovery stalls and page counts swing between runs.",
        "speed-tier.slow / lower concurrency; static IP + allowlist; don't schedule sibling properties at the same time.",
        "http status code is: 429 · ERR_HTTP2_SERVER_REFUSED_STREAM · high page-timeout ratio", "yes"),
 "A6": ("A", "Outdated browser user agent blocked", "Bot manager blocks old Chrome user agents (the scanner sent Chrome 65; Akamai requires 130+).",
        "Override the user agent / upgrade the browser in puppeteer-args.",
        "browser was opened successfully. version: Chrome/<old> · Akamai block", "yes"),
 "A7": ("A", "Geo-blocking", "Site blocks or redirects non-local IPs (US scanner egress), e.g. a geo redirect away from the login page.",
        "Customer allowlists the NAT IPs; region-specific egress not available.",
        "final url after redirections: <other-country page> · selector not found after redirect", "maybe"),
 "A8": ("A", "Redirect loop", "Site returns endless 302s to scanner IPs (staging/auth gateways).",
        "Customer-side fix or allowlist.", "Too many redirects · repeated 302 on seed", "yes"),
 "A9": ("A", "TLS / SSL certificate error", "Expired or invalid certificate on a host makes its pages fail.",
        "Customer renews the certificate (or Evinced ignores certificate errors for the property).", "net::ERR_CERT_* on page load", "yes"),
 # ---------------- B. AUTH: login & session
 "B1": ("B", "MFA / 2FA blocks login", "Login ends on an SMS/OTP/MFA challenge, which Site Scanner can't complete.",
        "Dedicated test user without MFA, IP-based MFA bypass, or use WFA/SDK instead.", "final URL after login matches /mfa|/otp|challenge · 0 pages", "yes"),
 "B2": ("B", "Login / interaction selector mismatch", "The stored login or interaction selectors don't match the page: the site changed, they were wrong from the start, IDs are generated per load, or a hashed CSS class changed.",
        "Update to stable selectors (name/aria/data-*); raise interaction timeoutSeconds.",
        "encountered error while running a function with timeout · No element found for selector: <sel> · cannot find User Name Selector", "yes"),
 "B3": ("B", "Stale / invalid credentials", "The crawler logs in with an expired password (including a product bug where edited credentials weren't copied from the scanner to the crawler); repeated failures can get the IP locked out.",
        "Customer updates the password; make sure crawler and scanner configs are in sync.", "wrong-password / login failed in crawler logs from the NAT IP · login alert in #sup-site_scanner-alerts", "yes"),
 "B4": ("B", "Multi-step / custom login flow needs configuration", "Two-step forms, modal logins, SSO hops, or expiring session URLs aren't handled by the simple login form; needs backend Multiple Interactions.",
        "Evinced configures scraper.user-interaction.configuration (multi-interaction script) on the backend.",
        "bound handleRequest execution took more than 300000 ms · login URL 404 · scraper.user-interaction.configuration", "maybe"),
 "B5": ("B", "Session lost mid-crawl", "The authenticated session drops while crawling: parallel workers, crawling logout or session-check URLs, or two properties logging in at once.",
        "parallelism=1; exclude logout/session URLs; stagger schedules.", "status of 401 (Unauthorized) · final url = /login|/guest after successful login", "yes"),
 # ---------------- C. SCOPE: property crawl configuration
 "C1": ("C", "Include regex matches nothing / invalid regex", "The include regex or locale filter matches none of the seed or discovered URLs, or the regex is malformed (unescaped slashes).",
        "Fix the regex (test against real seed URLs).", "0 URLs · not including url in result url set · regex parse error", "yes"),
 "C2": ("C", "Redirect target outside the domain whitelist", "The seed redirects (www/non-www, locale path, query string) to a final URL that the domain whitelist or include regex doesn't allow, so every page is dropped.",
        "Add the final domain/path to the whitelist, or use the post-redirect URL as seed.",
        "not including url in result url set. reason: final url not included in whitelist", "yes"),
 "C3": ("C", "Scope too broad / unexpected URLs", "Include domain or regex is too wide (or the site exposes rewrite paths), so out-of-scope or locale URLs are crawled and page counts inflate.",
        "Narrow the include regex / seed list; filter after the scan with a View.", "page count jump vs previous crawl · property PUT/urlsets POST change", "maybe"),
 "C4": ("C", "Seed unreachable / soft-404 / error-page redirect", "The seed returns 404, or listed URLs redirect to the site's 404/500 page, which then gets scanned.",
        "Use deeper or valid seed URLs; exclude error pages.", "Success Redirected to https://<host>/500 · seed 404", "yes"),
 "C5": ("C", "Grouping / URL-normalization rules", "Grouping merges distinct pages (fragment SPA routes, query params) or fails to merge duplicates (///, sort/filter params).",
        "Adjust grouping rules ('as different pages', untick 'ignoring URL fragments'); add param variants as seeds.", "page count far below expected with many fragment/param URLs", "no"),
 "C6": ("C", "Non-link (JS) navigation", "Navigation uses onclick / ng-click / javascript:void(0) with no href, so the crawler finds nothing to follow.",
        "Switch to List mode or give an explicit seed list.", "crawl ends with 1 discovered page and no auth/blocking errors", "maybe"),
 "C7": ("C", "List-mode misconfiguration", "List mode with a single URL, or the scan reusing a stale crawl list ('crawl before scan' off).",
        "Correct the mode / enable 'crawl before scan'.", "constant page count across runs", "maybe"),
 # ---------------- D. PAGE / ENGINE: rendering & analysis per page
 "D1": ("D", "Heavy page load timeout", "Heavy pages (maps, product grids, 5k complex pages) never reach the ready state within waitForPageReadySeconds/gotoURL limits.",
        "Exclude the URLs, raise timeouts, or reduce maxPagesCount; engine fixes.", "Function: gotoURL execution took more than 40000 ms · waitForPageReadySeconds", "yes"),
 "D2": ("D", "Analysis engine crash / limit", "The analysis engine fails on specific DOMs (AMP circular visibility, ~21k-element DOM).",
        "Engine fix; exclude the page as a workaround.", "FAILED_TO_RUN_ENGINES · CircularEvValueError · EvincedEnginesPlugin.ts runAnalysis", "yes"),
 "D3": ("D", "Incomplete render → findings variance", "The page is analysed before it stabilises (late JS, missing CSS, pop-up interstitial), producing spurious or flipping findings and scores.",
        "Longer wait or stabilisation, cookie to suppress the pop-up, re-scan.", "Target Size / contrast spikes between runs · blank screenshot", "maybe"),
 # ---------------- E. PLATFORM: Evinced backend / infra
 "E1": ("E", "Platform outage / infra incident", "Evinced-wide incident: scans and crawls hang or fail, or the UI can't load data.",
        "Infra fix, then rerun.", "Scan ... state changed from RUNNING to FAILED (many tenants at once) · passed its timeout, marking it as FAILED · kubernetes job failed", "yes"),
 "E2": ("E", "Scheduler bug (missed / wrong next run)", "Next-run computation is wrong (timezone/date bugs), so scheduled runs are skipped or shown on the wrong date.",
        "Product fix; manual rerun.", "JobScheduler ... next schedule job time is · nextScheduleJobTime mismatch · no crawl at the scheduled time", "yes"),
 "E3": ("E", "Pipeline dispatch / state-machine failure", "Crawl→scan hand-off fails: crawl POST refused (scrape-server DB pool exhausted), scan phase never triggered, RUNNING→FAILED bugs.",
        "Product/infra fix; retry the job.",
        "Failed running create crawl request · Connection refused · HikariPool-1 - Connection is not available · JobService failed processing URL set state changed", "yes"),
 "E4": ("E", "Tenant limits reached", "Concurrent-scan or tenant/licence limits block new scans.",
        "Raise limit.running-scans-count or the licence.", "LimitExceededException: ... limit of concurrently running scans has been reached", "yes"),
 "E5": ("E", "Backend query error / timeout ('Error loading scan')", "UI endpoints fail on heavy Views, huge regexes, deleted scans, or backend 502s.",
        "Simplify the View; backend fix.", "GET /api/scans?propertyId&viewId → 500/502 · Scan <id> could not be found · Error loading scan", "yes"),
 # ---------------- F. PRODUCT: UI / export / integrations
 "F1": ("F", "Export failure", "Export not produced or delivered: 10k-row Excel limit, email job not sent, spam quarantine, bad filename, missing columns.",
        "Filter to under 10k rows; product fix; customer allowlists the sender.", "There was a problem creating your export · scan-csv.max-allowed-issues-count", "yes"),
 "F2": ("F", "Export count semantics", "Export row counts differ from the UI (one row per component/selector/language), so IDs look duplicated.",
        "Explanation.", "—", "no"),
 "F3": ("F", "UI bug / UI confusion", "Front-end defects (save fails without a time zone, blank settings, toggles, severity totals, Edge content-type) or misread UI (sorting, stale View filter, deprecated compare).",
        "Product fix or explanation.", "Content-Type 'application/x-www-form-urlencoded' not supported · /collections/undefined/properties", "maybe"),
 "F4": ("F", "Integration issue (Jira / ADO / MCP)", "Ticket-system or MCP integration errors: permissions, formatting, on-prem unsupported, auth.",
        "Product fix / permission change.", "TF401322 · WorkItemUnauthorizedRuleBypassException · MCP auth error", "maybe"),
 # ---------------- G. FINDINGS: rule accuracy, score, severity
 "G1": ("G", "Confirmed engine false positive", "A rule really misfires (contrast on gradients/opacity, text spacing, a rule bug, wrong selector).",
        "Engine fix (Jira).", "—", "no"),
 "G2": ("G", "Disputed finding: true positive", "Customer reports an FP that turns out to be valid, or can't be reproduced.", "Explanation with evidence.", "—", "no"),
 "G3": ("G", "Score / severity / WCAG configuration", "Score or severity changes (engine bumps, formula), Needs Review semantics, WCAG version scoping.",
        "Explanation or property engine config (enginesConfiguration, AXE runOnly).", "engine version change between scans", "no"),
 "G4": ("G", "Suppression / masking request", "Customer wants to hide a rule or component; there's no in-product dismiss.", "View filter workaround / feature request.", "—", "no"),
 # ---------------- H. ACCOUNT / REQUESTS: non-incidents
 "H1": ("H", "Access & licence", "User or role permissions, user not in tenant, expired licence.", "Retool add_user_to_tenant / role change.", "—", "no"),
 "H2": ("H", "Access setup questions (IPs / headers)", "Proactive questions about scanner IPs, custom headers, basic auth, Evinced domains.", "Share the NAT IP list / header options.", "—", "no"),
 "H3": ("H", "Config / admin task", "Onboarding, property creation/copy/restore, schedule, viewport, iframe, login set-up help with no failure.", "Support performs the task.", "—", "no"),
 "H4": ("H", "Feature request / how-to", "Feature asks and product questions.", "Product feedback.", "—", "no"),
 "H5": ("H", "Out of scope / noise", "Not Site Scanner (WFA, sales), duplicates, empty requests, unknown cause.", "Route / close.", "—", "no"),
}

FAMILY = {
 "A": ("Access blocked", "The site, network or bot protection prevents the scanner from fetching pages."),
 "B": ("Authentication & session", "The scanner can't log in, or loses the session while crawling."),
 "C": ("Crawl scope configuration", "Property settings (regex, seeds, grouping, mode) produce the wrong URL set."),
 "D": ("Page render & analysis engine", "Individual pages time out, crash the engine, or are analysed before they finish rendering."),
 "E": ("Evinced platform & infra", "Backend, scheduler, pipeline or limits on Evinced's side."),
 "F": ("Product UI, export & integrations", "Non-crawl product defects and reporting behaviour."),
 "G": ("Findings accuracy & scoring", "Whether issues, severities and scores are right."),
 "H": ("Account, requests & noise", "Non-incident tickets."),
}

RAW = {
 # A
 "bot_protection_waf_block":"A1","ip_block_403_firewall":"A1","bot_protection_customer_waf":"A1","site_blocking_not_whitelisted":"A1",
 "bot_protection_403_whitelist":"A1","bot_protection_whitelist_refused":"A1","bot_protection_partial_block":"A1","login_page_access_blocked":"A1",
 "ip_not_whitelisted_internal_site":"A1","login_required_and_firewall_ip_allowlist":"A1","ip_whitelist_request":"A1",
 "bot_protection_cloudflare_challenge":"A2","login_recaptcha_bot_block":"A2",
 "bot_protection_soft_block_200":"A3","onboarding_bulk_property_setup":"A3",
 "static_ip_not_enabled_for_property":"A4","static_ip_not_configured":"A4","ip_whitelist_egress_misconfig":"A4","fast_tier_non_static_ips":"A4",
 "rate_limit_429_link_discovery_loss":"A5","bot_protection_akamai_rate_limit":"A5",
 "bot_protection_akamai_old_user_agent":"A6",
 "ip_whitelist_geo_block":"A7","login_flow_geo_redirect":"A7",
 "redirect_loop_too_many_redirects":"A8","ssl_certificate_expired":"A9",
 # B
 "login_2fa_unsupported":"B1","mfa_login_blocked":"B1","mfa_2fa_blocks_login":"B1",
 "login_selector_stale":"B2","login_selector_wrong":"B2","login_selector_not_found":"B2","dynamic_login_selectors":"B2","interaction_selector_stale":"B2",
 "crawler_login_stale_credentials_and_oom":"B3","login_creds_not_propagated_to_crawler":"B3","login_credentials_invalid":"B3",
 "login_dynamic_session_url":"B4","login_flow_misconfigured_redirect":"B4","login_multi_step_custom_script":"B4","login_multistep_config":"B4",
 "login_flow_failed":"B4","login_flow_failed_product_bug":"B4","login_config_help":"B4",
 "session_logout_parallelism":"B5","login_multistep_session_loss":"B5","login_flow_changed_session_logout":"B5",
 # C
 "regex_excludes_all":"C1","regex_mismatch_locale_format":"C1","invalid_regex_in_property_config":"C1",
 "domain_whitelist_mismatch":"C2","regex_excludes_redirect_target":"C2","property_domain_validation_seed_path":"C2",
 "include_regex_scope_misconfigured":"C3","property_scope_regex_config":"C3","unexpected_locale_urls_crawled":"C3","crawl_scope_config_help":"C3",
 "crawl_scope_view_filter":"C3","seed_scope_change_soft404_and_relative_link":"C3","stale_crawl_comparison_site_changed":"C3",
 "seed_path_unreachable_404":"C4","redirect_to_error_page_scanned":"C4",
 "spa_fragment_urls_grouped":"C5","grouping_rules_query_params_collapsed":"C5","crawl_coverage_grouping_rules":"C5",
 "query_param_pages_not_discovered":"C5","url_normalization_duplicate_slashes":"C5",
 "non_standard_navigation_links":"C6","js_navigation_no_href_links":"C6","seed_domain_config_spa_or_login":"C6",
 "list_mode_single_url_misconfig":"C7",
 # D
 "page_ready_timeout_heavy_pages":"D1","page_load_timeout_specific_urls":"D1","scan_fails_large_page_count_complex_pages":"D1",
 "engine_error_circular_visibility_amp":"D2","engine_limit_huge_dom":"D2",
 "false_positive_incomplete_render":"D3","score_change_page_not_stabilized":"D3","false_positive_dynamic_content_timing":"D3",
 "popup_interstitial_scan_variance":"D3","screenshot_render_artifact":"D3","false_positive_heading_one":"D3",
 # E
 "platform_outage_june2026":"E1","platform_outage":"E1","ui_error_loading_scan_backend_outage":"E1","ui_data_not_loading_outage":"E1",
 "scan_stuck_infra":"E1","scan_failed_infra_error":"E1","infra_transient_page_failure":"E1","dashboard_not_loading_tenant_migration":"E1",
 "scheduler_next_run_timezone_bug":"E2","scheduler_next_run_date_bug":"E2","ui_stale_scan_timestamp":"E2",
 "crawl_dispatch_connection_refused_scrape_server_pool_exhaustion":"E3","crawl_and_scan_scan_phase_not_triggered_regression":"E3",
 "scan_failed_platform_bug":"E3","unknown_engineering_fix":"E3",
 "concurrent_scan_limit_exceeded":"E4","tenant_scan_limit_reached":"E4",
 "ui_error_loading_scan_backend_timeout":"E5","ui_view_query_500_large_regex":"E5","view_config_load_failure":"E5",
 "ui_error_loading_property_backend":"E5","scan_deleted_not_found":"E5",
 # F
 "export_row_limit":"F1","export_csv_not_delivered":"F1","export_email_blocked_spam_filter":"F1","export_email_quarantined_customer_spam_filter":"F1",
 "export_filename_special_chars":"F1","export_missing_columns_bug":"F1","export_screenshot_links_require_login":"F1","export_csv_delimiter_locale":"F1",
 "export_row_semantics_elements_vs_issues":"F2","export_count_mismatch":"F2","export_duplicate_ids_nested_interactive":"F2","duplicate_issues_multilang":"F2",
 "ui_dashboard_not_loading":"F3","ui_collection_id_undefined":"F3","ui_crawl_count_mismatch":"F3","ui_property_settings_blank_page":"F3",
 "ui_property_save_missing_timezone":"F3","custom_severity_ui_bug":"F3","ui_severity_totals_mismatch":"F3","ui_toggle_bug":"F3",
 "ui_layout_broken_deploy":"F3","ui_filter_bug_unconfirmed":"F3","unsupported_browser_edge":"F3","ui_error_loading_scan_client_side":"F3",
 "compare_scans_deprecated":"F3","scan_compare_beta_unsupported":"F3","ui_stale_view_filter":"F3","ui_view_filter_confusion":"F3",
 "ui_scan_list_sort_confusion":"F3","remove_url_from_completed_scan":"F3",
 "jira_integration_reporter_field":"F4","ado_integration_permissions":"F4","ado_integration_formatting_bug":"F4","jira_onprem_integration_config":"F4",
 "jira_onprem_integration_unsupported":"F4","integration_access_help":"F4","mcp_auth_error":"F4","feature_request_mcp_collections":"F4",
 # G
 "false_positive_color_contrast":"G1","false_positive_locked_text_spacing":"G1","false_positive_engine_rule_bug":"G1",
 "false_positive_bulk_dispute":"G1","wrong_css_selector_component":"G1",
 "issue_validity_explanation":"G2","false_positive_image_alt":"G2","false_positive_target_size":"G2","false_positive_nested_interactive":"G2",
 "false_positive_unreproducible":"G2",
 "score_calculation_explanation":"G3","score_delta_explanation":"G3","score_reset_request":"G3","severity_change_engine_bump":"G3",
 "needs_review_semantics":"G3","severity_filter_config":"G3","wcag_version_scoping_config":"G3",
 "false_positive_suppression_request":"G4",
 # H
 "access_permissions":"H1","access_readonly_role":"H1","access_user_not_in_tenant":"H1","license_expired_no_access":"H1",
 "ip_whitelist_info_request":"H2","custom_headers_config":"H2","basic_auth_custom_header":"H2","evinced_domains_allowlist_question":"H2",
 "tenant_provisioning_request":"H3","property_copy_request":"H3","schedule_frequency_adjustment":"H3","viewport_config_request":"H3",
 "iframe_scanning_config":"H3","property_creation_task":"H3","property_restore_archived":"H3","property_archive_howto":"H3",
 "onboarding_config_docs_request":"H3","property_creator_audit_request":"H3",
 "feature_request_ui":"H4","feature_request_component_naming":"H4","report_naming_feature_request":"H4","wcag_version_filter_feature_request":"H4",
 "export_date_range_feature_request":"H4","new_validation_feature_request":"H4","reporting_feature_request":"H4","feature_question_existing":"H4",
 "crawler_link_discovery_question":"H4","crawl_behavior_question":"H4","view_config_question":"H4","ui_how_to_question":"H4","wfa_vs_scanner_discrepancy":"H4",
 "wfa_sessions_not_loading":"H5","wfa_extension_bug":"H5","wfa_session_page_count_bug":"H5","sales_tam_question":"H5","sales_lead":"H5",
 "vague_request_no_details":"H5","unclear_request_no_info":"H5","duplicate_ticket":"H5","meeting_request_umbrella":"H5",
 "egress_encrypted_followup_unreadable":"H5","site_migrated_login_reconfig_abandoned":"H5",
 "unknown":"H5","unknown_unresolved_in_thread":"H5","unknown_not_investigated":"H5",
}

if __name__ == "__main__":
    rows, missing = [], set()
    for f in sorted(glob.glob(os.path.join(ROOT, "data/analysis/c*.json"))):
        for e in json.load(open(f)):
            sid = RAW.get(e["sub_issue"])
            if not sid: missing.add(e["sub_issue"]); continue
            rows.append({**e, "sub_id": sid, "family": SUB[sid][0]})
    assert not missing, f"unmapped labels: {sorted(missing)}"
    with open(os.path.join(ROOT, "data/ticket_labels.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticket", "client", "gt_class", "family", "sub_id", "sub_issue_name", "raw_label", "resolution_type", "detectable_in_logs", "jira", "gt_class_doubt"])
        for r in sorted(rows, key=lambda r: int(r["ticket"].lstrip("#"))):
            w.writerow([r["ticket"], r["client"], r["gt_class"], r["family"], r["sub_id"], SUB[r["sub_id"]][1], r["sub_issue"],
                        r["resolution_type"], r["detectable_in_logs"], " ".join(r.get("jira") or []), r.get("gt_class_doubt", "")])
    out = {"families": [], "gt_classes": {"1": "Scan/crawl failure (not 0 pages)", "2": "0 pages", "3": "Successful scan with failed pages",
                                          "4": "Crawl irregularities", "5": "Other"}}
    for fid, (fname, fdef) in FAMILY.items():
        subs = []
        for sid, (fam, name, d, fix, sig, det) in SUB.items():
            if fam != fid: continue
            ts = [r for r in rows if r["sub_id"] == sid]
            subs.append({"id": sid, "name": name, "definition": d, "fix": fix, "signature": sig, "detectability": det,
                         "count": len(ts), "gt": dict(collections.Counter(r["gt_class"] for r in ts)),
                         "resolution": dict(collections.Counter(r["resolution_type"] for r in ts)),
                         "raw_labels": sorted({r["sub_issue"] for r in ts}),
                         "tickets": [r["ticket"] for r in sorted(ts, key=lambda r: int(r["ticket"].lstrip("#")))]})
        out["families"].append({"id": fid, "name": fname, "definition": fdef, "count": sum(s["count"] for s in subs), "subs": subs})
    json.dump(out, open(os.path.join(ROOT, "data/taxonomy.json"), "w"), indent=1)
    for fam in out["families"]:
        print(fam["id"], fam["name"], fam["count"])
        for s in fam["subs"]:
            print("   ", s["id"], s["count"], s["name"], s["gt"])
    print("total", len(rows))
