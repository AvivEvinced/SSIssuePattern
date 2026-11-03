"""Print a compact text view of a fetched ticket. Usage: python3 scripts/dump_ticket.py <id> [maxchars_per_comment]"""
import json, re, sys
t = json.load(open(f"data/zendesk/{sys.argv[1]}.json"))
mx = int(sys.argv[2]) if len(sys.argv) > 2 else 2500
print(f"=== #{t['id']} | {t['subject']} | {t['status']} | tags={','.join(t['tags'] or [])}")
for i, c in enumerate(t["comments"]):
    b = c["body"] or ""
    b = re.split(r"\n(?:On .{5,120} wrote:|From: .*\nSent: |-----Original Message-----)", b)[0]  # drop quoted history
    b = re.sub(r"\n{3,}", "\n\n", b).strip()
    print(f"--- [{i}] {c['created_at'][:10]} author={c['author_id']} {'PUBLIC' if c['public'] else 'INTERNAL'}\n{b[:mx]}{' …[trunc]' if len(b)>mx else ''}")
