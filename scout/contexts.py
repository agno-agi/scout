"""
Scout's Context Registry
========================

Wiring for the contexts available to Scout. Web and filesystem are always on;
Slack and Google Drive light up when their env vars are set.
"""

from __future__ import annotations

import asyncio
import json
from os import getenv
from pathlib import Path

from agno.context.database import DatabaseContextProvider
from agno.context.gdrive import GDriveContextProvider
from agno.context.mcp import MCPContextProvider
from agno.context.provider import ContextProvider
from agno.context.slack import SlackContextProvider
from agno.context.web.parallel import ParallelBackend
from agno.context.web.parallel_mcp import ParallelMCPBackend
from agno.context.web.provider import WebContextProvider
from agno.context.wiki import FileSystemBackend, GitBackend, WikiContextProvider
from agno.context.workspace import WorkspaceContextProvider
from agno.run import RunContext
from agno.tools import tool
from agno.utils.log import log_info, log_warning

from db import SCOUT_SCHEMA, get_readonly_engine, get_sql_engine
from scout.instructions import SCOUT_CRM_READ, SCOUT_CRM_WRITE
from scout.settings import default_model

# Workspace root for the always-on filesystem context. Hardcoded to the
# scout repo so Scout can answer questions about its own codebase out of
# the box. Forks/private deployments can re-point this to their own repo.
SCOUT_FS_ROOT = Path(__file__).resolve().parents[1]

# Wiki roots — knowledge is the prose memory Scout files into; voice is the
# code-managed style guide read-only. Knowledge is filesystem-backed by
# default; set WIKI_REPO_URL + WIKI_GITHUB_TOKEN to switch to GitBackend
# at startup (see `docs/WIKI_GIT.md`). Voice is always filesystem-backed.
WIKI_KNOWLEDGE_PATH = SCOUT_FS_ROOT / "wiki" / "knowledge"
WIKI_VOICE_PATH = SCOUT_FS_ROOT / "wiki" / "voice"


# ---------------------------------------------------------------------------
# Create Context Providers
# ---------------------------------------------------------------------------


context_providers: list[ContextProvider] = []


def create_context_providers() -> list[ContextProvider]:
    """Build the registered context providers from env and cache them for the process.

    Optional builders are wrapped in try/except so one bad config doesn't take
    the whole registry down. Duplicate `id`s are dropped with a warning
    (first one wins) so Scout never ends up with two `query_<id>` tools
    sharing a name.
    """
    configured_providers: list[ContextProvider] = [
        _create_web_provider(),
        _create_workspace_provider(),
        _create_database_provider(),
        _create_knowledge_wiki(),
        _create_voice_wiki(),
    ]
    for factory in (_create_slack_provider, _create_gdrive_provider):
        try:
            provider = factory()
        except Exception as exc:
            log_warning(f"{factory.__name__} failed: {exc}")
            continue
        if provider is not None:
            configured_providers.append(provider)
    configured_providers.extend(_create_mcp_providers())

    seen: set[str] = set()
    deduped: list[ContextProvider] = []
    for registered in configured_providers:
        if registered.id in seen:
            log_warning(
                f"context id {registered.id!r} already registered; skipping duplicate ({type(registered).__name__})"
            )
            continue
        seen.add(registered.id)
        deduped.append(registered)

    context_providers[:] = deduped
    _log_context_providers(deduped)
    return list(context_providers)


def _log_context_providers(ctxs: list[ContextProvider]) -> None:
    """Log the resolved provider set with each provider's status detail."""
    if not ctxs:
        log_info("Context Providers: (none)")
        return
    width = max(len(c.id) for c in ctxs)
    lines = ["Context Providers:"]
    for c in ctxs:
        try:
            detail = c.status().detail
        except Exception as exc:
            detail = f"<status failed: {type(exc).__name__}>"
        lines.append(f"  {c.id:<{width}}  {detail}")
    log_info("\n".join(lines))


def get_context_providers() -> list[ContextProvider]:
    """Return the cached provider list, building on first access."""
    if not context_providers:
        create_context_providers()
    return list(context_providers)


def update_context_providers(new_providers: list[ContextProvider]) -> None:
    """Swap the cached provider list in place. Used by eval fixtures."""
    context_providers[:] = new_providers


async def close_context_providers() -> None:
    """Release resources held by every cached provider.

    Providers that hold resources (MCP sessions, watch streams) override
    `aclose()`; the base class default is a no-op. `return_exceptions=True`
    so one stuck teardown can't block others on the way down.
    """
    # Close only what's already cached — don't lazily build during teardown.
    providers = list(context_providers)
    if not providers:
        return
    results = await asyncio.gather(
        *(p.aclose() for p in providers),
        return_exceptions=True,
    )
    for provider, outcome in zip(providers, results, strict=True):
        if isinstance(outcome, BaseException):
            log_warning(f"context {provider.id!r} aclose raised {type(outcome).__name__}: {outcome}")


