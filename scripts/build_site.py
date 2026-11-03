"""Render site/taxonomy.html from site/template.html + data/taxonomy.json."""
import json, os
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t = open(f"{R}/site/template.html").read()
d = json.dumps(json.load(open(f"{R}/data/taxonomy.json"))).replace("</", "<\\/")
open(f"{R}/site/taxonomy.html", "w").write(t.replace("__DATA__", d))
print("ok")
