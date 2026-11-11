"""Finding model shared by every analyzer. Every finding carries evidence and resolves its
client-facing explanation (what we check, why it matters, how to fix, how to verify) from the catalog."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SEVERITY_WEIGHT = {"critical": 10, "high": 6, "medium": 3, "low": 1, "info": 0}
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
# Diminishing returns: beyond these totals, extra findings of that severity count at half weight.
SEVERITY_SOFT_CAP = {"critical": 30, "high": 24, "medium": 15, "low": 6, "info": 0}
MAX_PENALTY = 50


_VERB_SING = {"have": "has", "are": "is", "do": "does", "carry": "carries", "canonicalise": "canonicalises", "miss": "misses"}


def tidy_title(title: str) -> str:
    """Fix '1 pages have' style grammar in generated finding titles."""
    import re

    def fix(m):
        noun = m.group(2)
        noun = noun[:-1] if noun.endswith("s") else noun
        verb = m.group(4)
        if verb:
            verb = _VERB_SING.get(verb, verb if verb.endswith("s") else verb + "s")
        return f"{m.group(1)}1 {noun}{m.group(3) or ''}{(' ' + verb) if verb else ''}"

    return re.sub(
        r"(^|\s)1 ((?:[a-z-]+ ){0,2}(?:pages|articles|titles|URLs|images|products|items|documents|links|templates|groups|descriptions|questions|listings))"
        r"(\s\([^)]*\))?(?: (have|are|do|share|carry|lack|read|forbid|disable|use|miss|show|end|serve|open|cite|embed|canonicalise|declare|load|link|contain|sit|return|go|point|lead|look|reuse|loads|returned|timed))?\b",
        fix,
        title,
    )


def weighted_penalty(findings: list[dict]) -> int:
    """Sum severity weights with a soft cap per severity (so 40 low findings cannot zero a category)."""
    total = 0.0
    for sev in SEVERITY_ORDER:
        n = sum(1 for f in findings if f.get("severity") == sev)
        w = SEVERITY_WEIGHT[sev]
        if not n or not w:
            continue
        raw = n * w
        cap = SEVERITY_SOFT_CAP[sev]
        total += raw if raw <= cap else cap + (raw - cap) * 0.5
    return round(total)


def score_from_penalty(pen: float, max_penalty: int = MAX_PENALTY) -> int:
    return max(0, round(100 - (100 * min(pen, max_penalty) / max_penalty)))


@dataclass
class Finding:
    id: str
    category: str
    severity: str
    title: str
    why: str
    fix: str
    evidence: list = field(default_factory=list)
    affected_count: int = 0
    effort: str = "medium"  # low / medium / high
    impact: str = "medium"  # low / medium / high
    pages: list = field(default_factory=list)
    group: str = ""  # sub-area inside the category (e.g. "Crawlability")
    what: str = ""  # what we checked, in client language
    steps: list = field(default_factory=list)  # how to fix, step by step
    verify: str = ""  # how to confirm the fix worked
    owner: str = ""  # developer / content / marketing / hosting
    ref: str = ""  # authoritative reference URL
    business_impact: str = ""  # one line in business terms
    why_long: str = ""  # client-language explanation from the catalog

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = [str(e)[:400] for e in self.evidence[:15]]
        d["pages"] = self.pages[:300]
        return d


class Collector:
    """Accumulates findings and pass/fail/skip checks per category, enriching each from the catalog."""

    def __init__(self, category: str):
        self.category = category
        self.findings: list[Finding] = []
        self.checks: list[dict] = []
        self._ids: set[str] = set()

    def _enrich(self, f: Finding) -> Finding:
        try:
            from .catalog import CHECKS
        except Exception:  # pragma: no cover
            return f
        meta = CHECKS.get(f.id) or {}
        f.group = f.group or meta.get("group", "")
        f.what = f.what or meta.get("what", "")
        f.steps = f.steps or list(meta.get("steps", []))
        f.verify = f.verify or meta.get("verify", "")
        f.owner = f.owner or meta.get("owner", "")
        f.ref = f.ref or meta.get("ref", "")
        f.business_impact = f.business_impact or meta.get("business_impact", "")
        f.why_long = meta.get("why_long", "")
        return f

    def add(self, id: str, severity: str, title: str, why: str, fix: str, evidence=None, pages=None, affected_count=None, effort="medium", impact=None, group: str = "", steps=None, verify: str = "", owner: str = "", ref: str = "") -> Finding:
        evidence = list(evidence or [])
        pages = list(pages or [])
        if affected_count is None:
            affected_count = len(pages) if pages else (len(evidence) if evidence else 1)
        if impact is None:
            impact = {"critical": "high", "high": "high", "medium": "medium", "low": "low", "info": "low"}[severity]
        title = tidy_title(title)
        f = Finding(id, self.category, severity, title, why, fix, evidence, affected_count, effort, impact, pages, group=group, steps=list(steps or []), verify=verify, owner=owner, ref=ref)
        f = self._enrich(f)
        self.findings.append(f)
        self._ids.add(id)
        self.checks.append({"id": id, "title": title, "status": "fail" if severity != "info" else "info", "severity": severity, "group": f.group, "affected": affected_count})
        return f

    def passed(self, id: str, title: str, note: str = "") -> None:
        if id in self._ids:
            return
        group = ""
        try:
            from .catalog import CHECKS

            group = (CHECKS.get(id) or {}).get("group", "")
        except Exception:  # pragma: no cover
            pass
        self.checks.append({"id": id, "title": tidy_title(title), "status": "pass", "note": note, "group": group})

    def skipped(self, id: str, title: str, note: str = "") -> None:
        self.checks.append({"id": id, "title": title, "status": "skip", "note": note})

    def has(self, id: str) -> bool:
        return id in self._ids

    def penalty(self) -> int:
        return weighted_penalty([{"severity": f.severity} for f in self.findings])

    def score(self, max_penalty: int = MAX_PENALTY) -> int:
        """100 minus weighted penalties with diminishing returns per severity, floored at 0."""
        return score_from_penalty(self.penalty(), max_penalty)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "score": self.score(),
            "penalty": self.penalty(),
            "findings": [f.to_dict() for f in self.findings],
            "checks": self.checks,
            "pass_count": sum(1 for c in self.checks if c["status"] == "pass"),
            "fail_count": sum(1 for c in self.checks if c["status"] == "fail"),
            "skip_count": sum(1 for c in self.checks if c["status"] == "skip"),
        }
