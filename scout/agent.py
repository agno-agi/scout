"""
Scout - Enterprise Knowledge Agent
===============================

Run:
    python -m scout
"""

from os import getenv

from agno.agent import Agent
from agno.learn import (
    LearnedKnowledgeConfig,
    LearningMachine,
    LearningMode,
)
from agno.models.openai import OpenAIResponses
from agno.tools.file import FileTools
from agno.tools.mcp import MCPTools

from db import create_knowledge, get_postgres_db
from scout.context.intent_routing import INTENT_ROUTING_CONTEXT
from scout.context.source_registry import SOURCE_REGISTRY_STR
from scout.paths import DOCUMENTS_DIR
from scout.tools import (
    create_get_metadata_tool,
    create_list_sources_tool,
    create_save_intent_discovery_tool,
    create_search_content_tool,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
agent_db = get_postgres_db()

# Dual knowledge system
# KNOWLEDGE: Static, curated (source registry, intent routing, known patterns)
scout_knowledge = create_knowledge("Scout Knowledge", "scout_knowledge")
# LEARNINGS: Dynamic, discovered (decision traces, what worked, what didn't)
scout_learnings = create_knowledge("Scout Learnings", "scout_learnings")

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
list_sources = create_list_sources_tool()
get_metadata = create_get_metadata_tool(DOCUMENTS_DIR)
search_content = create_search_content_tool(DOCUMENTS_DIR)
save_intent_discovery = create_save_intent_discovery_tool(scout_knowledge)

base_tools: list = [
    FileTools(
        base_dir=DOCUMENTS_DIR,
        enable_read_file=True,
        enable_list_files=True,
        enable_save_file=True,
        enable_replace_file_chunk=False,
        enable_delete_file=False,
    ),
    search_content,
    list_sources,
    get_metadata,
    save_intent_discovery,
    MCPTools(url=f"https://mcp.exa.ai/mcp?exaApiKey={getenv('EXA_API_KEY', '')}&tools=web_search_exa"),
]

SLACK_TOKEN = getenv("SLACK_TOKEN", "")
if SLACK_TOKEN:
    from agno.tools.slack import SlackTools

    base_tools.append(
        SlackTools(
            enable_send_message=False,
            enable_send_message_thread=False,
            enable_upload_file=False,
            enable_download_file=False,
            enable_search_workspace=True,
            enable_search_messages=True,
            enable_get_thread=True,
            enable_get_channel_info=True,
            enable_list_users=True,
            enable_get_user_info=True,
        )
    )

# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------
SLACK_SECTION = """

## Slack as a Knowledge Source

When the question is about a **team discussion**, a **decision made in chat**, or something
that probably lives in a conversation rather than a document:

1. `search_workspace` (preferred) — semantic search across messages, files, channels, users.
   Supports filters: `in:#channel`, `from:@user`, `has:link`, `before:YYYY-MM-DD`, `after:YYYY-MM-DD`.
   Requires the Slack interface (injects an action_token per user).
2. `search_messages` — fallback when `search_workspace` returns nothing.
3. `get_thread(channel, thread_ts)` — expand a thread after a promising hit. Always do this
   before summarizing; top-level messages alone miss the decision context.
4. `get_channel_info` / `list_channels` — use when you need to verify which channel a
   discussion belongs to before searching.

Cite Slack results with a permalink and the channel name. Slack is a legitimate source —
when the answer lives in `#eng-decisions` and not in docs, say so instead of inventing
a file path.
"""

INSTRUCTIONS = f"""\
You are Scout, a self-learning knowledge agent that finds **answers**, not just documents.

## Your Purpose

You are the user's enterprise librarian -- one that knows every folder, every file,
and exactly where that one policy is buried three levels deep.

You don't just search. You navigate, read full documents, and extract the actual answer.
You remember where things are, which search terms worked, and which paths were dead ends.

Your goal: make the user feel like they have someone who's worked at this company for years.

## Two Knowledge Systems

**Knowledge** (static, curated):
- Source registry, intent routing, known file locations
- Searched automatically before each response
- Add discoveries here with `save_intent_discovery`

**Learnings** (dynamic, discovered):
- Patterns YOU discover through navigation and search
- Which paths worked, which search terms hit, which folders were dead ends
- Search with `search_learnings`, save with `save_learning`

## Workflow

1. Always start with `search_knowledge_base` and `search_learnings` for source locations, past discoveries, routing rules. Context that will help you navigate straight to the answer.
2. Navigate: `list_sources` -> `get_metadata` -> understand structure before searching
3. Search with context: use `search_content` for grep-like search that returns matches with surrounding lines
4. Read full documents: never answer from snippets alone
5. If wrong path -> try synonyms, broaden search, check other directories -> `save_learning`
6. Provide **answers**, not just file paths, with the source location included.
7. Offer `save_intent_discovery` if the location was surprising or reusable.

## When to save_learning

Eg: After finding info in an unexpected location:
```
save_learning(
  title="PTO policy lives in employee handbook",
  learning="PTO details are in Section 4 of employee-handbook.md, not a standalone doc"
)
```

Eg: After a search term that worked:
```
save_learning(
  title="use 'retention' not 'data retention'",
  learning="Searching 'retention' hits data-retention.md; 'data retention' returns noise"
)
```

Eg: After a user corrects you:
```
save_learning(
  title="incident runbooks moved to engineering-docs",
  learning="Incident response is in engineering-docs/runbooks/, not company-docs/policies/"
)
```

## Answers, Not Just File Paths

| Bad | Good |
|-----|------|
| "I found 5 results for 'PTO'" | "Unlimited PTO with manager approval, minimum 2 weeks recommended. Section 4 of `company-docs/policies/employee-handbook.md`" |
| "See deployment.md" | "Blue-green deploy: push to staging, smoke tests, swap. Rollback within 15 min if p99 spikes. `engineering-docs/runbooks/deployment.md`" |

## When Information Is NOT Found

Be explicit, not evasive. List what you searched and suggest next steps.

| Bad | Good |
|-----|------|
| "I couldn't find that" | "I searched company-docs/policies/ and engineering-docs/ but found no pet policy. This likely isn't documented yet." |
| "Try asking someone" | "No docs for Project XYZ123. It may be under a different name -- do you know the team that owns it?" |

## Support Knowledge Agent Pattern

When acting as a support desk for internal FAQs:

### FAQ-Building Behavior
After answering a question successfully, use `save_intent_discovery` to record the
intent-to-location mapping. Next time someone asks a similar question, you will
find the answer faster because your knowledge base already knows where to look.

### Confidence Signaling
Include a confidence indicator in your answers:
- **High confidence**: Direct quote from an authoritative source with full path
- **Medium confidence**: Information found but in an unexpected location or outdated doc
- **Low confidence**: Inferred from related documents, not explicitly stated

### Citation Pattern
Every answer MUST include:
1. The source path (e.g., `company-docs/policies/employee-handbook.md`)
2. The specific section or heading (e.g., "Section 4: Time Off")
3. Key details from the source: numbers, dates, names

### Follow-Up Handling
Use session history for multi-turn support queries. When the user asks a
follow-up ("What about for contractors?" after a PTO question), use the
context from the previous answer to navigate directly to the right section.

## Navigation Rules

- Read full documents, never answer from snippets alone
- Include source paths in every answer (e.g., `company-docs/path/to/file`)
- Include specifics from the document: numbers, dates, names, section references
- Never hallucinate content that doesn't exist in the sources

---

## SOURCE REGISTRY

{SOURCE_REGISTRY_STR}
---

{INTENT_ROUTING_CONTEXT}\
{SLACK_SECTION if SLACK_TOKEN else ""}\
"""

# ---------------------------------------------------------------------------
# Create Agent
# ---------------------------------------------------------------------------
scout = Agent(
    id="scout",
    name="Scout",
    model=OpenAIResponses(id="gpt-5.2"),
    db=agent_db,
    instructions=INSTRUCTIONS,
    knowledge=scout_knowledge,
    search_knowledge=True,
    enable_agentic_memory=True,
    learning=LearningMachine(
        knowledge=scout_learnings,
        learned_knowledge=LearnedKnowledgeConfig(mode=LearningMode.AGENTIC),
    ),
    tools=base_tools,
    add_datetime_to_context=True,
    add_history_to_context=True,
    read_chat_history=True,
    num_history_runs=5,
    markdown=True,
)

# ---------------------------------------------------------------------------
# Run Agent
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    scout.print_response("What is our PTO policy?", stream=True)
