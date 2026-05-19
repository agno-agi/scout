"""
Comprehensive Google Context Provider Tests
============================================

Run: .venv/bin/python test_google_comprehensive.py

Tests all read/write operations for Calendar and Gmail providers.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from agno.context.calendar import GoogleCalendarContextProvider
from agno.context.gmail import GmailContextProvider
from agno.models.openai import OpenAIChat

CALENDAR_TOKEN = "calendar_token.json"
GMAIL_TOKEN = "gmail_token.json"


def get_model():
    return OpenAIChat(id="gpt-4o-mini")


def header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def subtest(name: str):
    print(f"\n--- {name} ---")


class CalendarTests:
    def __init__(self):
        self.provider = GoogleCalendarContextProvider(
            model=get_model(),
            token_path=CALENDAR_TOKEN,
            write=True,
        )
        self.results = {}
        self.created_event_id = None

    def run_all(self):
        header("CALENDAR PROVIDER TESTS")

        # Status
        subtest("1. Status Check")
        status = self.provider.status()
        print(f"OK: {status.ok}")
        print(f"Detail: {status.detail}")
        self.results["status"] = status.ok

        if not status.ok:
            print("SKIP: Calendar not authenticated")
            return self.results

        # Read operations
        self.test_list_events()
        self.test_search_events()
        self.test_check_availability()
        self.test_find_slots()

        # Write operations
        self.test_create_event()
        if self.created_event_id:
            self.test_get_event()
            self.test_update_event()
            self.test_delete_event()

        # Async operations
        asyncio.run(self.test_async_query())

        return self.results

    def test_list_events(self):
        subtest("2. List Events (sync)")
        try:
            answer = self.provider.query("List my next 5 upcoming events with their times and locations")
            print(f"Response length: {len(answer.text or '')} chars")
            print(f"Preview: {(answer.text or '')[:300]}...")
            self.results["list_events"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["list_events"] = False

    def test_search_events(self):
        subtest("3. Search Events")
        try:
            answer = self.provider.query("Search for any meetings with 'review' or 'standup' in the title this week")
            print(f"Response length: {len(answer.text or '')} chars")
            print(f"Preview: {(answer.text or '')[:300]}...")
            self.results["search_events"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["search_events"] = False

    def test_check_availability(self):
        subtest("4. Check Availability")
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        try:
            answer = self.provider.query(f"Am I free tomorrow ({tomorrow}) between 2pm and 4pm?")
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["check_availability"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["check_availability"] = False

    def test_find_slots(self):
        subtest("5. Find Available Slots")
        try:
            answer = self.provider.query("Find me 3 available 30-minute slots this week for a meeting")
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["find_slots"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["find_slots"] = False

    def test_create_event(self):
        subtest("6. Create Event (write)")
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        event_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
        try:
            answer = self.provider.update(
                f"Create a test event called 'Scout Integration Test' on {event_time.strftime('%Y-%m-%d')} "
                f"at 3:00 PM EST for 30 minutes. Add description 'Automated test - safe to delete'"
            )
            print(f"Response: {(answer.text or '')[:400]}...")
            # Try to extract event ID from response
            text = answer.text or ""
            if "created" in text.lower() or "event" in text.lower():
                self.results["create_event"] = True
                # Store that we created something (we'll search for it)
                self.created_event_id = "pending_lookup"
            else:
                self.results["create_event"] = False
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["create_event"] = False

    def test_get_event(self):
        subtest("7. Get Event Details")
        try:
            answer = self.provider.query("Find the event called 'Scout Integration Test' and show me its full details")
            print(f"Response: {(answer.text or '')[:400]}...")
            self.results["get_event"] = bool(answer.text and "Scout Integration Test" in (answer.text or ""))
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["get_event"] = False

    def test_update_event(self):
        subtest("8. Update Event (write)")
        try:
            answer = self.provider.update(
                "Find the event 'Scout Integration Test' and update its description to "
                "'Updated by Scout test suite - safe to delete'"
            )
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["update_event"] = bool(answer.text and ("updated" in (answer.text or "").lower()))
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["update_event"] = False

    def test_delete_event(self):
        subtest("9. Delete Event (write)")
        try:
            answer = self.provider.update(
                "Delete the event called 'Scout Integration Test'"
            )
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["delete_event"] = bool(answer.text and ("deleted" in (answer.text or "").lower() or "removed" in (answer.text or "").lower()))
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["delete_event"] = False

    async def test_async_query(self):
        subtest("10. Async Query")
        try:
            answer = await self.provider.aquery("What's on my calendar today?")
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["async_query"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["async_query"] = False


class GmailTests:
    def __init__(self):
        self.has_gmail = os.path.exists(GMAIL_TOKEN) or os.getenv("GOOGLE_DELEGATED_USER")
        if self.has_gmail:
            self.provider = GmailContextProvider(
                model=get_model(),
                token_path=GMAIL_TOKEN,
                write=True,
            )
        else:
            self.provider = None
        self.results = {}
        self.draft_id = None

    def run_all(self):
        header("GMAIL PROVIDER TESTS")

        if not self.has_gmail:
            print("SKIP: Gmail not configured (need GOOGLE_DELEGATED_USER or gmail_token.json)")
            return {"gmail_configured": False}

        # Status
        subtest("1. Status Check")
        try:
            status = self.provider.status()
            print(f"OK: {status.ok}")
            print(f"Detail: {status.detail}")
            self.results["status"] = status.ok
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["status"] = False
            return self.results

        if not self.results.get("status"):
            print("SKIP: Gmail not authenticated")
            return self.results

        # Read operations
        self.test_list_recent()
        self.test_search_emails()
        self.test_get_unread()

        # Write operations
        self.test_create_draft()
        if self.draft_id:
            self.test_update_draft()
            self.test_delete_draft()

        return self.results

    def test_list_recent(self):
        subtest("2. List Recent Emails")
        try:
            answer = self.provider.query("Show me my 3 most recent emails with sender and subject")
            print(f"Response: {(answer.text or '')[:400]}...")
            self.results["list_recent"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["list_recent"] = False

    def test_search_emails(self):
        subtest("3. Search Emails")
        try:
            answer = self.provider.query("Search for emails from the last 7 days with attachments")
            print(f"Response: {(answer.text or '')[:400]}...")
            self.results["search_emails"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["search_emails"] = False

    def test_get_unread(self):
        subtest("4. Get Unread Emails")
        try:
            answer = self.provider.query("How many unread emails do I have? List the first 3")
            print(f"Response: {(answer.text or '')[:400]}...")
            self.results["get_unread"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["get_unread"] = False

    def test_create_draft(self):
        subtest("5. Create Draft (write)")
        try:
            answer = self.provider.update(
                "Create a draft email to myself with subject 'Scout Test Draft' "
                "and body 'This is an automated test draft - safe to delete'"
            )
            print(f"Response: {(answer.text or '')[:400]}...")
            self.results["create_draft"] = bool(answer.text and "draft" in (answer.text or "").lower())
            if self.results["create_draft"]:
                self.draft_id = "created"
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["create_draft"] = False

    def test_update_draft(self):
        subtest("6. Update Draft (write)")
        try:
            answer = self.provider.update(
                "Find my draft with subject 'Scout Test Draft' and update the body to "
                "'Updated by Scout test suite'"
            )
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["update_draft"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["update_draft"] = False

    def test_delete_draft(self):
        subtest("7. Delete Draft (write)")
        try:
            answer = self.provider.update(
                "Delete my draft with subject 'Scout Test Draft'"
            )
            print(f"Response: {(answer.text or '')[:300]}...")
            self.results["delete_draft"] = bool(answer.text)
        except Exception as e:
            print(f"FAIL: {e}")
            self.results["delete_draft"] = False


def print_summary(calendar_results: dict, gmail_results: dict):
    header("TEST SUMMARY")

    all_results = {}

    print("\nCalendar Tests:")
    for name, passed in calendar_results.items():
        status = "PASS" if passed else "FAIL" if passed is False else "SKIP"
        print(f"  {name}: {status}")
        all_results[f"calendar_{name}"] = passed

    print("\nGmail Tests:")
    for name, passed in gmail_results.items():
        status = "PASS" if passed else "FAIL" if passed is False else "SKIP"
        print(f"  {name}: {status}")
        all_results[f"gmail_{name}"] = passed

    passed = sum(1 for v in all_results.values() if v is True)
    failed = sum(1 for v in all_results.values() if v is False)
    skipped = sum(1 for v in all_results.values() if v is None or v == "SKIP")

    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")

    if failed > 0:
        print("\nFailed tests:")
        for name, passed in all_results.items():
            if passed is False:
                print(f"  - {name}")


def main():
    print("=" * 70)
    print("  COMPREHENSIVE GOOGLE CONTEXT PROVIDER TEST SUITE")
    print("=" * 70)
    print(f"\nCalendar token: {CALENDAR_TOKEN} (exists: {os.path.exists(CALENDAR_TOKEN)})")
    print(f"Gmail token: {GMAIL_TOKEN} (exists: {os.path.exists(GMAIL_TOKEN)})")
    print(f"Delegated user: {os.getenv('GOOGLE_DELEGATED_USER', '(not set)')}")

    # Run tests
    calendar_tests = CalendarTests()
    calendar_results = calendar_tests.run_all()

    gmail_tests = GmailTests()
    gmail_results = gmail_tests.run_all()

    # Summary
    print_summary(calendar_results, gmail_results)


if __name__ == "__main__":
    main()
