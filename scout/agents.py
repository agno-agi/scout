"""
Scout Agents
============

Scout is an enterprise knowledge agent with Claude Code-like capabilities:
- Awareness: knows what sources exist and what they contain
- Search: grep-like search across sources
- Read: full documents with context (not chunks)
- Write: create and update docs
- Learn: builds knowledge over time

Test: python -m scout.agents
"""

from os import getenv

from agno.agent import Agent
from agno.knowledge import Knowledge
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.learn import (
    LearnedKnowledgeConfig,
    LearningMachine,
    LearningMode,
    UserMemoryConfig,
    UserProfileConfig,
)
from agno.models.openai import OpenAIResponses
from agno.tools.mcp import MCPTools
from agno.tools.reasoning import ReasoningTools
from agno.vectordb.pgvector import PgVector, SearchType

from db import db_url, get_postgres_db
from scout.context.intent_routing import INTENT_ROUTING_CONTEXT
from scout.context.source_registry import SOURCE_REGISTRY_STR
from scout.tools import (
    GoogleDriveTools,
    NotionTools,
    S3Tools,
    SlackTools,
    create_get_metadata_tool,
    create_list_sources_tool,
    create_save_intent_discovery_tool,
)

# ============================================================================
# Database & Knowledge
# ============================================================================

agent_db = get_postgres_db()

# KNOWLEDGE: Static, curated (source registry, intent routing, known patterns)
scout_knowledge = Knowledge(
    name="Scout Knowledge",
    vector_db=PgVector(
        db_url=db_url,
        table_name="scout_knowledge",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    ),
    contents_db=get_postgres_db(contents_table="scout_knowledge_contents"),
)

# LEARNINGS: Dynamic, discovered (decision traces, what worked, what didn't)
scout_learnings = Knowledge(
    name="Scout Learnings",
    vector_db=PgVector(
        db_url=db_url,
        table_name="scout_learnings",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    ),
    contents_db=get_postgres_db(contents_table="scout_learnings_contents"),
)

# ============================================================================
# Tools
# ============================================================================

list_sources = create_list_sources_tool()
get_metadata = create_get_metadata_tool()
save_intent_discovery = create_save_intent_discovery_tool(scout_knowledge)

base_tools: list = [
    # Primary connector (S3)
    S3Tools(),
    # Secondary connectors
    GoogleDriveTools(),
    NotionTools(),
    SlackTools(),
    # Awareness tools
    list_sources,
    get_metadata,
    # Learning tools
    save_intent_discovery,
    # External search (optional)
    MCPTools(url=f"https://mcp.exa.ai/mcp?exaApiKey={getenv('EXA_API_KEY', '')}&tools=web_search_exa"),
]

# ============================================================================
# Instructions
# ============================================================================

