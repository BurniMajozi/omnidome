"""Verified source-location hints for operator jobs.

The runtime image does not contain the web source. These hints locate likely
components; they are not evidence that an agent inspected or changed code.
"""

from __future__ import annotations

import re

COMPONENTS = (
    ("Sales AI Lead Warmers", "apps/web/components/modules/sales-lead-warming.tsx", "Sales", ("lead warmer", "lead warmers", "lead warming", "sales ai lead")),
    ("Sales pipeline", "apps/web/components/modules/sales-pipeline-board.tsx", "Sales", ("sales pipeline", "pipeline board")),
    ("Agent Manager", "apps/web/app/dashboard/admin/agents/page.tsx", "Agent orchestration", ("agent manager", "agent directory")),
    ("Agent work queue", "apps/web/components/admin/agent-work-view.tsx", "Agent orchestration", ("work queue", "agent work", "work budgets")),
    ("Talent org chart", "apps/web/components/modules/talent/org-chart-view.tsx", "HR", ("org chart", "hired agent", "talent agent")),
)


def component_hints(objective: str) -> list[dict[str, str]]:
    words = re.sub(r"[^a-z0-9]+", " ", objective.lower()).strip()
    matches = []
    for name, path, module, aliases in COMPONENTS:
        if any(alias in words for alias in aliases):
            matches.append({"name": name, "source_path": path, "module": module})
    return matches[:4]


def briefing(hints: list[dict[str, str]]) -> str:
    if not hints:
        return ""
    lines = ["Verified architecture index (source locations only; code is not mounted in this runtime):"]
    lines.extend(f"- {item['name']}: {item['source_path']} ({item['module']})" for item in hints)
    lines.append("Do not claim a source change or live diagnostic unless a tool actually performed it. If code inspection is needed, hand off to a coding workspace or ask for the relevant source and logs.")
    return "\n".join(lines)
