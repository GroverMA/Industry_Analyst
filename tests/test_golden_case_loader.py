from __future__ import annotations

from src.state.golden_case import load_golden_case
from src.state.project import ResearchMode, WorkflowStatus


def test_golden_case_is_an_optional_pack_not_the_product_boundary() -> None:
    project = load_golden_case()

    assert project.industry == "分子诊断"
    assert project.region == "中国"
    assert project.research_mode == ResearchMode.GOLDEN_CASE
    assert project.industry_pack == "molecular_diagnostics_cn"
    assert project.company_strategy_enabled is True
    assert project.company_strategy_objective
    assert project.workflow_status["research_brief"] == WorkflowStatus.COMPLETED
