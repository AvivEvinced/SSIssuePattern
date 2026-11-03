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
t = open(f"{R}/site/report_template.html").read()
open(f"{R}/site/report.html", "w").write(t.replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
print("ok", round(nmi_f, 3), round(nmi_s, 3), "validated", len(lt["validated"]))
