"""Fetch Zendesk tickets + comment threads for every ticket in the GT sheet.
Usage: python3 scripts/fetch_zendesk.py data/gt_tickets.json data/zendesk/
Requires env: ZENDESK_SUBDOMAIN, ZENDESK_EMAIL, ZENDESK_API_TOKEN
"""
import json, os, sys, time, base64, urllib.request
from concurrent.futures import ThreadPoolExecutor

SUB, EMAIL, TOK = (os.environ[k] for k in ("ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN"))
AUTH = "Basic " + base64.b64encode(f"{EMAIL}/token:{TOK}".encode()).decode()
BASE = f"https://{SUB}.zendesk.com/api/v2"

def get(url):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"Authorization": AUTH})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", 10))); continue
            if e.code == 404: return None
            time.sleep(2 ** attempt)
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(url)

def fetch(tid, outdir):
    path = os.path.join(outdir, f"{tid}.json")
    if os.path.exists(path): return
    t = get(f"{BASE}/tickets/{tid}.json")
    comments, url = [], f"{BASE}/tickets/{tid}/comments.json?page[size]=100"
    while url:
        d = get(url)
        if not d: break
        comments += [{"author_id": c["author_id"], "public": c["public"], "created_at": c["created_at"],
                      "body": c.get("plain_body") or c.get("body", "")} for c in d["comments"]]
        url = d.get("links", {}).get("next") if d.get("meta", {}).get("has_more") else None
    tk = (t or {}).get("ticket", {})
    json.dump({"id": tid, "subject": tk.get("subject"), "status": tk.get("status"), "tags": tk.get("tags"),
               "created_at": tk.get("created_at"), "comments": comments}, open(path, "w"), indent=1)

if __name__ == "__main__":
    gt, outdir = json.load(open(sys.argv[1])), sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    ids = [int(r["Ticket"].lstrip("#")) for r in gt]
    with ThreadPoolExecutor(6) as ex: list(ex.map(lambda i: fetch(i, outdir), ids))
    print("done", len(ids))
