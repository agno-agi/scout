"""Evaluate structural wiring.

Checks:
    W1  Scout has every provider's tools + `list_contexts`; no bare `SQLTools`.
    W2  `DatabaseContextProvider` exposes `query_crm` AND `update_crm`.
    W3  Schema guard rejects DDL/DML targeting `public`/`ai` on the scout engine.
    W4  Every registered `ContextProvider` has the expected shape.
    W5  GDrive provider uses `ScoutGoogleDriveTools`, not bare `GoogleDriveTools`.
    W6  `MCPContextProvider` implements the lifecycle interface cleanly.
    W7  Readonly engine rejects writes at the DB level (belt for `default_transaction_read_only`).
    W8  Slack provider's SlackTools has send/upload/download disabled.
    W9  Every registered provider has a sanitized, unique id + tool name.
    W10 FS provider's FileTools has save/delete/replace disabled.
    W11 Scout agent has `add_history_to_context=True` + `num_history_runs>=2`.

Each check is a function that returns None on PASS and raises
``AssertionError`` on FAIL. Zero LLM, zero network — runs in under a second.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InvariantResult:
    id: str
    name: str
    passed: bool
    detail: str = ""


FORBIDDEN_OUTBOUND = ("send_email", "send_message", "create_event", "post_message", "delete_event")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_names(tools: Any) -> list[str]:
    """Best-effort extraction of tool names from an agent's ``tools=`` list."""
    if tools is None:
        return []
    if callable(tools) and not hasattr(tools, "__iter__"):
        try:
            tools = tools()
        except Exception:
            return []

    names: list[str] = []
    for item in tools:
        name = getattr(item, "name", None)
        if isinstance(name, str) and name:
            names.append(name)
            continue

        fns = getattr(item, "functions", None)
        if isinstance(fns, dict):
            names.extend(str(k) for k in fns.keys())
            continue

        sub = getattr(item, "tools", None)
        if isinstance(sub, (list, tuple)):
            for t in sub:
                n = getattr(t, "name", None)
                if isinstance(n, str) and n:
                    names.append(n)
            continue

        entry = getattr(item, "entrypoint", None)
        if callable(entry):
            fn_name = getattr(entry, "__name__", None)
            if isinstance(fn_name, str) and fn_name:
                names.append(fn_name)
                continue

        names.append(f"<{type(item).__name__}>")

    return names


def _assert_has(names: list[str], wanted: tuple[str, ...], agent: str) -> None:
    missing = [w for w in wanted if not any(w in n for n in names)]
    if missing:
        raise AssertionError(f"{agent} missing expected tool(s) {missing}. Full tool list: {names}")


def _assert_no_outbound(names: list[str], agent: str) -> None:
    leaks = [n for n in names for bad in FORBIDDEN_OUTBOUND if bad in n]
    if leaks:
        raise AssertionError(f"{agent} has outbound tool(s) it shouldn't: {leaks}. Full tool list: {names}")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def w1_scout_tool_surface() -> None:
    """Scout exposes every provider's tools + `list_contexts`, nothing outbound.

    With single-agent Scout all tools are resolved through the registry.
    The factory is a callable so this check resolves it to a concrete list.
    """
    from scout.agent import scout
    from scout.contexts import (
        create_context_providers,
        get_context_providers,
        update_context_providers,
    )

    prev = get_context_providers()
    try:
        create_context_providers()
        names = _tool_names(scout.tools)
    finally:
        update_context_providers(prev)

    _assert_no_outbound(names, "Scout")
    _assert_has(names, ("list_contexts", "query_crm", "update_crm"), "Scout")

    # Scout should not hold bare SQLTools — SQL lives inside the CRM
    # provider's sub-agents. If this regresses we lose the read/write
    # separation the CRM provider enforces.
    if any("run_sql_query" in n or "sql_tools" in n.lower() for n in names):
        raise AssertionError(f"Scout has bare SQL tools; SQL must be wrapped by the CRM provider. Tool list: {names}")


