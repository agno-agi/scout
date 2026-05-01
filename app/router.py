"""Custom API routes for Scout

GET  /contexts                 — list all contexts + status
GET  /contexts/{id}/status     — single context status
POST /contexts/{id}/query      — debug: query context directly
GET  /calendar/events          — raw calendar events in a date range
                                 (bypasses the LLM — used by the week-view UI)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from os import getenv
from pathlib import Path

import ssl
import time

from agno.context.calendar import CalendarContextProvider
from agno.os.auth import get_authentication_dependency
from agno.os.settings import AgnoAPISettings
from agno.run import RunContext
from agno.tools.google.calendar import GoogleCalendarTools
from agno.tools.google.gmail import GmailTools
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from db import SCOUT_SCHEMA, get_sql_engine
from scout.contexts import (
    CALENDAR_TOKEN_PATH,
    GMAIL_TOKEN_PATH,
    get_context_providers,
    status_row,
)


class QueryRequest(BaseModel):
    question: str
    user_id: str | None = None


class CreateFollowupRequest(BaseModel):
    title: str
    notes: str | None = None
    due_at: str | None = None  # ISO 8601 — null for "no due date"
    user_id: str = "scout-web-user"


class UpdateFollowupRequest(BaseModel):
    status: str  # 'pending' | 'done' | 'dropped'


class MarkEmailRequest(BaseModel):
    action: str  # 'read' | 'unread'


def create_router(settings: AgnoAPISettings) -> APIRouter:
    router = APIRouter(
        dependencies=[Depends(get_authentication_dependency(settings))],
    )

    @router.get("/contexts")
    def list_contexts_route():
        return [status_row(ctx) for ctx in get_context_providers()]

    @router.get("/contexts/{target_id:path}/status")
    def context_status(target_id: str):
        target = _target(target_id)
        if target is None:
            return JSONResponse({"error": f"unknown target {target_id}"}, status_code=404)
        return status_row(target)

    @router.post("/contexts/{target_id:path}/query")
    async def context_query(target_id: str, body: QueryRequest):
        target = _target(target_id)
        if target is None:
            return JSONResponse({"error": f"unknown target {target_id}"}, status_code=404)
        run_context = _build_debug_run_context(body.user_id)
        answer = await target.aquery(body.question, run_context=run_context)
        return {
            "text": answer.text,
            "results": [asdict(r) for r in answer.results],
        }

    @router.get("/calendar/events")
    def calendar_events(
        time_min: str = Query(..., alias="from", description="ISO datetime, inclusive"),
        time_max: str = Query(..., alias="to", description="ISO datetime, exclusive"),
    ):
        """Raw Google Calendar events in [time_min, time_max).

        Bypasses the calendar sub-agent — instantiates GoogleCalendarTools
        directly with the same OAuth token the agent uses, calls
        fetch_all_events, and returns the parsed JSON. Used by the week-view
        UI; an LLM hop is wasted overhead for a structured fetch.
        """
        target = _target("calendar")
        if target is None or not isinstance(target, CalendarContextProvider):
            return JSONResponse(
                {"error": "Calendar context not configured"},
                status_code=404,
            )

        token_path = str(CALENDAR_TOKEN_PATH)
        if not Path(token_path).exists() and not getenv("GOOGLE_SERVICE_ACCOUNT_FILE"):
            return JSONResponse(
                {"error": f"Calendar token missing at {token_path}. "
                          "Run scripts/google_oauth_setup.sh on the host."},
                status_code=500,
            )

        tools = GoogleCalendarTools(
            service_account_path=getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
            delegated_user=getenv("GOOGLE_DELEGATED_USER"),
            token_path=token_path,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            # Disable write + unused read tools so the constructor doesn't
            # demand the write scope.
            create_event=False,
            update_event=False,
            delete_event=False,
            find_available_slots=False,
            get_event_attendees=False,
        )

        raw = tools.fetch_all_events(
            max_results=100, start_date=time_min, end_date=time_max
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": "Calendar API returned non-JSON response"},
                status_code=502,
            )

        if isinstance(data, dict) and "error" in data:
            return JSONResponse({"error": data["error"]}, status_code=502)
        if isinstance(data, dict) and data.get("message"):
            return {"events": []}
        return {"events": data if isinstance(data, list) else []}

    # -----------------------------------------------------------------
    # Gmail unread — direct API fetch, bypasses the agent.
    #
    # The Gmail/Calendar Python clients hit Google over httplib2 with
    # connection pooling that occasionally breaks on idle connections,
    # surfacing as ssl WRONG_VERSION_NUMBER. The agent has no way to
    # retry the underlying call — it just relays the error. Here we
    # rebuild the toolkit (= fresh connection pool) on each retry,
    # which clears the bad connection.
    # -----------------------------------------------------------------

    def _build_gmail_service(scope: str = "modify"):
        """Build a fresh GmailTools instance and prime its `service`.
        New instance per call = fresh httplib2 connection pool, which is the
        whole point — it's how we recover from idle-closed TLS connections."""
        scope_url = (
            "https://www.googleapis.com/auth/gmail.modify"
            if scope == "modify"
            else "https://www.googleapis.com/auth/gmail.readonly"
        )
        tools = GmailTools(
            service_account_path=getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
            delegated_user=getenv("GOOGLE_DELEGATED_USER"),
            token_path=str(GMAIL_TOKEN_PATH),
            scopes=[scope_url],
            # Disable everything — we call .service directly.
            get_latest_emails=False,
            get_unread_emails=False,
            get_emails_from_user=False,
            get_starred_emails=False,
            get_emails_by_context=False,
            get_emails_by_date=False,
            get_emails_by_thread=False,
            search_emails=False,
            get_message=False,
            list_drafts=False,
            get_draft=False,
            list_custom_labels=False,
            create_draft_email=False,
            send_email=False,
            send_email_reply=False,
            mark_email_as_read=False,
            mark_email_as_unread=False,
            star_email=False,
            unstar_email=False,
            apply_label=False,
            remove_label=False,
            delete_custom_label=False,
            update_draft=False,
        )
        tools._auth()
        tools.service = tools._build_service()
        return tools.service

    def _retry_gmail(fn):
        """Run a Gmail API call with up to 3 retries on transient TLS / network
        errors. The fn must rebuild the service inside (so each retry gets a
        fresh httplib2 connection pool)."""
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                return fn()
            except (ssl.SSLError, ConnectionError, OSError) as exc:
                last_err = exc
                time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(
            f"Gmail upstream flaky: {type(last_err).__name__}: {last_err}"
        )

    @router.get("/gmail/unread")
    def gmail_unread(count: int = Query(50, ge=1, le=100)):
        if not Path(str(GMAIL_TOKEN_PATH)).exists() and not getenv("GOOGLE_SERVICE_ACCOUNT_FILE"):
            return JSONResponse(
                {"error": f"Gmail token missing at {GMAIL_TOKEN_PATH}. "
                          "Run scripts/google_oauth_setup.sh on the host."},
                status_code=500,
            )

        def fetch_once() -> dict:
            service = _build_gmail_service("readonly")
            list_res = (
                service.users()
                .messages()
                .list(userId="me", q="is:unread", maxResults=count)
                .execute()
            )
            messages = list_res.get("messages", []) or []
            out: list[dict] = []
            for m in messages:
                meta = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=m["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )
                headers = {
                    h["name"]: h["value"]
                    for h in meta.get("payload", {}).get("headers", [])
                }
                out.append({
                    "id": meta["id"],
                    "thread_id": meta.get("threadId"),
                    "from": headers.get("From"),
                    "subject": headers.get("Subject"),
                    "date": headers.get("Date"),
                    "snippet": meta.get("snippet"),
                })
            return {"emails": out}

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                return fetch_once()
            except (ssl.SSLError, ConnectionError, OSError) as exc:
                last_err = exc
                time.sleep(0.5 * (2 ** attempt))  # 0.5s, 1s, 2s
            except Exception as exc:
                # Non-transient: don't retry.
                return JSONResponse(
                    {"error": f"{type(exc).__name__}: {exc}"},
                    status_code=502,
                )
        return JSONResponse(
            {"error": f"Gmail upstream flaky: {type(last_err).__name__}: {last_err}"},
            status_code=502,
        )

    @router.get("/gmail/thread/{thread_id}")
    def gmail_thread(thread_id: str):
        """Full thread with all messages — used by the email detail modal."""
        try:
            def go():
                service = _build_gmail_service("readonly")
                t = (
                    service.users()
                    .threads()
                    .get(userId="me", id=thread_id, format="full")
                    .execute()
                )
                return {
                    "id": t["id"],
                    "messages": [_parse_message(m) for m in t.get("messages", [])],
                }
            return _retry_gmail(go)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        except Exception as exc:
            return JSONResponse(
                {"error": f"{type(exc).__name__}: {exc}"}, status_code=502
            )

    @router.post("/gmail/message/{message_id}/mark")
    def gmail_mark(message_id: str, body: MarkEmailRequest):
        if body.action not in ("read", "unread"):
            return JSONResponse(
                {"error": "action must be 'read' or 'unread'"}, status_code=400
            )
        try:
            def go():
                service = _build_gmail_service("modify")
                request_body = (
                    {"removeLabelIds": ["UNREAD"]}
                    if body.action == "read"
                    else {"addLabelIds": ["UNREAD"]}
                )
                service.users().messages().modify(
                    userId="me", id=message_id, body=request_body
                ).execute()
                return {"ok": True, "action": body.action}
            return _retry_gmail(go)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=502)
        except Exception as exc:
            # 403 most commonly means the OAuth token doesn't have
            # gmail.modify scope. Surface that clearly.
            msg = str(exc)
            hint = (
                " — re-run scripts/google_oauth_setup.sh to grant the modify scope"
                if "insufficient" in msg.lower() or "403" in msg
                else ""
            )
            return JSONResponse(
                {"error": f"{type(exc).__name__}: {exc}{hint}"},
                status_code=403 if "insufficient" in msg.lower() else 502,
            )

    # -----------------------------------------------------------------
    # Follow-ups (scout.scout_followups) — direct DB endpoints
    #
    # The CRM context provider can already write here via natural language
    # (update_crm), but the dashboard needs a fast, deterministic surface
    # to add / list / check off items without an LLM hop. These routes
    # talk to the same table the agent uses, so chat and UI stay in sync.
    # -----------------------------------------------------------------

    @router.get("/crm/followups")
    def list_followups(
        status: str | None = Query(None, description="pending | done | dropped"),
        user_id: str = Query("scout-web-user"),
    ):
        engine = get_sql_engine()
        sql = (
            f"SELECT id, title, notes, due_at, status, tags, created_at "
            f"FROM {SCOUT_SCHEMA}.scout_followups WHERE user_id = :user_id"
        )
        params: dict = {"user_id": user_id}
        if status:
            sql += " AND status = :status"
            params["status"] = status
        sql += " ORDER BY (due_at IS NULL), due_at ASC, id DESC"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return {"followups": [_row_to_dict(r) for r in rows]}

    @router.post("/crm/followups", status_code=201)
    def create_followup(body: CreateFollowupRequest):
        if not body.title.strip():
            return JSONResponse({"error": "title is required"}, status_code=400)
        engine = get_sql_engine()
        sql = (
            f"INSERT INTO {SCOUT_SCHEMA}.scout_followups "
            f"(title, notes, due_at, user_id) "
            f"VALUES (:title, :notes, :due_at, :user_id) "
            f"RETURNING id, title, notes, due_at, status, tags, created_at"
        )
        params = {
            "title": body.title.strip(),
            "notes": body.notes,
            "due_at": body.due_at,
            "user_id": body.user_id,
        }
        with engine.begin() as conn:
            row = conn.execute(text(sql), params).mappings().first()
        return _row_to_dict(row) if row else JSONResponse(
            {"error": "insert failed"}, status_code=500
        )

    @router.patch("/crm/followups/{followup_id}")
    def update_followup(followup_id: int, body: UpdateFollowupRequest):
        if body.status not in ("pending", "done", "dropped"):
            return JSONResponse(
                {"error": "status must be pending|done|dropped"},
                status_code=400,
            )
        engine = get_sql_engine()
        sql = (
            f"UPDATE {SCOUT_SCHEMA}.scout_followups SET status = :status "
            f"WHERE id = :id "
            f"RETURNING id, title, notes, due_at, status, tags, created_at"
        )
        with engine.begin() as conn:
            row = conn.execute(
                text(sql), {"status": body.status, "id": followup_id}
            ).mappings().first()
        if row is None:
            return JSONResponse(
                {"error": f"followup {followup_id} not found"}, status_code=404
            )
        return _row_to_dict(row)

    return router


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy RowMapping to a JSON-safe dict."""
    out = dict(row)
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out


def _parse_message(msg: dict) -> dict:
    """Pull the fields the email modal renders out of a Gmail message resource."""
    headers = {
        h["name"]: h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "from": headers.get("From"),
        "to": headers.get("To"),
        "cc": headers.get("Cc"),
        "subject": headers.get("Subject"),
        "date": headers.get("Date"),
        "snippet": msg.get("snippet"),
        "is_unread": "UNREAD" in (msg.get("labelIds") or []),
        "body_text": _extract_text_body(msg.get("payload", {})),
    }


def _extract_text_body(payload: dict) -> str:
    """Walk a Gmail payload tree and pull the best plain-text body.
    Falls back to a stripped text/html part if no text/plain exists."""
    import base64
    import html
    import re

    def decode(data: str) -> str:
        try:
            return base64.urlsafe_b64decode(data.encode("ascii")).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            return ""

    def find_part(p: dict, mime: str) -> str | None:
        if p.get("mimeType") == mime:
            data = p.get("body", {}).get("data")
            if data:
                return decode(data)
        for child in p.get("parts") or []:
            found = find_part(child, mime)
            if found:
                return found
        return None

    plain = find_part(payload, "text/plain")
    if plain:
        return plain.strip()

    html_body = find_part(payload, "text/html")
    if html_body:
        # Strip tags as a last resort. Not pretty but readable.
        no_scripts = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", "", html_body, flags=re.S | re.I
        )
        text = re.sub(r"<[^>]+>", " ", no_scripts)
        return html.unescape(re.sub(r"\s+", " ", text)).strip()

    return ""


def _target(target_id: str):
    for ctx in get_context_providers():
        if ctx.id == target_id:
            return ctx
    return None


def _build_debug_run_context(user_id: str | None) -> RunContext | None:
    """Fresh RunContext per debug call so the sub-agent's {user_id} template
    substitutes correctly. run_id/session_id are required by the constructor
    but the sub-agent picks its own session when it runs; these IDs just
    identify this debug hop in traces.
    """
    if not user_id:
        return None
    debug_id = uuid.uuid4().hex[:8]
    return RunContext(
        run_id=f"debug-{debug_id}",
        session_id=f"debug-{debug_id}",
        user_id=user_id,
    )
