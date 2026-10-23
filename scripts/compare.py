#!/usr/bin/env python3
"""Compare two RankSherlock audit.json files (before/after, or your site vs a competitor).

Usage: python compare.py BEFORE/audit.json AFTER/audit.json [--competitor]
Prints JSON: score deltas, resolved / new / persisting findings by id.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(p: str) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--competitor", action="store_true", help="treat files as two different sites instead of two runs of one site")
    args = ap.parse_args(argv)
    a, b = load(args.before), load(args.after)
    sa, sb = a["scores"], b["scores"]
    fa = {f["id"]: f for f in sa["findings"]}
    fb = {f["id"]: f for f in sb["findings"]}
    out = {
        "mode": "competitor" if args.competitor else "before-after",
        "sites": [a["site"]["host"], b["site"]["host"]],
        "dates": [a.get("generated_at", "")[:10], b.get("generated_at", "")[:10]],
        "overall": [sa["overall"], sb["overall"], (sb["overall"] or 0) - (sa["overall"] or 0)],
        "search_seo": [sa["search_seo"]["score"], sb["search_seo"]["score"]],
        "ai_visibility": [sa["ai_visibility"]["score"], sb["ai_visibility"]["score"]],
        "categories": {k: [(sa["categories"].get(k, {}).get("score") if sa["categories"].get(k, {}).get("measured", True) else None), (sb["categories"].get(k, {}).get("score") if sb["categories"].get(k, {}).get("measured", True) else None)] for k in sorted(set(sa["categories"]) | set(sb["categories"]))},
        "scoring_version_match": sa.get("scoring_version") == sb.get("scoring_version"),
    }
    if args.competitor:
        out["only_in_first"] = [{"id": k, "severity": v["severity"], "title": v["title"]} for k, v in fa.items() if k not in fb]
        out["only_in_second"] = [{"id": k, "severity": v["severity"], "title": v["title"]} for k, v in fb.items() if k not in fa]
        out["shared"] = sorted(set(fa) & set(fb))
    else:
        out["resolved"] = [{"id": k, "severity": v["severity"], "title": v["title"]} for k, v in fa.items() if k not in fb]
        out["new"] = [{"id": k, "severity": v["severity"], "title": v["title"]} for k, v in fb.items() if k not in fa]
        out["persisting"] = [{"id": k, "severity": fb[k]["severity"], "title": fb[k]["title"], "affected": [fa[k].get("affected_count"), fb[k].get("affected_count")]} for k in fa if k in fb]
        out["not_rechecked"] = [c for c in sa.get("measured", []) if c not in sb.get("measured", [])]
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
