"""Build site/report.html: comparison of views, data-drivenness, log tree, crosswalk, back-test, signature catalog."""
import json, csv, collections, math, os, subprocess
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
subprocess.run(["python3", f"{R}/scripts/logtree.py"], check=True, capture_output=True)
tax = json.load(open(f"{R}/data/taxonomy.json"))
lt = json.load(open(f"{R}/data/logtree.json"))
agr = json.load(open(f"{R}/data/analysis/agreement.json"))
rows = list(csv.DictReader(open(f"{R}/data/ticket_labels.csv")))
ct = collections.Counter((r["gt_class"], r["family"]) for r in rows)
def H(c):
    n = sum(c.values()); return -sum(v/n*math.log2(v/n) for v in c.values() if v)
hc = H(collections.Counter(r["gt_class"] for r in rows)); hf = H(collections.Counter(r["family"] for r in rows))
hs = H(collections.Counter(r["sub_id"] for r in rows))
nmi_f = 2*(hc+hf-H(ct))/(hc+hf)
nmi_s = 2*(hc+hs-H(collections.Counter((r["gt_class"], r["sub_id"]) for r in rows)))/(hc+hs)
data = {"tax": tax, "lt": lt, "agr": {"n": agr["n"], "sub": agr["sub"], "fam": agr["fam"], "pairs": agr["pairs"]},
        "crosstab": {f"{c}|{f}": n for (c, f), n in ct.items()}, "nmi_f": nmi_f, "nmi_s": nmi_s,
        "raw_labels": len({r["raw_label"] for r in rows}),
        "doubts": sum(1 for r in rows if r["gt_class_doubt"].strip())}
import sys, re, html as H_
sys.path.insert(0, f"{R}/scripts"); import logtree
subprocess.run(["python3", f"{R}/scripts/detectability.py"], check=True, capture_output=True)
data["tickets"] = [{"t": r["ticket"], "gt": r["gt_class"], "fam": r["family"], "sub": r["sub_id"], "leaf": logtree.PRIMARY[r["sub_id"]]} for r in rows]
data["det"] = json.load(open(f"{R}/data/detectability.json"))
data["dis"] = [json.load(open(f"{R}/data/logs/disambig_{g}.json")) for g in ("access", "login", "discovery_platform")]
for g, n in zip(data["dis"], ("access", "login", "discovery_platform")): g["group"] = n
def md2html(md):
    out, tbl = [], []
    def inline(x):
        x = H_.escape(x); x = re.sub(r"`([^`]+)`", r"<code>\1</code>", x); return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", x)
    def flush():
        if tbl:
            hdr, body = tbl[0], [r for r in tbl[2:]]
            out.append('<div class="tbl"><table><tr>' + "".join(f"<th>{inline(c)}</th>" for c in hdr) + "</tr>" +
                       "".join("<tr>" + "".join(f'<td class="small">{inline(c)}</td>' for c in r) + "</tr>" for r in body) + "</table></div>")
            tbl.clear()
    ul = False
    for line in md.splitlines():
        if line.startswith("|"):
            tbl.append([c.strip() for c in line.strip().strip("|").split("|")]); continue
        flush()
        if line.startswith("- "):
            if not ul: out.append("<ul>"); ul = True
            out.append(f"<li>{inline(line[2:])}</li>"); continue
        if ul: out.append("</ul>"); ul = False
        if line.startswith("## "): out.append(f"<h3>{inline(line[3:])}</h3>")
        elif line.startswith("# "): continue
        elif line.strip(): out.append(f'<p class="small">{inline(line)}</p>')
    flush()
    if ul: out.append("</ul>")
    return "".join(out)
data["gaps"] = md2html(open(f"{R}/docs/backend_logging_gaps.md").read())
t = open(f"{R}/site/report_template.html").read()
open(f"{R}/site/report.html", "w").write(t.replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
print("ok", round(nmi_f, 3), round(nmi_s, 3), "validated", len(lt["validated"]))