def w2_crm_provider_surface() -> None:
    """`DatabaseContextProvider` exposes both `query_crm` and `update_crm`."""
    from db import SCOUT_SCHEMA, get_readonly_engine, get_sql_engine
    from scout.context.database import DatabaseContextProvider

    provider = DatabaseContextProvider(
        id="crm",
        name="CRM",
        sql_engine=get_sql_engine(),
        readonly_engine=get_readonly_engine(),
        schema=SCOUT_SCHEMA,
    )
    tools = provider.get_tools()
    names = _tool_names(tools)
    _assert_has(names, ("query_crm", "update_crm"), "DatabaseContextProvider")

    # The base `aupdate()` raises NotImplementedError; the CRM provider
    # must override both `aquery` and `aupdate` — otherwise `update_crm`
    # returns a read-only error.
    base_aupdate = type(provider).__mro__[1].aupdate  # type: ignore[attr-defined]
    crm_aupdate = type(provider).aupdate
    if crm_aupdate is base_aupdate:
        raise AssertionError(
            "DatabaseContextProvider.aupdate is not overridden — update_crm will always return read-only"
        )


def w3_schema_guard_blocks_non_scout_writes() -> None:
    """The scout engine rejects DDL/DML against `public` / `ai` at the hook.

    Belt-and-suspenders on top of `search_path=scout,public`. Exercises the
    guard directly; if a future refactor removes the before-cursor hook,
    this check flips red immediately.
    """
    from sqlalchemy import text

    from db import get_sql_engine

    engine = get_sql_engine()
    bad_statements = [
        "CREATE TABLE public.pwned (id int)",
        "INSERT INTO public.foo VALUES (1)",
        "INSERT INTO ai.secrets VALUES (1)",
        "DELETE FROM public.users",
        "UPDATE ai.sessions SET deleted = true",
    ]
    for stmt in bad_statements:
        try:
            with engine.connect() as conn:
                conn.execute(text(stmt))
        except RuntimeError as exc:
            if "public" not in str(exc) and "ai" not in str(exc) and "scout" not in str(exc):
                raise AssertionError(f"Unexpected error text for {stmt!r}: {exc}") from exc
            continue
        except Exception as exc:
            # Anything else (e.g. OperationalError because table missing) is
            # NOT acceptable — the guard should fire first.
            raise AssertionError(f"Guard didn't fire for {stmt!r}; got {type(exc).__name__}: {exc}") from exc
        else:
            raise AssertionError(f"Guard let through: {stmt!r}")


def w4_context_protocol_shape() -> None:
    from scout.context.provider import ContextProvider
    from scout.contexts import create_context_providers

    for ctx in create_context_providers():
        if not isinstance(ctx, ContextProvider):
            raise AssertionError(f"ContextProvider {ctx.id!r} is not a subclass of ContextProvider")
        for attr in ("id", "name"):
            if not isinstance(getattr(ctx, attr, None), str):
                raise AssertionError(f"ContextProvider {type(ctx).__name__!s} missing/non-string attr {attr!r}")
        for method in ("query", "status", "get_tools", "instructions"):
            if not callable(getattr(ctx, method, None)):
                raise AssertionError(f"ContextProvider {ctx.id!r} missing callable method {method!r}")


def w5_gdrive_uses_scout_subclass() -> None:
    """GDrive provider must use `ScoutGoogleDriveTools`, not bare `GoogleDriveTools`.

    The bare upstream toolkit queries `corpora=user` and misses every file
    the SA doesn't own directly (shared folders, Shared Drives). Regressing
    to bare `GoogleDriveTools` silently breaks every real deployment, so
    pin the subclass here.
    """
    from scout.context.gdrive import GDriveContextProvider
    from scout.context.gdrive.tools import ScoutGoogleDriveTools

    provider = GDriveContextProvider(service_account_path="/tmp/eval-wiring-stub.json")
    toolkit = provider._ensure_tools()
    if not isinstance(toolkit, ScoutGoogleDriveTools):
        raise AssertionError(
            f"GDriveContextProvider._ensure_tools() returned {type(toolkit).__name__}; "
            f"expected ScoutGoogleDriveTools so shared-folder / Shared-Drive files are visible"
        )