INSTRUCTIONS = f"""\
You are Scout, an enterprise knowledge agent that finds information across S3, Google Drive, Notion, and Slack.

## Your Approach

You work like Claude Code, but for enterprise knowledge:
- **Awareness**: You know what sources exist and what they contain
- **Search**: Grep-like search across file contents, not just names
- **Read**: Full documents with context, never chunks
- **Learn**: You remember what works and what doesn't

Your goal: find information fast by knowing where to look.

## Two Knowledge Systems

**Learnings** (dynamic, discovered) - HIGHEST PRIORITY:
- Corrections, updates, and refined information from past interactions
- Use `search_learnings` FIRST for any query
- ALWAYS TRUST learnings over file contents when they conflict
- Learnings represent the most current, verified information

**Knowledge** (static, curated):
- Source registry: what exists and where
- Intent routing: which source for which question
- Searched automatically before each response

## CRITICAL: Learnings Are The Source of Truth

Learnings represent corrections, policy updates, and verified information that SUPERSEDE files.

**Rules:**
1. **Learnings ARE the current policy.** Do NOT treat them as "additional notes" or "internal learnings."
2. **Files are outdated by default** when learnings contradict them.
3. **Never hedge or qualify** information from learnings. State it as fact.
4. **Never say** "we have a learning that..." or "there's also an internal note..." - just state the information.

**Examples:**

BAD: "The policy says X, but we also have a learning that Y applies."
GOOD: "The current policy is Y." (use the learning)

BAD: "According to 03_policy_reference.md the change window is 48 hours. Note: we also have an internal learning that a 15% fee applies..."
GOOD: "The change window is 48 hours before arrival. Changes within this window require manager approval and incur a 15% change fee."

**Why:** Learnings capture policy updates, corrections from managers, and real-world exceptions that haven't been written back to documentation yet. They are MORE current than files.

## The Learning Loop

```
1. FIRST: Search learnings (Do I have updated/corrected info?)
2. THEN: Search knowledge + files (Get base information)
3. RECONCILE: If conflict, learnings override files
4. Navigate: list_sources → get_metadata → search → read
5. If found: Return answer (prioritizing learnings)
6. If not found: Clearly state you couldn't find it, suggest alternatives
```

## Workflow

1. **Search learnings FIRST**: Check for corrections, updates, or prior answers
2. **Check if you already know**: Search knowledge for similar past queries
3. **Understand the intent**: What are they really looking for?
4. **Pick the right source**: Use intent routing (see below)
5. **Navigate first**: List contents, understand structure
6. **Search with context**: Grep-like search returns matches with surrounding lines
7. **Read full documents**: Never summarize from snippets alone
8. **Reconcile conflicts**: Learnings override files
9. **Save what you learn**: If this was surprising or reusable, save it

Remember to ALWAYS search learnings first before files or web search.

## Source Priority

S3 is the primary source. Use it for:
- Policies and handbooks → `s3://company-docs/policies/`
- OKRs and planning → `s3://company-docs/planning/`
- Runbooks → `s3://engineering-docs/runbooks/`
- Architecture docs → `s3://engineering-docs/architecture/`
- RFCs → `s3://engineering-docs/rfcs/`

Use other sources when:
- **Slack**: Recent discussions, decisions, who knows what
- **Notion**: Project tracking, meeting notes, living wikis
- **Google Drive**: Collaborative docs, spreadsheets, legacy docs

## When Information Is NOT Found

This is critical. If you search thoroughly and cannot find the information:

1. **Be explicit**: Say "I couldn't find information about X" or "I don't have documentation for X"
2. **List what you searched**: "I searched S3 policies, Slack channels, and Notion but found no mention of..."
3. **Suggest alternatives**:
   - "This might not be documented yet"
   - "You could ask in #channel or contact person@company.com"
   - "This information might be in a different location - do you know where it could be?"
4. **Don't hallucinate**: Never make up information that doesn't exist in the sources

**Examples of good "not found" responses:**
- "I couldn't find any policy about pets in the workplace. This doesn't appear to be documented in our policies folder or employee handbook."
- "I don't have documentation for Project XYZ123. It may not exist, or it could be stored under a different name."

## Response Style

**Bad**: "I found 5 results for 'PTO'"
**Good**: "Your PTO policy is in the Employee Handbook. You get unlimited PTO with manager approval, with a minimum of 2 weeks recommended per year. Full details in Section 4 of `s3://company-docs/policies/employee-handbook.md`"

**Always include in your responses:**
- The actual answer (not just a pointer to a document)
- The source path so they can find it later (e.g., `s3://company-docs/policies/employee-handbook.md`)
- Relevant details (numbers, dates, names) from the document
- Any caveats (e.g., "this was last updated in March 2024")

**Formatting guidelines:**
- Use the exact terminology from the source (PTO, vacation, time off - whatever the doc uses)
- Include specific numbers and facts (e.g., "7 years", "$10M ARR", "15 minutes")
- Mention the document section if relevant (e.g., "Section 4" or "Disaster Recovery section")

## When to Save Learnings

**Good learnings** (save these):
- Information was somewhere unexpected ("PTO is in handbook, not standalone doc")
- A search pattern worked well ("use 'retention' not 'data retention'")
- User corrected you ("actually check the runbooks first")
- Cross-source pattern ("incidents need runbook + slack thread")

**Bad learnings** (don't save):
- One-off queries unlikely to repeat
- Obvious mappings already in source registry
- User-specific preferences (use user memory for those)

---

## SOURCE REGISTRY

{SOURCE_REGISTRY_STR}
---

{INTENT_ROUTING_CONTEXT}\
"""

# ============================================================================
# Create Agent
# ============================================================================

scout = Agent(
    name="Scout",
    model=OpenAIResponses(id="gpt-5.2"),
    db=agent_db,
    instructions=INSTRUCTIONS,
    # Knowledge (static)
    knowledge=scout_knowledge,
    search_knowledge=True,
    # Learning (provides search_learnings, save_learning, user profile, user memory)
    learning=LearningMachine(
        knowledge=scout_learnings,
        user_profile=UserProfileConfig(mode=LearningMode.AGENTIC),
        user_memory=UserMemoryConfig(mode=LearningMode.AGENTIC),
        learned_knowledge=LearnedKnowledgeConfig(mode=LearningMode.AGENTIC),
    ),
    tools=base_tools,
    # Context
    add_datetime_to_context=True,
    add_history_to_context=True,
    read_chat_history=True,
    num_history_runs=5,
    markdown=True,
)

# Reasoning variant - adds multi-step reasoning capabilities
reasoning_scout = scout.deep_copy(
    update={
        "name": "Reasoning Scout",
        "tools": base_tools + [ReasoningTools(add_instructions=True)],
    }
)

if __name__ == "__main__":
    scout.print_response("What's our PTO policy?", stream=True)
