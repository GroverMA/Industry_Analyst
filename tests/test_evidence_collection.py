from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime

from src.models.evidence import (
    CrawlResult,
    CrawledPage,
    EvidenceCollectionArtifact,
    EvidenceReviewStatus,
    SearchHit,
    SourceTier,
    WebSearchResult,
)
from src.models.research import MethodologyTrace, ResearchPlanArtifact, ResearchTask
from src.providers.base import ModelResponse
from src.providers.search_router import RoutedCrawlResult, RoutedSearchResult
from src.services.evidence_collection import (
    EvidenceCollectionService,
    classify_source,
    evidence_coverage_advisories,
    evidence_coverage_gaps,
    evidence_gate_reasons,
    review_evidence,
    upsert_task_run,
)
from src.state.project import ProjectState


def methodology() -> MethodologyTrace:
    return MethodologyTrace(
        sop_id="test",
        sop_name="Test SOP",
        sop_version="1",
        sop_hash="abc",
        rule_ids=["EVIDENCE-1"],
    )


def plan() -> ResearchPlanArtifact:
    return ResearchPlanArtifact(
        plan_summary="test",
        tasks=[
            ResearchTask(
                task_id="T01",
                title="市场规模",
                objective="核验市场规模",
                questions=["市场有多大？"],
                hypotheses=["市场增长"],
                information_needs=["正式统计"],
                preferred_sources=["政府"],
                search_queries=["中国 分子诊断 市场 统计", "分子诊断 监管 数据"],
                deliverables=["证据矩阵"],
                evidence_standard="必须可追溯",
                validation_gate="人工审核",
            )
        ],
        human_review_gates=["来源审核"],
        methodology=methodology(),
        human_confirmed=True,
    )


def project() -> ProjectState:
    return ProjectState(
        project_name="分子诊断研究",
        industry="中国分子诊断行业",
        region="中国",
        research_objective="研究行业现状",
        time_horizon="2024-2030",
    )


class FakeRouter:
    async def search_web(self, query: str) -> RoutedSearchResult:
        return RoutedSearchResult(
            result=WebSearchResult(
                query=query,
                results=[
                    SearchHit(
                        title="国家监管数据",
                        url="https://example.gov.cn/report",
                        content="官方统计摘要",
                        score=0.95,
                    ),
                    SearchHit(
                        title="行业新闻",
                        url="https://industry.example.com/news",
                        content="行业摘要",
                        score=0.8,
                    ),
                ],
            ),
            transport="rest",
            fallback_reason="MCP unavailable",
        )

    async def crawl_page(self, url: str) -> RoutedCrawlResult:
        return RoutedCrawlResult(
            result=CrawlResult(
                pages=[
                    CrawledPage(
                        url=url,
                        raw_content="官方数据显示，样本数量在2025年达到一万例。其他说明。",
                    )
                ]
            ),
            transport="rest",
        )


class FakeModel:
    def complete_json(self, messages, *, enable_thinking=False):
        source_id = re.search(r"SRC-[0-9a-f]+", messages[-1].content).group(0)
        payload = {
            "evidence": [
                {
                    "source_id": source_id,
                    "kind": "data",
                    "statement": "2025年样本数量达到一万例。",
                    "supporting_excerpt": "样本数量在2025年达到一万例",
                    "source_date": "2025",
                    "geographic_scope": "中国",
                    "market_scope": "分子诊断",
                    "supports_or_challenges": "supports",
                    "model_confidence": 0.9,
                    "prompt_relevance": 0.95,
                    "question_ids": ["T01-Q1"],
                    "prompt_question_ids": [],
                    "scope_match": True,
                }
            ],
            "conflicts": [],
            "information_gaps": ["缺少收入规模口径"],
        }
        return payload, ModelResponse(content="{}", model="fake")


