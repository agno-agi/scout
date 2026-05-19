"""
Test Gmail and Calendar Context Providers
==========================================

Run: .venv/bin/python test_google_context_providers.py

Tests:
1. Provider status (auth validation)
2. Gmail read operations (search, get message)
3. Calendar read operations (list events, search)
4. Write operations (marked skip by default)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_FILE", ".scout/service-account.json")

from dotenv import load_dotenv

load_dotenv()

from agno.context.calendar import GoogleCalendarContextProvider
from agno.context.gmail import GmailContextProvider
from agno.models.openai import OpenAIChat

TEST_WRITE_OPS = os.getenv("TEST_WRITE_OPS", "").lower() in ("1", "true", "yes")


def get_model():
    return OpenAIChat(id="gpt-4o-mini")


def test_calendar_status():
    print("\n" + "=" * 60)
    print("TEST: Calendar Provider Status")
    print("=" * 60)

    provider = GoogleCalendarContextProvider(model=get_model(), token_path="calendar_token.json")
    status = provider.status()
    print(f"OK: {status.ok}")
    print(f"Detail: {status.detail}")
    return status.ok


def test_gmail_status():
    print("\n" + "=" * 60)
    print("TEST: Gmail Provider Status")
    print("=" * 60)

    delegated_user = os.getenv("GOOGLE_DELEGATED_USER")
    if not delegated_user:
        print("SKIP: GOOGLE_DELEGATED_USER not set (required for Gmail SA auth)")
        return None

    provider = GmailContextProvider(model=get_model())
    status = provider.status()
    print(f"OK: {status.ok}")
    print(f"Detail: {status.detail}")
    return status.ok


def test_calendar_query():
    print("\n" + "=" * 60)
    print("TEST: Calendar Query (list events)")
    print("=" * 60)

    provider = GoogleCalendarContextProvider(model=get_model(), token_path="calendar_token.json")

    # Simple query - avoid date ranges that trigger time_min/time_max bug
    query = "List my upcoming 5 events"
    print(f"Query: {query}")

    try:
        answer = provider.query(query)
        text = answer.text or "(no text)"
        print(f"\nAnswer (first 500 chars):")
        print("-" * 40)
        print(text[:500] if len(text) > 500 else text)
        print("-" * 40)

        # Check for common errors
        if "API has not been used" in text or "accessNotConfigured" in text:
            print("\nFAIL: Calendar API not enabled in GCP project")
            print("Enable at: https://console.developers.google.com/apis/api/calendar-json.googleapis.com")
            return False

        return True
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return False


def test_gmail_query():
    print("\n" + "=" * 60)
    print("TEST: Gmail Query (search emails)")
    print("=" * 60)

    delegated_user = os.getenv("GOOGLE_DELEGATED_USER")
    if not delegated_user:
        print("SKIP: GOOGLE_DELEGATED_USER not set")
        return None

    provider = GmailContextProvider(model=get_model())

    query = "Show me my 3 most recent emails"
    print(f"Query: {query}")

    try:
        answer = provider.query(query)
        text = answer.text or "(no text)"
        print(f"\nAnswer (first 500 chars):")
        print("-" * 40)
        print(text[:500] if len(text) > 500 else text)
        print("-" * 40)

        if "API has not been used" in text or "accessNotConfigured" in text:
            print("\nFAIL: Gmail API not enabled in GCP project")
            return False

        return True
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return False


async def test_calendar_async_query():
    print("\n" + "=" * 60)
    print("TEST: Calendar Async Query")
    print("=" * 60)

    provider = GoogleCalendarContextProvider(model=get_model(), token_path="calendar_token.json")

    query = "List my next 3 events"
    print(f"Query: {query}")

    try:
        answer = await provider.aquery(query)
        text = answer.text or "(no text)"
        print(f"\nAnswer (first 500 chars):")
        print("-" * 40)
        print(text[:500] if len(text) > 500 else text)
        print("-" * 40)

        if "API has not been used" in text or "accessNotConfigured" in text:
            print("\nFAIL: Calendar API not enabled in GCP project")
            return False

        return True
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return False


def test_calendar_update():
    print("\n" + "=" * 60)
    print("TEST: Calendar Update (create event)")
    print("=" * 60)

    if not TEST_WRITE_OPS:
        print("SKIP: Set TEST_WRITE_OPS=1 to run write tests")
        return None

    provider = GoogleCalendarContextProvider(model=get_model(), token_path="calendar_token.json", write=True)

    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    instruction = f"Create a test event called 'Scout Test Event' tomorrow ({tomorrow.date()}) at 2pm for 30 minutes"
    print(f"Instruction: {instruction}")

    try:
        answer = provider.update(instruction)
        text = answer.text or "(no text)"
        print(f"\nAnswer:")
        print("-" * 40)
        print(text)
        print("-" * 40)
        return True
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return False


def test_gmail_update():
    print("\n" + "=" * 60)
    print("TEST: Gmail Update (draft email)")
    print("=" * 60)

    delegated_user = os.getenv("GOOGLE_DELEGATED_USER")
    if not delegated_user:
        print("SKIP: GOOGLE_DELEGATED_USER not set")
        return None

    if not TEST_WRITE_OPS:
        print("SKIP: Set TEST_WRITE_OPS=1 to run write tests")
        return None

    provider = GmailContextProvider(model=get_model(), write=True)

    instruction = "Draft an email to myself with subject 'Scout Test' and body 'This is a test email from Scout.'"
    print(f"Instruction: {instruction}")

    try:
        answer = provider.update(instruction)
        text = answer.text or "(no text)"
        print(f"\nAnswer:")
        print("-" * 40)
        print(text)
        print("-" * 40)
        return True
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return False


def test_scout_contexts_integration():
    print("\n" + "=" * 60)
    print("TEST: Scout contexts.py integration")
    print("=" * 60)

    from scout.contexts import (
        _create_calendar_provider,
        _create_gmail_provider,
    )

    # Test individual factories (doesn't require database)
    try:
        calendar = _create_calendar_provider()
        gmail = _create_gmail_provider()

        print(f"Calendar factory: {type(calendar).__name__ if calendar else 'None'}")
        print(f"Gmail factory: {type(gmail).__name__ if gmail else 'None'}")

        calendar_ok = calendar is not None
        gmail_ok = gmail is not None or not os.getenv("GOOGLE_DELEGATED_USER")

        print(f"\nCalendar created: {calendar_ok}")
        print(f"Gmail created: {gmail_ok} (requires GOOGLE_DELEGATED_USER)")

        # Skip full registry test - requires database
        print("\nNote: Full registry test skipped (requires database)")

        return calendar_ok and gmail_ok
    except Exception as exc:
        print(f"\nFAIL: {type(exc).__name__}: {exc}")
        return False


def main():
    print("Google Context Providers Test Suite")
    print("=" * 60)
    print(f"Service account: {os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE')}")
    print(f"Delegated user: {os.environ.get('GOOGLE_DELEGATED_USER', '(not set)')}")
    print(f"Write tests: {'ENABLED' if TEST_WRITE_OPS else 'disabled (set TEST_WRITE_OPS=1 to enable)'}")

    results = {}

    # Status tests
    results["calendar_status"] = test_calendar_status()
    results["gmail_status"] = test_gmail_status()

    # Query tests
    if results.get("calendar_status"):
        results["calendar_query"] = test_calendar_query()
        results["calendar_async"] = asyncio.run(test_calendar_async_query())

    if results.get("gmail_status"):
        results["gmail_query"] = test_gmail_query()

    # Write tests
    if results.get("calendar_status"):
        results["calendar_update"] = test_calendar_update()

    if results.get("gmail_status"):
        results["gmail_update"] = test_gmail_update()

    # Integration test
    results["scout_integration"] = test_scout_contexts_integration()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, result in results.items():
        status = "PASS" if result is True else "SKIP" if result is None else "FAIL"
        print(f"  {name}: {status}")

    passed = sum(1 for r in results.values() if r is True)
    skipped = sum(1 for r in results.values() if r is None)
    failed = sum(1 for r in results.values() if r is False)
    print(f"\nTotal: {passed} passed, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
