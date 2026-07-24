"""Live smoke test for the SOP-governed Research Brief and Planner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Settings  # noqa: E402
from src.knowledge.sop import load_active_sop  # noqa: E402
from src.providers.hkgai_model import HKGAIModelProvider  # noqa: E402
from src.services.research_planning import ResearchPlanningService  # noqa: E402
from src.state.golden_case import load_golden_case  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-plan", action="store_true")
    args = parser.parse_args()

    service = ResearchPlanningService(
        HKGAIModelProvider(Settings.load()),
        load_active_sop(),
    )
    project = load_golden_case()
    brief = service.generate_brief(project)
    print(
        "Brief: OK — "
        f"{len(brief.key_questions)} questions, "
        f"{len(brief.hypotheses)} hypotheses, "
        f"SOP {brief.methodology.sop_id}@{brief.methodology.sop_version}"
    )
    if args.with_plan:
        brief = brief.model_copy(update={"human_confirmed": True})
        plan = service.generate_plan(project, brief)
        print(
            "Plan:  OK — "
            f"{len(plan.tasks)} tasks, "
            f"{len(plan.human_review_gates)} review gates, "
            f"SOP locked={plan.methodology.locked}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