def test_source_classifier_is_transparent() -> None:
    assert classify_source("https://www.stats.gov.cn/data")[0] == SourceTier.A
    assert classify_source("https://university.edu/paper")[0] == SourceTier.B
    assert classify_source("https://baike.baidu.com/item/x")[0] == SourceTier.D
    assert classify_source("https://industry.example.com/news")[0] == SourceTier.C


def test_collection_builds_candidate_evidence_and_deduplicates_urls() -> None:
    service = EvidenceCollectionService(FakeModel(), FakeRouter())  # type: ignore[arg-type]
    result = asyncio.run(service.collect_task(project(), plan(), "T01"))

    assert len(result.queries_used) == 3
    assert len(result.sources) == 2
    assert len(result.evidence) == 1
    assert result.evidence[0].review_status == EvidenceReviewStatus.NEEDS_REVIEW
    assert result.evidence[0].qa_score >= 90
    assert result.information_gaps == ["缺少收入规模口径"]


def test_human_review_controls_evidence_gate() -> None:
    research_plan = plan()
    service = EvidenceCollectionService(FakeModel(), FakeRouter())  # type: ignore[arg-type]
    run = asyncio.run(service.collect_task(project(), research_plan, "T01"))
    artifact = upsert_task_run(None, research_plan.artifact_id, run)

    assert evidence_gate_reasons(artifact, research_plan) == ["T01 尚无人工接受的证据"]
    accepted = review_evidence(
        artifact,
        run.evidence[0].evidence_id,
        EvidenceReviewStatus.ACCEPTED,
        "已核对原网页",
    )
    assert evidence_gate_reasons(accepted, research_plan) == []
    assert accepted.evidence[0].reviewer_note == "已核对原网页"


def test_task_run_crosses_json_boundary_after_streamlit_hot_reload() -> None:
    research_plan = plan()
    service = EvidenceCollectionService(FakeModel(), FakeRouter())  # type: ignore[arg-type]
    run = asyncio.run(service.collect_task(project(), research_plan, "T01"))

    class HotReloadTaskRunProxy:
        """Same payload, different runtime class identity."""

        task_id = run.task_id

        @staticmethod
        def model_dump(*, mode: str = "python"):
            return run.model_dump(mode=mode)

    artifact = upsert_task_run(
        None,
        research_plan.artifact_id,
        HotReloadTaskRunProxy(),  # type: ignore[arg-type]
    )

    assert artifact.task_runs[0].task_id == "T01"


def test_quick_pipeline_authorization_allows_unconfirmed_plan_execution() -> None:
    research_plan = plan().model_copy(update={"human_confirmed": False})
    quick_project = project().model_copy(
        update={"execution_authorized_at": datetime.now(UTC)}
    )
    service = EvidenceCollectionService(FakeModel(), FakeRouter())  # type: ignore[arg-type]

    run = asyncio.run(service.collect_task(quick_project, research_plan, "T01"))

    assert run.task_id == "T01"


def test_gate_allows_reviewed_evidence_and_preserves_uncovered_question() -> None:
    research_plan = plan()
    task = research_plan.tasks[0].model_copy(
        update={"questions": ["市场有多大？", "市场为什么增长？"]}
    )
    research_plan = research_plan.model_copy(update={"tasks": [task]})
    service = EvidenceCollectionService(FakeModel(), FakeRouter())  # type: ignore[arg-type]
    run = asyncio.run(service.collect_task(project(), research_plan, "T01"))
    artifact = upsert_task_run(None, research_plan.artifact_id, run)
    accepted = review_evidence(
        artifact,
        run.evidence[0].evidence_id,
        EvidenceReviewStatus.ACCEPTED,
        "已核对原网页",
    )

    reasons = evidence_gate_reasons(accepted, research_plan)
    gaps = evidence_coverage_gaps(accepted, research_plan)
    advisories = evidence_coverage_advisories(accepted, research_plan)

    assert reasons == []
    assert any("T01-Q2" in detail for detail in gaps["T01"])
    assert advisories[0]["task_id"] == "T01"
    assert "降低结论置信度" in advisories[0]["recommended_handling"]