async def setup_context_providers() -> list[ContextProvider]:
    """Initialize providers — build the registry (if not already built)
    and run async setup on each.

    Returns the ready-to-use provider list.
    """
    providers = get_context_providers()
    if not providers:
        return providers
    results = await asyncio.gather(
        *(p.asetup() for p in providers),
        return_exceptions=True,
    )
    for provider, outcome in zip(providers, results, strict=True):
        if isinstance(outcome, BaseException):
            log_warning(f"context {provider.id!r} asetup raised {type(outcome).__name__}: {outcome}")
    return providers


def _create_web_provider() -> WebContextProvider:
    model = default_model()
    if getenv("PARALLEL_API_KEY"):
        return WebContextProvider(backend=ParallelBackend(), model=model)
    return WebContextProvider(backend=ParallelMCPBackend(), model=model)


def _create_workspace_provider() -> WorkspaceContextProvider:
    return WorkspaceContextProvider(root=SCOUT_FS_ROOT, model=default_model())


def _create_knowledge_wiki() -> WikiContextProvider:
    """The company knowledge wiki — read + write, prose pages.

    Filesystem-backed by default. Set ``WIKI_REPO_URL`` AND
    ``WIKI_GITHUB_TOKEN`` to switch to ``GitBackend`` for durable storage
    with an audit trail (see ``docs/WIKI_GIT.md``). Optional knobs:
    ``WIKI_BRANCH`` (default ``main``), ``WIKI_LOCAL_PATH``.
    """
    repo_url = getenv("WIKI_REPO_URL", "").strip()
    github_token = getenv("WIKI_GITHUB_TOKEN", "").strip()

    backend: FileSystemBackend | GitBackend
    if repo_url and github_token:
        backend = GitBackend(
            repo_url=repo_url,
            github_token=github_token,
            branch=getenv("WIKI_BRANCH", "main"),
            local_path=getenv("WIKI_LOCAL_PATH") or None,
        )
        log_info(f"Knowledge wiki: GitBackend ({repo_url})")
    else:
        if repo_url or github_token:
            log_warning(
                "Knowledge wiki: WIKI_REPO_URL and WIKI_GITHUB_TOKEN must both be set "
                "to enable GitBackend; falling back to FileSystemBackend."
            )
        WIKI_KNOWLEDGE_PATH.mkdir(parents=True, exist_ok=True)
        backend = FileSystemBackend(path=WIKI_KNOWLEDGE_PATH)

    return WikiContextProvider(
        id="knowledge",
        name="Company Knowledge",
        backend=backend,
        model=default_model(),
    )


def _create_voice_wiki() -> WikiContextProvider:
    """The company voice guide — read-only, code-managed.

    Voice rules are committed to the repo and changed via PR, not by the
    agent. ``write=False`` removes the ``update_voice`` tool from Scout.
    """
    return WikiContextProvider(
        id="voice",
        name="Company Voice",
        backend=FileSystemBackend(path=WIKI_VOICE_PATH),
        write=False,
        model=default_model(),
    )


def _create_database_provider() -> DatabaseContextProvider:
    return DatabaseContextProvider(
        id="crm",
        name="CRM",
        sql_engine=get_sql_engine(),
        readonly_engine=get_readonly_engine(),
        schema=SCOUT_SCHEMA,
        read_instructions=SCOUT_CRM_READ,
        write_instructions=SCOUT_CRM_WRITE,
        model=default_model(),
    )


def _create_slack_provider() -> SlackContextProvider | None:
    if not getenv("SLACK_BOT_TOKEN"):
        return None
    return SlackContextProvider(model=default_model())


def _create_gdrive_provider() -> GDriveContextProvider | None:
    if not getenv("GOOGLE_SERVICE_ACCOUNT_FILE"):
        return None
    return GDriveContextProvider(model=default_model())


def _create_mcp_providers() -> list[MCPContextProvider]:
    """Registered MCP servers.

    Add a ``MCPContextProvider(...)`` entry per server. Pull secrets
    from env via ``getenv(...)`` inside the constructor call. See
    ``docs/MCP_CONNECT.md``.
    """
    return []


def context_providers_summary() -> str:
    """Markdown summary of registered providers, for prompt interpolation.

    Wired as a callable on `Agent.dependencies["context_providers"]` so
    agno re-resolves it per run — picks up provider swaps from eval
    fixtures without Scout holding a stale snapshot.
    """
    providers = get_context_providers()
    if not providers:
        return "(no context providers registered)"
    return "\n".join(f"- `{p.id}`: {p.name}" for p in providers)


def status_row(ctx: ContextProvider) -> dict:
    """Row-shape summary of one context's current status."""
    try:
        s = ctx.status()
        return {"id": ctx.id, "name": ctx.name, "ok": s.ok, "detail": s.detail}
    except Exception as exc:
        return {"id": ctx.id, "name": ctx.name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


async def astatus_row(ctx: ContextProvider) -> dict:
    """Async variant of ``status_row``."""
    try:
        s = await ctx.astatus()
        return {"id": ctx.id, "name": ctx.name, "ok": s.ok, "detail": s.detail}
    except Exception as exc:
        return {"id": ctx.id, "name": ctx.name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


@tool
async def list_contexts(run_context: RunContext | None = None) -> str:
    """List registered contexts with current status.

    Returns:
        JSON list of ``{id, name, ok, detail}``.
    """
    rows = [await astatus_row(ctx) for ctx in get_context_providers()]
    return json.dumps(rows)
