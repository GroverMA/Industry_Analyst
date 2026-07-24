"""Run a compact real evidence-to-industry-analysis validation."""

from __future__ import annotations

import asyncio

from src.config import Settings
from src.knowledge.sop import load_active_sop
from src.models.evidence import EvidenceReviewStatus
from src.models.research import MethodologyTrace, ResearchPlanArtifact, ResearchTask
from src.providers.hkgai_mcp import HKGAIMCPProvider
from src.providers.hkgai_model import HKGAIModelProvider
from src.providers.hkgai_structured_rest import HKGAIStructuredRestProvider
from src.providers.search_router import SearchRouter
from src.services.evidence_collection import EvidenceCollectionService, review_evidence, upsert_task_run
from src.services.industry_analysis import IndustryAnalysisService
from src.state.project import ProjectState


async def collect(settings: Settings, project: ProjectState):
    trace = MethodologyTrace(
        sop_id="live-validation",
        sop_name="Live Validation",
        sop_version="1",
        sop_hash="runtime",
        rule_ids=["EVIDENCE-FIRST"],
    )
    plan = ResearchPlanArtifact(
        plan_summary="验证真实行业分析链路",
        tasks=[
            ResearchTask(
                task_id="T01",
                title="中国分子诊断当前行业结构",
                objective="寻找当前市场、竞争和驱动因素的可追溯公开证据",
                questions=["当前行业结构和参与者有哪些公开事实？"],
                hypotheses=["监管和技术共同影响市场结构"],
                information_needs=["市场结构、参与者、监管、应用"],
                preferred_sources=["政府、正式机构、公司披露、专业研究"],
                search_queries=["中国 分子诊断 行业 竞争格局 驱动因素 2025"],
                deliverables=["行业分析证据"],
                evidence_standard="原文可定位、来源可追溯",
                validation_gate="人工核验",
            )
        ],
        human_review_gates=["证据核验", "行业判断审核"],
        methodology=trace,
        human_confirmed=True,
    )
    router = SearchRouter(
        HKGAIMCPProvider(settings),
        HKGAIStructuredRestProvider(settings),
        mode=settings.search_transport,
    )
    collector = EvidenceCollectionService(HKGAIModelProvider(settings), router)
    run = await collector.collect_task(project, plan, "T01")
    artifact = upsert_task_run(None, plan.artifact_id, run)
    reviewable = [
        item for item in artifact.evidence
        if item.review_status not in {
            EvidenceReviewStatus.UNSUPPORTED,
            EvidenceReviewStatus.OUT_OF_SCOPE,
        }
    ]
    if not reviewable:
        raise RuntimeError("live collection produced no reviewable evidence")
    for item in reviewable:
        artifact = review_evidence(
            artifact,
            item.evidence_id,
            EvidenceReviewStatus.ACCEPTED,
            "automated live validation only",
        )
    return artifact.model_copy(update={"human_confirmed": True})


async def main() -> None:
    settings = Settings.load()
    project = ProjectState(
        project_name="中国分子诊断当前行业分析验证",
        industry="中国分子诊断行业",
        region="中国",
        research_objective="分析当前市场结构、竞争关系、驱动制约与商业逻辑",
        time_horizon="2024-2026",
    )
    evidence = await collect(settings, project)
    analysis = IndustryAnalysisService(
        HKGAIModelProvider(settings),
        load_active_sop(),
    ).generate(project, evidence)
    print(f"accepted_evidence={len(analysis.input_evidence_ids)}")
    print(f"modules={len(analysis.modules)}")
    print(f"findings={len(analysis.findings)}")
    print(f"empty_modules={sum(not module.findings for module in analysis.modules)}")
    print(f"analysis_rules={len(analysis.methodology.rule_ids)}")


if __name__ == "__main__":
    asyncio.run(main())
