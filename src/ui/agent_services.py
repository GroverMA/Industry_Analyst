"""Construct UI-facing agent services from secure runtime configuration."""

from __future__ import annotations

import streamlit as st

from src.config import Settings
from src.knowledge.sop import load_active_sop
from src.providers.hkgai_mcp import HKGAIMCPProvider
from src.providers.hkgai_model import HKGAIModelProvider
from src.providers.hkgai_structured_rest import HKGAIStructuredRestProvider
from src.providers.search_router import SearchRouter
from src.services.evidence_collection import EvidenceCollectionService
from src.services.action_planning import ActionPlanningService
from src.services.company_assessment import CompanyAssessmentService
from src.services.future_intelligence import FutureIntelligenceService
from src.services.industry_analysis import IndustryAnalysisService
from src.services.research_planning import ResearchPlanningService
from src.services.report_generation import ReportGenerationService
from src.services.reviewer_orchestration import ReviewerOrchestrationService


def research_planning_service() -> ResearchPlanningService:
    settings = Settings.load()
    return ResearchPlanningService(
        model=HKGAIModelProvider(settings),
        sop=load_active_sop(),
    )


EVIDENCE_SERVICE_CACHE_VERSION = "reviewer-report-first-v1"


@st.cache_resource(show_spinner=False)
def _cached_evidence_collection_service(
    cache_version: str,
) -> EvidenceCollectionService:
    """Keep the router health state and crawl cache for the active app process."""

    settings = Settings.load()
    router = SearchRouter(
        HKGAIMCPProvider(settings),
        HKGAIStructuredRestProvider(settings),
        mode=settings.search_transport,
    )
    return EvidenceCollectionService(
        model=HKGAIModelProvider(settings),
        search=router,
    )


def evidence_collection_service() -> EvidenceCollectionService:
    """Return a versioned service so Streamlit never reuses pre-hotfix code."""

    return _cached_evidence_collection_service(EVIDENCE_SERVICE_CACHE_VERSION)


def industry_analysis_service() -> IndustryAnalysisService:
    settings = Settings.load()
    return IndustryAnalysisService(
        model=HKGAIModelProvider(settings),
        sop=load_active_sop(),
    )


def future_intelligence_service() -> FutureIntelligenceService:
    settings = Settings.load()
    return FutureIntelligenceService(
        model=HKGAIModelProvider(settings),
        sop=load_active_sop(),
    )


def report_generation_service() -> ReportGenerationService:
    settings = Settings.load()
    return ReportGenerationService(model=HKGAIModelProvider(settings))


def company_assessment_service() -> CompanyAssessmentService:
    settings = Settings.load()
    return CompanyAssessmentService(
        model=HKGAIModelProvider(settings),
        sop=load_active_sop(),
    )


def action_planning_service() -> ActionPlanningService:
    settings = Settings.load()
    return ActionPlanningService(
        model=HKGAIModelProvider(settings),
        sop=load_active_sop(),
    )


def reviewer_orchestration_service() -> ReviewerOrchestrationService:
    """Build the report-first Reviewer pipeline from the same production services.

    The orchestration layer uses temporary approved copies only while satisfying
    downstream service contracts.  Returned artifacts remain pending review.
    """

    return ReviewerOrchestrationService(
        planning=research_planning_service(),
        evidence=evidence_collection_service(),
        industry=industry_analysis_service(),
        future=future_intelligence_service(),
        report=report_generation_service(),
        company=company_assessment_service(),
        action=action_planning_service(),
    )
