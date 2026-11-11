#!/usr/bin/env python3
"""Generate docs/checks.md (and print a JSON id list with --json) from the check ids declared in the engine."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "ranksherlock"
MODULES = {"technical.py": "Technical SEO", "schema_check.py": "Structured data", "content.py": "Content, on-page and AEO", "geo.py": "AI visibility (GEO)", "local.py": "Local SEO", "ecommerce.py": "E-commerce", "performance.py": "Performance"}
ADD_RE = re.compile(r'c\.add\(\s*f?"([^"]+)",\s*(?:"(critical|high|medium|low|info)"|[a-z_]+(?:\s+if\s+[^,]+?\s+else\s+"[a-z]+")?),\s*f?"([^"]+)"', re.S)
PASS_RE = re.compile(r'c\.passed\(\s*f?"([^"]+)",\s*f?"([^"]+)"')


def collect() -> dict:
    out = {}
    for fname, label in MODULES.items():
        src = (ROOT / fname).read_text(encoding="utf-8")
        fails = []
        seen = set()
        for cid, sev, title in ADD_RE.findall(src):
            cid = re.sub(r"\{[^}]+\}", "X", cid)
            if cid in seen:
                continue
            seen.add(cid)
            fails.append({"id": cid, "severity": sev or "varies", "title": re.sub(r"\{[^}]+\}", "N", title)})
        passes = [{"id": re.sub(r"\{[^}]+\}", "X", p[0]), "title": re.sub(r"\{[^}]+\}", "N", p[1])} for p in PASS_RE.findall(src)]
        out[fname] = {"label": label, "fails": fails, "passes": passes}
    return out


def main() -> int:
    data = collect()
    if "--json" in sys.argv:
        print(json.dumps(data, indent=1))
        return 0
    out = ["# RankSherlock checks", "", "Generated from the engine source. Severity shown is the default; many checks escalate with scale.", ""]
    total = 0
    for fname, info in data.items():
        out.append(f"## {info['label']}")
        out.append("")
        out.append("| Check id | Severity | Finding |")
        out.append("|---|---|---|")
        for f in info["fails"]:
            out.append(f"| `{f['id']}` | {f['severity']} | {f['title'].replace('|', '/')} |")
            total += 1
        if info["passes"]:
            out.append("")
            out.append("Pass markers: " + ", ".join(f"`{p['id']}`" for p in info["passes"]))
        out.append("")
    out.insert(3, f"Total distinct failing checks: {total}.")
    dest = Path(__file__).resolve().parent.parent / "docs" / "checks.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dest} ({total} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
