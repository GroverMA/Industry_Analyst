"""Report-first orchestration for retrospective reviewer workspaces.

The consultant workflow deliberately stops at human gates.  Reviewer mode has
the opposite interaction contract: after confirming scope, it produces the
report and every traceable artifact in one run, then lets the reviewer inspect
the references and reasoning retrospectively.

Existing domain services still require approved inputs.  This module satisfies
those contracts with *ephemeral pipeline copies*.  The artifacts persisted on
the returned project remain ``needs_review`` and therefore never misrepresent
an automated selection as a human decision.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from src.models.analysis import AnalysisReviewStatus, IndustryAnalysisArtifact
from src.models.evidence import (
    EvidenceCollectionArtifact,
    EvidenceReviewStatus,
)
from src.models.future import ForecastReviewStatus, FutureIntelligenceArtifact
from src.models.report import GeneralReportArtifact
from src.models.research import ResearchPlanArtifact
from src.models.strategy import (
    ActionPlanArtifact,
    CompanyScorecardArtifact,
    EnterpriseDecisionReportArtifact,
    StrategyReviewStatus,
)
from src.services.evidence_collection import (
    EvidenceCollectionService,
    evidence_coverage_advisories,
    evidence_is_gate_one_candidate,
    unresolved_task_run,
    upsert_task_run,
)
from src.services.strategy_report import generate_enterprise_decision_report
from src.state.project import ProjectState, WorkflowStatus


class PlanningService(Protocol):
    def generate_plan(self, project: ProjectState, brief) -> ResearchPlanArtifact: ...


class IndustryService(Protocol):
    def generate(
        self,
        project: ProjectState,
        evidence_artifact: EvidenceCollectionArtifact,
    ) -> IndustryAnalysisArtifact: ...


class FutureService(Protocol):
    def generate(
        self,
        project: ProjectState,
        evidence_artifact: EvidenceCollectionArtifact,
        analysis_artifact: IndustryAnalysisArtifact,
        *,
        allow_pending_findings: bool = False,
    ) -> FutureIntelligenceArtifact: ...


class GeneralReportService(Protocol):
    def generate(self, project: ProjectState) -> GeneralReportArtifact: ...


class CompanyService(Protocol):
    def generate(self, project: ProjectState) -> CompanyScorecardArtifact: ...


class ActionService(Protocol):
    def generate(self, project: ProjectState) -> ActionPlanArtifact: ...


ProgressCallback = Callable[[str, int, int], None]
EnterpriseReportBuilder = Callable[[ProjectState], EnterpriseDecisionReportArtifact]


class ReviewerPipelineError(RuntimeError):
    """A safe stage error that retains successfully generated partial work."""

    def __init__(self, stage: str, message: str, project: ProjectState) -> None:
        super().__init__(f"{stage}：{message}")
        self.stage = stage
        self.project = project


@dataclass(frozen=True, slots=True)
class ReviewerPipelineResult:
    project: ProjectState
    enterprise: bool
    generated_stages: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def report(self) -> GeneralReportArtifact | EnterpriseDecisionReportArtifact:
        if self.enterprise:
            artifact = self.project.enterprise_decision_report_artifact
            assert artifact is not None
            return artifact
        artifact = self.project.general_report_artifact
        assert artifact is not None
        return artifact


class ReviewerOrchestrationService:
    """Build all reviewer artifacts before exposing the trace views.

    A failed research task is recorded once as an explicit limitation.  A retry
    resumes from the first missing artifact and does not silently repeat already
    completed web research.
    """

    STAGES = (
        "research_plan",
        "reference_collection",
        "industry_analysis",
        "future_intelligence",
        "general_report",
        "company_scorecard",
        "action_plan",
        "enterprise_report",
    )

    def __init__(
        self,
        *,
        planning: PlanningService,
        evidence: EvidenceCollectionService,
        industry: IndustryService,
        future: FutureService,
        report: GeneralReportService,
        company: CompanyService | None = None,
        action: ActionService | None = None,
        enterprise_report_builder: EnterpriseReportBuilder = generate_enterprise_decision_report,
    ) -> None:
        self.planning = planning
        self.evidence = evidence
        self.industry = industry
        self.future = future
        self.report = report
        self.company = company
        self.action = action
        self.enterprise_report_builder = enterprise_report_builder

    async def run(
        self,
        project: ProjectState,
        *,
        enterprise: bool | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ReviewerPipelineResult:
        enterprise = project.company_strategy_enabled if enterprise is None else enterprise
        self._validate_preconditions(project, enterprise)
        generated: list[str] = []
        warnings: list[str] = []
        active = project.model_copy(
            update={
                "execution_authorized_at": project.execution_authorized_at
                or datetime.now(UTC),
                "last_pipeline_error": None,
                "updated_at": datetime.now(UTC),
            }
        )

        def progress(stage: str) -> None:
            generated.append(stage)
            if on_progress is not None:
                on_progress(stage, len(generated), 8 if enterprise else 5)

        try:
            plan = active.research_plan_artifact
            if plan is None:
                plan = self.planning.generate_plan(active, active.research_brief_artifact)
                active = active.model_copy(update={"research_plan_artifact": plan})
            progress("research_plan")

            evidence = active.evidence_collection_artifact
            completed_tasks = {
                run.task_id for run in evidence.task_runs
            } if evidence and evidence.research_plan_id == plan.artifact_id else set()
            if evidence is not None and evidence.research_plan_id != plan.artifact_id:
                evidence = None
            for task in plan.tasks:
                if task.task_id in completed_tasks:
                    continue
                try:
                    run = await self.evidence.collect_task(active, plan, task.task_id)
                except Exception as exc:  # task failure becomes an auditable limitation
                    run = unresolved_task_run(active, task, str(exc))
                    warnings.append(f"{task.task_id}首次检索结果有限，已列入Content Revision重点审阅。")
                evidence = upsert_task_run(evidence, plan.artifact_id, run)
                active = active.model_copy(update={"evidence_collection_artifact": evidence})
            if evidence is None:
                raise ValueError("未建立Reference Matrix")
            # Coverage advice is explanatory metadata, never a generation
            # gate.  Older persisted plans may predate question-level fields;
            # they must remain runnable instead of failing report creation.
            try:
                warnings.extend(
                    row["recommended_handling"]
                    for row in evidence_coverage_advisories(evidence, plan)
                )
            except (AttributeError, TypeError, ValueError):
                warnings.append(
                    "当前项目沿用旧版研究计划，Reference Check将按已有来源展示，"
                    "不提供问题级覆盖提示。"
                )
            pipeline_evidence = _pipeline_evidence(evidence)
            active = active.model_copy(update={"evidence_collection_artifact": evidence})
            progress("reference_collection")

            analysis = active.industry_analysis_artifact
            if (
                analysis is None
                or analysis.evidence_collection_id != evidence.artifact_id
                or any(not module.findings for module in analysis.modules)
            ):
                analysis = self.industry.generate(
                    active,
                    pipeline_evidence,
                )
                active = active.model_copy(update={"industry_analysis_artifact": analysis})
            pipeline_analysis = _pipeline_analysis(analysis)
            progress("industry_analysis")

            future = active.future_intelligence_artifact
            if (
                future is None
                or future.industry_analysis_id != analysis.artifact_id
                or future.evidence_collection_id != evidence.artifact_id
            ):
                future = self.future.generate(
                    active,
                    pipeline_evidence,
                    analysis,
                    allow_pending_findings=True,
                )
                active = active.model_copy(update={"future_intelligence_artifact": future})
            pipeline_future = _pipeline_future(future)
            progress("future_intelligence")

            pipeline_project = active.model_copy(
                update={
                    "evidence_collection_artifact": pipeline_evidence,
                    "industry_analysis_artifact": pipeline_analysis,
                    "future_intelligence_artifact": pipeline_future,
                }
            )
            general = active.general_report_artifact
            if general is None or _report_requires_regeneration(general.markdown):
                general = self.report.generate(pipeline_project).model_copy(
                    update={"report_status": "reviewer_draft"}
                )
                active = active.model_copy(
                    update={
                        "general_report_artifact": general,
                        "content_revision_artifact": None,
                        "enterprise_decision_report_artifact": None,
                    }
                )
            progress("general_report")

            if enterprise:
                assert self.company is not None and self.action is not None
                scorecard = active.company_scorecard_artifact
                if scorecard is None:
                    scorecard = self.company.generate(
                        pipeline_project.model_copy(
                            update={"general_report_artifact": general}
                        )
                    )
                    active = active.model_copy(update={"company_scorecard_artifact": scorecard})
                pipeline_scorecard = _pipeline_scorecard(scorecard)
                progress("company_scorecard")

                action_plan = active.action_plan_artifact
                if action_plan is None or action_plan.scorecard_id != scorecard.artifact_id:
                    action_plan = self.action.generate(
                        pipeline_project.model_copy(
                            update={
                                "general_report_artifact": general,
                                "company_scorecard_artifact": pipeline_scorecard,
                            }
                        )
                    )
                    active = active.model_copy(update={"action_plan_artifact": action_plan})
                pipeline_action = _pipeline_action_plan(action_plan)
                progress("action_plan")

                enterprise_report = active.enterprise_decision_report_artifact
                if enterprise_report is None or _report_requires_regeneration(
                    enterprise_report.markdown
                ):
                    enterprise_report = self.enterprise_report_builder(
                        pipeline_project.model_copy(
                            update={
                                "general_report_artifact": general,
                                "company_scorecard_artifact": pipeline_scorecard,
                                "action_plan_artifact": pipeline_action,
                            }
                        )
                    )
                    active = active.model_copy(
                        update={"enterprise_decision_report_artifact": enterprise_report}
                    )
                progress("enterprise_report")

            active = _set_generated_workflow_statuses(active, enterprise)
            return ReviewerPipelineResult(
                project=active,
                enterprise=enterprise,
                generated_stages=tuple(generated),
                warnings=tuple(dict.fromkeys(warnings)),
            )
        except ReviewerPipelineError:
            raise
        except Exception as exc:
            stage = self.STAGES[min(len(generated), len(self.STAGES) - 1)]
            failed = active.model_copy(
                update={
                    "last_pipeline_error": f"{stage}：{exc}",
                    "updated_at": datetime.now(UTC),
                }
            )
            raise ReviewerPipelineError(stage, str(exc), failed) from exc

    def _validate_preconditions(self, project: ProjectState, enterprise: bool) -> None:
        brief = project.research_brief_artifact
        if brief is None or not brief.human_confirmed:
            raise ReviewerPipelineError("scope", "请先确认研究需求与市场范围", project)
        if enterprise:
            if not project.company_strategy_enabled:
                raise ReviewerPipelineError("scope", "项目未启用企业战略决策支持", project)
            sensing = project.enterprise_sensing_artifact
            if sensing is None or not sensing.human_confirmed or not sensing.accepted_entries:
                raise ReviewerPipelineError(
                    "enterprise_sensing",
                    "请先上传、审阅并确认企业一手资料",
                    project,
                )
            if self.company is None or self.action is None:
                raise ReviewerPipelineError(
                    "configuration",
                    "企业审阅式研究流程尚未配置Company Scorecard或Action Plan服务",
                    project,
                )


def _pipeline_evidence(artifact: EvidenceCollectionArtifact) -> EvidenceCollectionArtifact:
    """Select the best available material without turning thresholds into a gate."""

    selected = 0
    runs = []
    for run in artifact.task_runs:
        ranked_ids = {
            item.evidence_id
            for item in sorted(
                run.evidence,
                key=lambda row: (row.prompt_relevance, row.qa_score),
                reverse=True,
            )[: max(1, min(6, len(run.evidence)))]
        }
        items = []
        for item in run.evidence:
            if evidence_is_gate_one_candidate(item) or item.evidence_id in ranked_ids:
                selected += 1
                item = item.model_copy(
                    update={
                        "review_status": EvidenceReviewStatus.ACCEPTED,
                        "reviewer_note": (
                            "系统按Prompt相关性和资料质量预选；低于建议阈值的材料仅用于形成"
                            "可审阅草稿，并已在Content Revision标记重点核对。"
                        ),
                    }
                )
            items.append(item)
        runs.append(run.model_copy(update={"evidence": items}))
    if not selected:
        raise ValueError("网页检索未返回任何可用于形成草稿的内容")
    return artifact.model_copy(update={"task_runs": runs, "human_confirmed": True})


def _pipeline_analysis(artifact: IndustryAnalysisArtifact) -> IndustryAnalysisArtifact:
    modules = []
    count = 0
    for module in artifact.modules:
        findings = []
        for finding in module.findings:
            count += 1
            findings.append(
                finding.model_copy(
                    update={
                        "review_status": AnalysisReviewStatus.ACCEPTED,
                        "reviewer_note": "系统草稿判断，仍待人工追溯检查。",
                    }
                )
            )
        modules.append(module.model_copy(update={"findings": findings}))
    implications = [
        item.model_copy(update={"review_status": AnalysisReviewStatus.ACCEPTED})
        for item in artifact.company_implications
    ]
    if not count:
        raise ValueError("行业分析未形成任何可用于报告的结构化判断")
    return artifact.model_copy(
        update={
            "modules": modules,
            "company_implications": implications,
            "human_confirmed": True,
        }
    )


def _pipeline_future(artifact: FutureIntelligenceArtifact) -> FutureIntelligenceArtifact:
    trends = [
        item.model_copy(
            update={
                "review_status": ForecastReviewStatus.ACCEPTED,
                "reviewer_note": "系统草稿趋势，仍待人工追溯检查。",
            }
        )
        for item in artifact.trends
    ]
    scenarios = [
        item.model_copy(
            update={
                "review_status": ForecastReviewStatus.ACCEPTED,
                "reviewer_note": "系统草稿情景，仍待人工追溯检查。",
            }
        )
        for item in artifact.scenarios
    ]
    return artifact.model_copy(
        update={"trends": trends, "scenarios": scenarios, "human_confirmed": True}
    )


def _pipeline_scorecard(artifact: CompanyScorecardArtifact) -> CompanyScorecardArtifact:
    dimensions = []
    scored_count = 0
    scored_weight = 0.0
    for item in artifact.dimensions:
        accepted = item.score is not None
        if accepted:
            scored_count += 1
            scored_weight += item.weight
        dimensions.append(
            item.model_copy(
                update={
                    "review_status": (
                        StrategyReviewStatus.ACCEPTED
                        if accepted
                        else StrategyReviewStatus.REJECTED
                    ),
                    "reviewer_note": "系统草稿评分，仍待人工追溯检查。",
                }
            )
        )
    if scored_count < 3 or scored_weight < 0.5:
        raise ValueError("企业资料不足以支持至少三个、合计权重50%的公司评分维度")
    return artifact.model_copy(
        update={
            "dimensions": dimensions,
            "human_confirmed": True,
            "confirmed_at": datetime.now(UTC),
        }
    )


def _pipeline_action_plan(artifact: ActionPlanArtifact) -> ActionPlanArtifact:
    actions = [
        item.model_copy(
            update={
                "review_status": StrategyReviewStatus.ACCEPTED,
                "reviewer_note": "系统草稿行动，仍待人工追溯检查。",
            }
        )
        for item in artifact.actions
    ]
    if not actions:
        raise ValueError("未生成可供审阅式研究检查的Action Plan")
    return artifact.model_copy(
        update={
            "actions": actions,
            "human_confirmed": True,
            "confirmed_at": datetime.now(UTC),
        }
    )


def _set_generated_workflow_statuses(
    project: ProjectState,
    enterprise: bool,
) -> ProjectState:
    statuses = dict(project.workflow_status)
    for key in (
        "research_planning",
        "evidence_collection",
        "industry_analysis",
        "future_intelligence",
        "decision_report",
    ):
        statuses[key] = WorkflowStatus.COMPLETED
    statuses["evidence_qa"] = WorkflowStatus.NEEDS_REVIEW
    statuses["human_review"] = WorkflowStatus.NEEDS_REVIEW
    if enterprise:
        statuses["company_assessment"] = WorkflowStatus.COMPLETED
        statuses["action_plan"] = WorkflowStatus.COMPLETED
    else:
        statuses["company_assessment"] = WorkflowStatus.NOT_APPLICABLE
        statuses["action_plan"] = WorkflowStatus.NOT_APPLICABLE
    return project.model_copy(
        update={
            "workflow_status": statuses,
            "current_step": "decision_report",
            "updated_at": datetime.now(UTC),
        }
    )


def _report_requires_regeneration(markdown: str) -> bool:
    forbidden = (
        "证据缺口",
        "证据不足",
        "证据限制",
        "无直接证据支持",
        "缺乏直接数据",
        "无法量化",
        "无法测算",
        "本模块仅能覆盖",
        "evidence_gaps",
        "基于已批准材料",
        "基于已接受证据",
        "根据券商",
        "根据研报",
        "内容审阅环节",
    )
    return any(item in markdown for item in forbidden)