def w8_slack_provider_tools_are_read_only() -> None:
    """The Slack provider doesn't register any send/upload/download tool.

    Scout's Slack context is read-only by design — posting to Slack goes
    through the Slack *interface*, not the context. SlackTools maps its
    enable_* flags to which tool functions get registered; this check
    walks the resulting functions dict and fails if any write tool is
    present.
    """
    from scout.context.slack import SlackContextProvider

    provider = SlackContextProvider(token="dummy-eval-token")
    toolkit = provider._ensure_tools()
    functions = getattr(toolkit, "functions", {}) or {}
    names = list(functions.keys())
    forbidden = ("send_message", "send_message_thread", "upload_file", "download_file")
    leaks = [n for n in names for bad in forbidden if bad in n]
    if leaks:
        raise AssertionError(
            f"SlackContextProvider: toolkit has write tool(s) {leaks}; "
            "Slack context must stay read-only (posts go through the interface)"
        )


def w11_scout_agent_has_history_enabled() -> None:
    """Scout must have session history enabled for multi-turn to work.

    `scout_multi_turn_recall`, `scout_multi_turn_fact_recall`, and the
    save-then-recall CRM cases all rely on agno's `add_history_to_context`
    feeding prior turns into the next one. If this flag flips off, every
    multi-turn case quietly regresses without a compile error — this
    check catches that.
    """
    from scout.agent import scout

    if not getattr(scout, "add_history_to_context", False):
        raise AssertionError(
            "Scout agent must have add_history_to_context=True; "
            "multi-turn cases depend on it. See scout/agent.py."
        )
    num_runs = getattr(scout, "num_history_runs", 0)
    if not isinstance(num_runs, int) or num_runs < 2:
        raise AssertionError(
            f"Scout agent num_history_runs={num_runs!r}; expected int >= 2 "
            "so at least the previous turn is visible."
        )


def w10_fs_provider_tools_are_read_only() -> None:
    """The Filesystem provider's FileTools disables save/delete/replace.

    Scout's fs context is read-only by design — agents can browse and
    read files under the configured root but cannot create, mutate, or
    delete anything. If a future refactor flips any write flag back on
    Scout gains a write surface that bypasses the CRM's scout-schema
    guardrails.
    """
    from scout.context.fs import FilesystemContextProvider

    provider = FilesystemContextProvider(root="/tmp")
    toolkit = provider._all_tools()[0]
    functions = getattr(toolkit, "functions", {}) or {}
    names = list(functions.keys())
    forbidden = ("save_file", "delete_file", "replace_file_chunk", "write_file", "create_file")
    leaks = [n for n in names for bad in forbidden if bad in n]
    if leaks:
        raise AssertionError(
            f"FilesystemContextProvider: toolkit has write tool(s) {leaks}; "
            "fs context must stay read-only"
        )


def w9_provider_ids_are_sanitized_and_unique() -> None:
    """Every registered ContextProvider has a sanitized, unique id.

    Ids feed into `query_<id>` / `update_<id>` tool names on Scout. If
    a provider sneaks through with uppercase, spaces, or punctuation,
    the resulting tool name is either invalid or collides with a
    sibling. Dedup is also checked in `create_context_providers`, but
    this catches the case where two providers coincidentally end up
    with the same tool name after sanitization.
    """
    import re

    from scout.contexts import create_context_providers

    sanitized = re.compile(r"^[a-z0-9_]+$")
    seen_ids: dict[str, str] = {}
    seen_tool_names: dict[str, str] = {}
    for ctx in create_context_providers():
        if not isinstance(ctx.id, str) or not ctx.id:
            raise AssertionError(f"Provider {type(ctx).__name__} has empty/non-string id {ctx.id!r}")
        if not sanitized.match(ctx.id):
            raise AssertionError(
                f"Provider id {ctx.id!r} contains non-sanitized chars — tool names would "
                "be invalid. ids must match ^[a-z0-9_]+$"
            )
        if ctx.id in seen_ids:
            raise AssertionError(f"Duplicate provider id {ctx.id!r}: {seen_ids[ctx.id]} vs {type(ctx).__name__}")
        seen_ids[ctx.id] = type(ctx).__name__
        if ctx.query_tool_name in seen_tool_names:
            raise AssertionError(
                f"Duplicate query_tool_name {ctx.query_tool_name!r}: "
                f"{seen_tool_names[ctx.query_tool_name]} vs {type(ctx).__name__}"
            )
        seen_tool_names[ctx.query_tool_name] = type(ctx).__name__


