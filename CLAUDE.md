# CLAUDE.md

## Project Overview

Scout is an **enterprise knowledge agent** with Claude Code-like capabilities. It finds information across a local documents directory — and learns from every interaction.

- **Awareness** — Knows what sources exist and what they contain
- **Search** — Grep-like search across file contents, not just names
- **Read** — Full documents with context, never chunks
- **Learn** — Builds knowledge over time

## Structure

```
scout/
├── __init__.py               # Exports: scout, scout_knowledge, scout_learnings
├── __main__.py               # CLI entry (python -m scout)
├── agent.py                  # Scout agent definition
├── paths.py                  # Path resolution (DOCUMENTS_DIR, knowledge dirs)
├── context/
│   ├── source_registry.py    # Source metadata for system prompt
│   └── intent_routing.py     # Intent-to-location routing
├── tools/
│   ├── awareness.py          # list_sources, get_metadata
│   ├── search.py             # search_content (grep-like)
│   └── save_discovery.py     # Save successful discoveries
├── evals/
│   ├── test_cases.py         # Test cases with expected strings
│   ├── grader.py             # LLM-based response grading
│   └── run_evals.py          # Evaluation runner with rich output
├── knowledge/
│   ├── sources/files.json    # Source registry metadata
│   ├── routing/intents.json  # Intent routing rules
│   └── patterns/common_patterns.md
└── scripts/
    └── load_knowledge.py     # Load knowledge into vector DB

documents/                    # Enterprise documents (sample data)
├── company-docs/             # Policies, HR, planning
├── engineering-docs/         # Runbooks, architecture
└── data-exports/             # Reports, metrics

app/
├── main.py                   # API entry point (AgentOS)
└── config.yaml               # Agent configuration

db/
├── session.py                # get_postgres_db(), create_knowledge()
└── url.py                    # Database URL builder
```

## Commands

```bash
./scripts/venv_setup.sh && source .venv/bin/activate
./scripts/format.sh      # Format code
./scripts/validate.sh    # Lint + type check
python -m scout          # CLI mode

# Knowledge
python -m scout.scripts.load_knowledge              # Load knowledge into vector DB
python -m scout.scripts.load_knowledge --recreate    # Drop & reload

# Evaluations
python -m scout.evals.run_evals                     # String matching (default)
python -m scout.evals.run_evals --category policy   # Filter by category
python -m scout.evals.run_evals --llm-grader        # LLM-based grading
python -m scout.evals.run_evals --verbose           # Show responses on failure
python -m scout.evals.run_evals --check-sources      # Source citation affects pass/fail
python -m scout.evals.run_evals -g -s -v             # All modes combined
```

## Two Knowledge Systems

| System | What It Stores | How It Evolves |
|--------|---------------|----------------|
| **Knowledge** | Source registry, intent routing, known patterns | Curated by you + Scout |
| **Learnings** | Decision traces: what worked, what didn't, why | Managed by Learning Machine |

## The Learning Loop

```
User Question
     ↓
Search Knowledge + Learnings (Do I already know where this is?)
     ↓
Navigate: list_sources → get_metadata → search → read
     ↓
Found? → Return answer, save discovery if surprising
Not found? → Try fallback paths, save negative knowledge
```

## Tools

| Tool | Source | Purpose |
|------|--------|---------|
| `FileTools` | agno built-in | Read/list files in documents directory |
| `search_content` | scout/tools/search.py | Grep-like content search across files |
| `list_sources` | scout/tools/awareness.py | List available sources with details |
| `get_metadata` | scout/tools/awareness.py | Get file/directory metadata |
| `save_intent_discovery` | scout/tools/save_discovery.py | Save findings to knowledge base |
| `MCPTools` (Exa) | Optional (EXA_API_KEY) | Web search fallback |
| `SlackTools` | Optional (SLACK_TOKEN) | Slack as a knowledge source — `search_workspace`, `get_thread`, `get_channel_history`, channel/user lookups |

## Key Files to Reference

- `scout/agent.py` — Agent configuration and instructions
- `scout/paths.py` — Path resolution for documents and knowledge
- `scout/tools/search.py` — Content search implementation
- `scout/context/source_registry.py` — Context loading pattern
- `scout/knowledge/sources/files.json` — Source registry metadata
- `scout/knowledge/routing/intents.json` — Intent routing rules

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `EXA_API_KEY` | No | Exa for web research |
| `DOCUMENTS_DIR` | No | Documents directory (default: `./documents`, `/documents` in Docker) |
| `DB_HOST` | No | Database host (default: localhost) |
| `DB_PORT` | No | Database port (default: 5432) |
| `DB_USER` | No | Database user (default: ai) |
| `DB_PASS` | No | Database password (default: ai) |
| `DB_DATABASE` | No | Database name (default: ai) |
| `SLACK_TOKEN` | No | Slack bot token — enables SlackTools (search + retrieve) as a knowledge source |
| `SLACK_SIGNING_SECRET` | No | Required alongside `SLACK_TOKEN` to mount the Slack AgentOS interface |

## Conventions

### Agent Pattern

```python
from agno.agent import Agent
from agno.models.openai import OpenAIResponses
from db import get_postgres_db

agent_db = get_postgres_db()

my_agent = Agent(
    id="my-agent",
    name="My Agent",
    model=OpenAIResponses(id="gpt-5.2"),
    db=agent_db,
    instructions="...",
    add_datetime_to_context=True,
    add_history_to_context=True,
    read_chat_history=True,
    num_history_runs=5,
    markdown=True,
)
```

### Database

- Use `get_postgres_db()` from `db` module
- Use `create_knowledge()` for Knowledge bases with PgVector hybrid search
- Knowledge bases use `text-embedding-3-small` embedder

### Imports

```python
from db import db_url, get_postgres_db, create_knowledge
from scout import scout, scout_knowledge, scout_learnings
from scout.paths import DOCUMENTS_DIR
```
