"""Page renderer registry."""

from .action_plan import render as render_action_plan
from .company_scorecard import render as render_company_scorecard
from .decision_report import render as render_decision_report
from .enterprise_sensing import render as render_enterprise_sensing
from .evidence_analysis import render as render_evidence_analysis
from .home import render as render_home
from .research_brief import render as render_research_brief
from .research_studio import render as render_research_studio
from .trend_forecast import render as render_trend_forecast
from .workflow import render as render_workflow

PAGE_RENDERERS = {
    "home": render_home,
    "research_studio": render_research_studio,
    "research_brief": render_research_brief,
    "workflow": render_workflow,
    "enterprise_sensing": render_enterprise_sensing,
    "evidence_analysis": render_evidence_analysis,
    "trend_forecast": render_trend_forecast,
    "company_scorecard": render_company_scorecard,
    "action_plan": render_action_plan,
    "decision_report": render_decision_report,
}

__all__ = ["PAGE_RENDERERS"]
