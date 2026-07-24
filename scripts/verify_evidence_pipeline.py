"""Run one small real evidence task without printing credentials or page bodies."""

from __future__ import annotations

import asyncio

from src.config import Settings
from src.models.research import MethodologyTrace, ResearchPlanArtifact, ResearchTask
from src.providers.hkgai_mcp import HKGAIMCPProvider
from src.providers.hkgai_model import HKGAIModelProvider
from src.providers.hkgai_structured_rest import HKGAIStructuredRestProvider
from src.providers.search_router import SearchRouter
from src.services.evidence_collection import EvidenceCollectionService
from src.state.project import ProjectState


async def main() -> None:
    settings = Settings.load()
    project = ProjectState(
        project_name="中国分子诊断行业证据验证",
        industry="中国分子诊断行业",
        region="中国",
        research_objective="核验行业监管与市场发展的公开事实",
        time_horizon="2024-2026",
    )
    methodology = MethodologyTrace(
        sop_id="live-validation",
        sop_name="Live Validation",
        sop_version="1",
        sop_hash="runtime",
        rule_ids=["EVIDENCE-FIRST"],
    )
    plan = ResearchPlanArtifact(
        plan_summary="验证真实证据链路",
        tasks=[
            ResearchTask(
                task_id="T01",
                title="监管与市场事实",
                objective="寻找可追溯的中国分子诊断监管或市场事实",
                questions=["近期有哪些监管或市场变化？"],
                hypotheses=["监管变化正在影响行业竞争"],
                information_needs=["政府或监管公开信息"],
                preferred_sources=["政府、监管、正式机构"],
                search_queries=["中国 分子诊断 监管 政策 2025 官方"],
                deliverables=["证据候选"],
                evidence_standard="原文可定位、来源可追溯",
                validation_gate="人工核对来源",
            )
        ],
        human_review_gates=["来源核对", "证据接受"],
        methodology=methodology,
        human_confirmed=True,
    )
    router = SearchRouter(
        HKGAIMCPProvider(settings),
        HKGAIStructuredRestProvider(settings),
        mode=settings.search_transport,
    )
    service = EvidenceCollectionService(HKGAIModelProvider(settings), router)
    run = await service.collect_task(project, plan, "T01")
    print(f"queries={len(run.queries_used)}")
    print(f"sources={len(run.sources)}")
    print(f"crawled={sum(source.crawled for source in run.sources)}")
    print(f"evidence_candidates={len(run.evidence)}")
    print(f"statuses={sorted({item.review_status.value for item in run.evidence})}")
    print(f"transports={sorted({source.transport for source in run.sources})}")
    print(f"gaps={len(run.information_gaps)}")
    print(f"search_errors={len(run.search_errors)}")
    for error in run.search_errors:
        print(f"error={error}")


if __name__ == "__main__":
    asyncio.run(main())
