"""
Scout Teams
===========

Team-based orchestration for Scout agents.

The Scout Team combines:
- Coordinator: Triages requests and synthesizes structured responses
- Scout: Enterprise knowledge agent that searches across sources

Test: python -m scout.teams
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from agno.models.openai import OpenAIResponses
from agno.team import Team

from db import get_postgres_db
from scout.agents import scout

# ============================================================================
# Response Models
# ============================================================================


class TriageResponse(BaseModel):
    """Structured response for request triage."""

    category: str = Field(
        ...,
        description="Category of the request (e.g., 'policy_question', 'technical_support', 'hr_request', 'general_inquiry')",
    )
    department: str = Field(
        ...,
        description="Department responsible for handling this request (e.g., 'HR', 'Engineering', 'IT', 'Finance', 'Legal')",
    )
    priority: Literal["low", "medium", "high", "urgent"] = Field(
        ...,
        description="Priority level based on urgency and impact",
    )
    summary: str = Field(
        ...,
        description="Brief summary of the request in 1-2 sentences",
    )
    action_type: Literal["answer", "escalate", "redirect", "clarify"] = Field(
        ...,
        description="Recommended action: answer directly, escalate to human, redirect to another team, or request clarification",
    )
    deadline: Optional[str] = Field(
        default=None,
        description="Deadline if mentioned or implied (ISO 8601 format or natural language)",
    )
    requires_human_review: bool = Field(
        ...,
        description="Whether this request requires human review before responding",
    )
    review_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why human review is needed: missing documentation, policy not found, sensitive topic, needs approval, etc.",
    )
    ai_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score as decimal between 0.0 and 1.0",
    )
    missing_info: list[str] = Field(
        default_factory=list,
        description="Specific information that could not be found in knowledge sources (e.g., 'PTO policy document', 'approval workflow')",
    )
    assigned_team: Optional[str] = Field(
        default=None,
        description="Specific team or person to assign this request to",
    )
    draft_response: str = Field(
        ...,
        description="Draft response TO THE END USER. Include all information found. Use [NEEDS COMPLETION: ...] placeholders for gaps the admin must fill in before sending. Do not mention internal systems.",
    )


# ============================================================================
# Database
# ============================================================================

team_db = get_postgres_db()

# ============================================================================
# Team Instructions
# ============================================================================

TEAM_INSTRUCTIONS = [
    # Role
    "You are a request triage coordinator. You help admin users respond to employee requests by drafting responses they can review, complete, and send.",
    # Information gathering strategy
    "Query Scout multiple times to build a complete picture. Do NOT settle for a single query.",
    "Start with the primary question, then follow up on: edge cases, exceptions, related policies, escalation procedures, and who to contact.",
    "If Scout cannot find information after 2-3 different search approaches, note this in missing_info and move on.",
    # Example query sequence
    "Example for PTO: 1) What is our PTO policy? 2) What is the process for requesting time off? 3) Are there blackout dates? 4) Who approves and what's the lead time?",
    # Categories
    "Categories: policy_question (PTO, benefits, conduct), technical_support (systems/tools), hr_request (onboarding, payroll, leave), general_inquiry, compliance (legal, regulatory), finance (budget, expenses).",
    # Priority
    "Priority: urgent (immediate impact, security, time-sensitive), high (affects multiple people), medium (standard requests), low (non-urgent info).",
    # Action types
    "Action types: answer (have info), escalate (needs human approval), redirect (different team), clarify (need more info).",
    # Human review triggers
    "Flag for human review when: sensitive topics (termination, legal, personal data), policy exceptions, low AI confidence, ambiguous requests, financial decisions, external communications.",
    # CRITICAL: Draft response guidelines
    "CRITICAL: draft_response is written TO THE END USER. The admin will review and complete it before sending.",
    "NEVER apologize for not finding information. NEVER tell the user to contact HR or another department. NEVER say you couldn't access something.",
    "ALWAYS write a complete, professional response structure. Use [NEEDS COMPLETION: description] for ANY information you don't have.",
    "Do NOT mention internal systems (S3, Notion, Google Drive, Slack) to the user.",
    # Example draft response
    "Example draft for PTO question: 'Hi John,\\n\\nThank you for reaching out about your time off request.\\n\\nOur PTO policy provides [NEEDS COMPLETION: PTO allowance details]. To request time off, [NEEDS COMPLETION: request process].\\n\\nFor your family event next month, please [NEEDS COMPLETION: specific instructions].\\n\\nLet me know if you have any questions.\\n\\nBest regards'",
    # Admin-facing fields
    "review_reasons is for the ADMIN explaining what needs to be filled in (e.g., 'PTO policy details not found - please add current policy information').",
    "missing_info lists specific gaps (e.g., 'PTO allowance', 'request process', 'approval workflow').",
    "Set requires_human_review=true whenever there are [NEEDS COMPLETION: ...] placeholders.",
]

# ============================================================================
# Scout Team
# ============================================================================

scout_team = Team(
    name="Scout Team",
    model=OpenAIResponses(id="gpt-5.2"),
    members=[scout],
    instructions=TEAM_INSTRUCTIONS,
    output_schema=TriageResponse,
    db=team_db,
    markdown=True,
    show_members_responses=True,
)



if __name__ == "__main__":
    # Example triage request
    request = """
    ID: REQ-001
    Channel: #help-desk
    From: John Smith
    Message: What's our PTO policy? I need to take some time off next month for a family event.
    """
    scout_team.print_response(request, stream=True)


