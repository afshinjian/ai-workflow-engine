"""Services that compose `agentos_dashboard.core` adapters and `agentos_dashboard.parsing`
views into higher-level page/API data. `DASH-003` adds the consistency engine only
(`services/consistency.py`); state/board/tasks/prompts/runs/audit services belong to later
stages (`ARCHITECTURE.md` §2).
"""

from __future__ import annotations
