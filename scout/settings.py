"""
Scout Settings
==============

Environment and runtime objects shared across agents.
"""

from agno.models.openai import OpenAIResponses

from db import get_postgres_db

agent_db = get_postgres_db()


def default_model() -> OpenAIResponses:
    """Fresh model instance per agent — avoids shared-state footguns."""
    return OpenAIResponses(id="gpt-5.6-sol")
