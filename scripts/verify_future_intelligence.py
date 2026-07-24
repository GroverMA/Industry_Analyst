"""Run a compact real evidence -> analysis -> future intelligence validation."""

from __future__ import annotations

import asyncio

from scripts.verify_industry_analysis import collect
from src.config import Settings
from src.knowledge.sop import load_active_sop
from src.models.analysis import AnalysisReviewStatus
from src.providers.hkgai_model import HKGAIModelProvider
from src.services.future_intelligence import FutureIntelligenceService
from src.services.industry_analysis import IndustryAnalysisService, review_analysis_finding
from src.state.project import ProjectState


async def main() -> None:
    settings = Settings.load()
    project = ProjectState(
        project_name="中国分子诊断Future Intelligence验证",
        industry="中国分子诊断行业",
        region="中国",
        research_objective="推演竞争格局、商业模式和客户需求可能如何变化",
        time_horizon="2026-2030",
    )
    evidence = await collect(settings, project)
    analysis = IndustryAnalysisService(
        HKGAIModelProvider(settings),
        load_active_sop(),
    ).generate(project, evidence)
    for finding in list(analysis.findings):
        analysis = review_analysis_finding(
            analysis,
            finding.finding_id,
            AnalysisReviewStatus.ACCEPTED,
            "automated live validation only",
        )
    analysis = analysis.model_copy(update={"human_confirmed": True})
    future = FutureIntelligenceService(
        HKGAIModelProvider(settings),
        load_active_sop(),
    ).generate(project, evidence, analysis)
    print(f"input_evidence={len(future.input_evidence_ids)}")
    print(f"input_findings={len(future.input_finding_ids)}")
    print(f"trends={len(future.trends)}")
    print(f"scenarios={len(future.scenarios)}")
    print(f"avg_confidence={round(sum(item.confidence.overall for item in future.trends) / len(future.trends))}")
    print(f"future_rules={len(future.methodology.rule_ids)}")


if __name__ == "__main__":
    asyncio.run(main())
