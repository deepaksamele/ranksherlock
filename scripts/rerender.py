#!/usr/bin/env python3
"""Re-render report.html / report.pdf from an existing audit.json without re-crawling.

Usage: python rerender.py OUT_DIR [--pdf] [--brand NAME] [--client NAME] [--prepared-by NAME] [--accent #hex] [--logo URL]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ranksherlock.report import render_html, write_pdf  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--brand", default="RankSherlock")
    ap.add_argument("--client", default="")
    ap.add_argument("--prepared-by", default="")
    ap.add_argument("--accent", default="#0f766e")
    ap.add_argument("--logo", default="")
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    audit = json.loads((out / "audit.json").read_text(encoding="utf-8"))
    html_path = out / "report.html"
    html_path.write_text(render_html(audit, brand=args.brand, client=args.client, prepared_by=args.prepared_by, accent=args.accent, logo_url=args.logo), encoding="utf-8")
    note = None
    if args.pdf:
        note = write_pdf(str(html_path), str(out / "report.pdf"), brand=args.brand, client=args.client or audit["site"]["host"])
    print(json.dumps({"ok": True, "html": str(html_path), "pdf": None if (note or not args.pdf) else str(out / "report.pdf"), "pdf_note": note}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
