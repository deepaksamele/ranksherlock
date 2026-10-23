#!/usr/bin/env python3
"""Generate docs/checks.md from the check ids declared in the engine (keeps docs honest)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "ranksherlock"
MODULES = {"technical.py": "Technical SEO", "schema_check.py": "Structured data", "content.py": "Content, on-page and AEO", "geo.py": "AI visibility (GEO)", "local.py": "Local SEO", "performance.py": "Performance"}
ADD_RE = re.compile(r'c\.add\(\s*f?"([^"]+)",\s*"(critical|high|medium|low|info)",\s*"([^"]+)"', re.S)
PASS_RE = re.compile(r'c\.passed\(\s*"([^"]+)",\s*f?"([^"]+)"')


def main() -> int:
    out = ["# RankSherlock checks", "", "Generated from the engine source. Severity shown is the default; some checks escalate with scale.", ""]
    total = 0
    for fname, label in MODULES.items():
        src = (ROOT / fname).read_text(encoding="utf-8")
        adds = ADD_RE.findall(src)
        passes = PASS_RE.findall(src)
        out.append(f"## {label}")
        out.append("")
        out.append("| Check id | Severity | Finding |")
        out.append("|---|---|---|")
        seen = set()
        for cid, sev, title in adds:
            if cid in seen:
                continue
            seen.add(cid)
            out.append(f"| `{cid}` | {sev} | {title.replace('|', '/')} |")
            total += 1
        if passes:
            out.append("")
            out.append("Pass markers: " + ", ".join(f"`{p[0]}`" for p in passes))
        out.append("")
    out.insert(3, f"Total distinct failing checks: {total}.")
    dest = Path(__file__).resolve().parent.parent / "docs" / "checks.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dest} ({total} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
