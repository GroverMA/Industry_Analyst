from __future__ import annotations

from src.models.report import GeneralReportArtifact
from src.models.revision import RevisionTarget
from src.models.strategy import EnterpriseDecisionReportArtifact
from src.providers.base import ModelResponse
from src.services.reviewer_revision import (
    ReviewerRevisionService,
    finalize_revision,
    initialize_revision,
    save_report_version,
)
from src.services.report_generation import sanitize_formal_report
from src.state.project import ProjectState


LONG_REPORT = "# 中国IVD行业研究\n\n" + "中国体外诊断市场保持结构性发展，竞争格局持续演进。" * 35


class FakeModel:
    def complete_json(self, messages, *, enable_thinking=False):
        payload = {
            "assistant_analysis": "审阅意见要求重新突出竞争格局，并与原始研究目标重新对齐。",
            "recommendations": ["将国际龙头和国产头部企业分层比较"],
            "questions_for_reviewer": ["是否重点讨论化学发光子赛道？"],
            "proposed_markdown": LONG_REPORT.replace("持续演进", "加速分化"),
        }
        return payload, ModelResponse(content="{}")


def project(*, enterprise: bool = False) -> ProjectState:
    value = ProjectState(
        project_name="中国IVD行业",
        industry="体外诊断",
        region="中国",
        target_company="示例医疗" if enterprise else None,
        company_strategy_enabled=enterprise,
        company_strategy_objective="扩大化学发光业务" if enterprise else None,
        research_objective="研究市场规模、竞争格局和未来趋势",
        time_horizon="2026-2030",
        general_report_artifact=GeneralReportArtifact(title="中国IVD行业", markdown=LONG_REPORT),
    )
    if enterprise:
        value = value.model_copy(
            update={
                "enterprise_decision_report_artifact": EnterpriseDecisionReportArtifact(
                    title="企业决策报告",
                    general_report_id=value.general_report_artifact.report_id,
                    scorecard_id="SCORE-1",
                    action_plan_id="ACTION-1",
                    markdown=LONG_REPORT,
                )
            }
        )
    return value


def test_reviewer_can_repeat_ai_revision_and_accept_new_version() -> None:
    item = project()
    service = ReviewerRevisionService(FakeModel())
    artifact = service.analyze(
        item,
        "请加强竞争格局分析",
        [RevisionTarget.REPORT, RevisionTarget.INDUSTRY_ANALYSIS],
    )
    item = item.model_copy(update={"content_revision_artifact": artifact})
    item = save_report_version(
        item,
        artifact.turns[-1].proposed_markdown,
        source="ai_revision",
        accept_latest_turn=True,
    )

    assert item.content_revision_artifact.active_version == 2
    assert item.content_revision_artifact.turns[-1].accepted is True
    assert "加速分化" in item.general_report_artifact.markdown

    artifact = service.analyze(item, "再加强未来趋势", [RevisionTarget.FUTURE_INTELLIGENCE])
    assert len(artifact.turns) == 2


def test_enterprise_revision_updates_enterprise_report_and_can_finalize() -> None:
    item = project(enterprise=True)
    artifact = initialize_revision(item)
    item = item.model_copy(update={"content_revision_artifact": artifact})
    item = save_report_version(item, LONG_REPORT + "\n企业行动路径已经明确。", source="direct_edit")
    item = finalize_revision(item)

    assert item.enterprise_decision_report_artifact.markdown.endswith("企业行动路径已经明确。\n")
    assert item.content_revision_artifact.finalized is True


def test_revision_turn_can_preserve_trace_amendments() -> None:
    from src.models.revision import RevisionTurn

    turn = RevisionTurn(
        reviewer_message="重新解释国产替代节奏",
        targets=[RevisionTarget.INDUSTRY_ANALYSIS],
        assistant_analysis="需要区分产品层与企业层。",
        trace_amendments={"industry_analysis": "改为按产品层、客户层和企业层分别判断。"},
        proposed_markdown=LONG_REPORT,
    )

    assert "产品层" in turn.trace_amendments["industry_analysis"]


def test_formal_report_sanitizer_keeps_internal_review_language_out_of_deliverable() -> None:
    draft = """# 中国IVD行业研究

根据券商预测，中国IVD整体市场规模为1,200亿元。EVD-123 · data。

本章节仍存在证据限制。无直接证据支持完整赛道分类体系。

当前模块由结构修复生成，需要Reviewer审阅环节重点核对。

由于缺少官方连续历史序列及Tier1数据源，多数市场数字基于券商与公司公告推算，置信度中等偏低。

下游系统集成环节因无公开证据未纳入分析。

中国IVD行业将保持结构性增长。
"""

    cleaned = sanitize_formal_report(draft)

    assert "EVD-123" not in cleaned
    assert "根据券商" not in cleaned
    assert "证据限制" not in cleaned
    assert "结构修复" not in cleaned
    assert "Reviewer" not in cleaned
    assert "Tier1" not in cleaned
    assert "置信度" not in cleaned
    assert "未纳入分析" not in cleaned
    assert "中国IVD行业将保持结构性增长" in cleaned
