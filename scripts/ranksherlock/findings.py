"""Finding model shared by every analyzer. Every finding carries evidence."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

SEVERITY_WEIGHT = {"critical": 10, "high": 6, "medium": 3, "low": 1, "info": 0}
SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence"] = [str(e)[:300] for e in self.evidence[:12]]
        d["pages"] = self.pages[:25]
        return d


class Collector:
    """Accumulates findings and simple pass/fail checks per category."""

    def __init__(self, category: str):
        self.category = category
        self.findings: list[Finding] = []
        self.checks: list[dict] = []

    def add(self, id: str, severity: str, title: str, why: str, fix: str, evidence=None, pages=None, affected_count=None, effort="medium", impact=None) -> Finding:
        evidence = list(evidence or [])
        pages = list(pages or [])
        if affected_count is None:
            affected_count = len(pages) if pages else (len(evidence) if evidence else 1)
        if impact is None:
            impact = {"critical": "high", "high": "high", "medium": "medium", "low": "low", "info": "low"}[severity]
        f = Finding(id, self.category, severity, title, why, fix, evidence, affected_count, effort, impact, pages)
        self.findings.append(f)
        self.checks.append({"id": id, "title": title, "status": "fail" if severity != "info" else "info", "severity": severity})
        return f

    def passed(self, id: str, title: str, note: str = "") -> None:
        self.checks.append({"id": id, "title": title, "status": "pass", "note": note})

    def skipped(self, id: str, title: str, note: str = "") -> None:
        self.checks.append({"id": id, "title": title, "status": "skip", "note": note})

    def penalty(self) -> int:
        return sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in self.findings)

    def score(self, max_penalty: int = 40) -> int:
        """100 minus weighted penalties, floored at 0. max_penalty tunes how fast a category hits zero."""
        pen = self.penalty()
        return max(0, round(100 - (100 * min(pen, max_penalty) / max_penalty)))

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "score": self.score(),
            "penalty": self.penalty(),
            "findings": [f.to_dict() for f in self.findings],
            "checks": self.checks,
            "pass_count": sum(1 for c in self.checks if c["status"] == "pass"),
            "fail_count": sum(1 for c in self.checks if c["status"] == "fail"),
        }