def w7_readonly_engine_blocks_writes() -> None:
    """The readonly engine rejects any INSERT/UPDATE/DELETE/CREATE/DROP at the DB level.

    Uses PostgreSQL's ``default_transaction_read_only=on``. If a future
    refactor drops the readonly flag or hands the CRM read sub-agent the
    write engine, this check flips red immediately — regardless of how
    the read sub-agent is prompted.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import InternalError, ProgrammingError

    from db import get_readonly_engine

    engine = get_readonly_engine()
    bad_statements = [
        "CREATE TABLE scout.w7_probe (id int)",
        "INSERT INTO scout.scout_notes (user_id, title, body) VALUES ('w7', 't', 'b')",
        "UPDATE scout.scout_notes SET title='hacked' WHERE user_id='w7-nobody'",
        "DELETE FROM scout.scout_notes WHERE user_id='w7-nobody'",
        "DROP TABLE scout.scout_notes",
    ]
    for stmt in bad_statements:
        try:
            with engine.connect() as conn:
                conn.execute(text(stmt))
        except (InternalError, ProgrammingError) as exc:
            msg = str(exc).lower()
            if "read-only" not in msg and "read only" not in msg:
                raise AssertionError(f"Unexpected error text for {stmt!r}: {exc}") from exc
            continue
        except Exception as exc:
            raise AssertionError(
                f"Readonly engine didn't reject {stmt!r}; got {type(exc).__name__}: {exc}"
            ) from exc
        else:
            raise AssertionError(f"Readonly engine let through: {stmt!r}")


def w6_mcp_provider_lifecycle() -> None:
    """`MCPContextProvider` implements the lifecycle interface cleanly.

    Pins the contract Scout relies on for MCP servers:
    - exposes `query_mcp_<slug>` via `get_tools()`;
    - `aclose` is callable and safe pre-connect (no session yet);
    - `status()` never raises when the session hasn't connected;
    - sync `query()` refuses (MCP is async-only).
    """
    import asyncio

    from scout.context.mcp import MCPContextProvider
    from scout.context.provider import ContextProvider

    provider = MCPContextProvider(
        server_name="wiring_probe",
        transport="stdio",
        command="echo",
        args=["unused"],
    )

    if not isinstance(provider, ContextProvider):
        raise AssertionError("MCPContextProvider does not subclass ContextProvider")

    if provider.id != "mcp_wiring_probe":
        raise AssertionError(f"expected id 'mcp_wiring_probe', got {provider.id!r}")

    names = _tool_names(provider.get_tools())
    if not any("query_mcp_wiring_probe" in n for n in names):
        raise AssertionError(f"MCPContextProvider missing query_mcp_<slug> tool; saw {names}")

    status = provider.status()
    if not status.ok:
        raise AssertionError(f"status() should not fail pre-connect: {status.detail}")

    # aclose must be safe to await even though the session was never created.
    try:
        asyncio.run(provider.aclose())
    except Exception as exc:
        raise AssertionError(f"aclose() raised pre-connect: {type(exc).__name__}: {exc}") from exc

    # Sync query must refuse — MCP sessions are async-only.
    try:
        provider.query("ping")
    except NotImplementedError:
        pass
    else:
        raise AssertionError("MCPContextProvider.query() must raise NotImplementedError")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


CHECKS = (
    w1_scout_tool_surface,
    w2_crm_provider_surface,
    w3_schema_guard_blocks_non_scout_writes,
    w4_context_protocol_shape,
    w5_gdrive_uses_scout_subclass,
    w6_mcp_provider_lifecycle,
    w7_readonly_engine_blocks_writes,
    w8_slack_provider_tools_are_read_only,
    w9_provider_ids_are_sanitized_and_unique,
    w10_fs_provider_tools_are_read_only,
    w11_scout_agent_has_history_enabled,
)


def run_all() -> list[InvariantResult]:
    """Run every check. Returns a result per check."""
    results = []
    for fn in CHECKS:
        id_, _, name = fn.__name__.partition("_")
        try:
            fn()
            results.append(InvariantResult(id=id_.upper(), name=name, passed=True))
        except Exception as exc:
            results.append(
                InvariantResult(id=id_.upper(), name=name, passed=False, detail=f"{type(exc).__name__}: {exc}")
            )
    return results
