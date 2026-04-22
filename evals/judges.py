"""Evaluate answer quality via LLM-as-judge.

Graders the behavioral tier can't express — answer quality, routing
clarity. Each case scores 0–10 via ``AgentAsJudgeEval``; pass threshold
is ``passing_score`` on the ``Judged`` dataclass (default 7.0).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal

from agno.eval.agent_as_judge import AgentAsJudgeEval

from evals.runner import build_fixture, install_fixture, restore_contexts
from scout.settings import default_model

JUDGE_MODEL = default_model()


@dataclass(frozen=True)
class Judged:
    """One judged case."""

    id: str
    prompt: str
    criteria: str
    scoring: Literal["binary", "numeric"] = "numeric"
    passing_score: float = 7.0
    fixture: str = "default"


JUDGED: tuple[Judged, ...] = (
    Judged(
        id="capabilities_clarity",
        prompt="What can you do? Explain in 2-3 sentences.",
        criteria=(
            "Score 1-10. Scout is a single context agent — no team, no "
            "specialists. It answers by querying its registered contexts.\n\n"
            "The default fixture registers these contexts: Web, Slack, "
            "Google Drive, CRM (the user's contacts/projects/notes), and "
            "an MCP-wrapped Jira server. "
            "A well-formed answer names some of these by category so the "
            "user understands what Scout can actually reach. "
            "Generic phrases like 'search the web' or 'remember notes' "
            "count — the exact provider name isn't required, and naming "
            "MCP-registered sources like Jira is accurate (not fabrication).\n\n"
            "Points: "
            "(+3) the answer mentions READING external context (web/slack/drive "
            "or any concrete external source) by name or clear paraphrase; "
            "(+3) the answer mentions MEMORY / CRM — contacts, notes, projects, "
            "or an equivalent 'remember'/'save'/'track' capability; "
            "(+2) the answer is concise (roughly 2-3 sentences, not a long essay); "
            "(+1) the answer does NOT name old specialists (no 'Explorer', no "
            "'Engineer' as roles Scout delegates to); "
            "(+1) the answer does NOT promise features Scout doesn't have — no "
            "email sending, calendar, gmail, wiki, etc."
        ),
    ),
    Judged(
        id="identity_recall",
        prompt=(
            "Who are you? What can you help me with, and what do you "
            "remember about me?"
        ),
        criteria=(
            "Score 1-10. Scout is a single context agent with access to "
            "Web, Slack, Drive, CRM (the user's contacts/projects/notes), "
            "and an MCP-wrapped Jira source (under the default fixture). "
            "It has no persistent memory outside session history + the "
            "CRM. The user_id is 'default'; Scout has no prior CRM data "
            "on this user unless it queries.\n\n"
            "Award points for SUBSTANCE, not framing. Harmless helpfulness — "
            "offers to look up, confidence caveats — does not cost points "
            "unless it introduces invented facts.\n\n"
            "Points: "
            "(+3) the response identifies Scout by name (capitalized "
            "'Scout' appears); "
            "(+3) the response names at least two registered sources — any "
            "of web/slack/drive/CRM/contacts/notes/projects/jira/MCP "
            "— with names or clear paraphrases; "
            "(+2) no fabricated personal details about the user (no invented "
            "name, company, or prior conversations unless they're in session "
            "history); acknowledging 'I don't have any saved data about you "
            "yet' or offering to look in the CRM is fine; "
            "(+2) the response is concise — a few sentences or a short "
            "bulleted block, not a capability-tour essay with every tool "
            "listed."
        ),
    ),
    Judged(
        id="web_citation_quality",
        prompt="Ask the web context about 'sample topic' and cite the source URL you find.",
        criteria=(
            "Score 1-10. The stub web context returns exactly this string:\n"
            "'Stub web answer for eval purposes. Cited: https://example.com/stub'\n\n"
            "Award points for SUBSTANCE, not framing. Harmless helpfulness — "
            "caveats about the stub being a placeholder, offers to try other "
            "sources — does not cost points unless it introduces invented facts.\n\n"
            "Points: "
            "(+4) the response includes the URL https://example.com/stub "
            "(any recognizable form — full URL or the hostname plus path); "
            "(+3) the response stays on the stub's content — no fabricated "
            "topic facts presented as coming from the web; "
            "(+2) the source is clearly attributed (a labeled 'source:' / "
            "'cited at' / URL on its own line) rather than buried in prose "
            "with no label; "
            "(+1) the response is concise — one focused answer, not padded "
            "with training trivia or cross-provider fan-out."
        ),
    ),
    Judged(
        id="gdrive_citation_quality",
        prompt="Find a Google Drive file about the Q4 roadmap and tell me what it is.",
        criteria=(
            "Score 1-10. The stub Drive context returns exactly this string:\n"
            "\"File: 'Q4 Roadmap 2026.gdoc' (application/vnd.google-apps.document). "
            'webViewLink: https://drive.google.com/file/d/1eval_stub/view"\n\n'
            "Award points for SUBSTANCE, not framing. Harmless helpfulness — "
            "confidence levels, offers to look further, caveats about only having "
            "metadata — does not cost points unless it introduces invented facts.\n\n"
            "Points: "
            "(+4) the response names the file (any recognizable form of "
            "'Q4 Roadmap 2026'); "
            "(+3) the response includes the webViewLink or a drive.google.com URL "
            "traceable to the stub (file id `1eval_stub` or the full link); "
            "(+2) the response does NOT fabricate content beyond what the stub "
            'returned. Stating the MIME type, calling it "a Google Docs file", '
            "saying it appears to be a Q4 roadmap by filename, or offering to do "
            "follow-up work are all fine. Deduct only for invented authors, made-up "
            "body text, or details that contradict or extend the stub; "
            "(+1) the answer is focused on the single file the stub returned — "
            "not a padded list of additional hypothetical matches."
        ),
    ),
    Judged(
        id="slack_citation_quality",
        prompt="Search Slack for Q4 roadmap discussion and cite the source.",
        criteria=(
            "Score 1-10. The stub Slack context returns exactly this string:\n"
            "\"From #eng-roadmap (U07EVAL): 'Q4 roadmap finalized for "
            "2026-03-11'. Permalink: "
            'https://example.slack.com/archives/C07EVAL/p1712345000"\n\n'
            "Award points for SUBSTANCE, not framing. Harmless helpfulness — "
            "caveats about stub content, offers to expand the thread — does "
            "not cost points unless it introduces invented facts.\n\n"
            "Points: "
            "(+3) the response quotes the stub's message ('Q4 roadmap "
            "finalized for 2026-03-11') — any faithful rewording is fine; "
            "(+3) the response includes the channel name '#eng-roadmap' "
            "OR the permalink URL (any recognizable form); "
            "(+2) no fabricated facts — no invented participants, owners, "
            "milestones, or quotes beyond what the stub returned (the user "
            "id 'U07EVAL' is in the stub, so echoing it isn't fabrication); "
            "(+2) the source is clearly attributed (channel, permalink, or "
            "a 'Slack:' label) rather than blended into prose."
        ),
    ),
    Judged(
        id="scout_concise_write_ack",
        prompt=(
            "For user 'eval-user-42', save a note titled 'ship status' with body 'API release slipping to next week'."
        ),
        criteria=(
            "Score 1-10. This is a write — the user wants a short "
            "acknowledgment, not a debrief. Scout calls update_crm and "
            "the final response should be a short confirmation.\n\n"
            "Echoing DB-assigned fields that come out of the INSERT (the "
            "SERIAL id, created_at timestamp, or the schema name like "
            "'scout.scout_notes') is NOT fabrication — those are facts the "
            "database returned. Do not deduct for including them.\n\n"
            "Points: "
            "(+5) the response confirms the save in plain language "
            "(e.g. 'saved', 'stored', 'noted', 'added', 'recorded'); "
            "(+3) the response includes the title ('ship status') OR the "
            "body text so the user can verify the right note was stored "
            "(either is sufficient — one is enough); "
            "(+1) the response is FOCUSED — a short confirmation plus a "
            "compact bullet list of the saved row (title/body/id/user_id) "
            "is ideal. Deduct only for actual padding: other-capability "
            "menus, cross-provider offers, multi-section essays, filler "
            "disclaimers. A tight bullet list of the inserted columns is "
            "the target shape, NOT padding; "
            "(+1) no fabricated facts — no invented project status, owner, "
            "or follow-up commitment beyond what the user provided."
        ),
    ),
    Judged(
        id="crm_query_quality",
        prompt=(
            "For user 'eval-judge-crm', save a note titled 'judge-probe' "
            "with body 'this is the body the judge is looking for'. Then, "
            "in the same turn, list the notes the user has saved so far."
        ),
        criteria=(
            "Score 1-10. This combines a write and a read through the CRM "
            "provider. Scout should call update_crm, then query_crm, and "
            "report back.\n\n"
            "The judge-probe note gets inserted into scout.scout_notes with "
            "user_id='eval-judge-crm', title='judge-probe', body='this is "
            "the body the judge is looking for'. The list-back should "
            "surface that row. Note: this user may have MORE notes from "
            "prior test runs — the user_id is reused across the 5-run "
            "sweep. Extra historical rows in the list are NOT fabrication; "
            "they are real data.\n\n"
            "Points: "
            "(+4) the write is confirmed (Scout says it saved / stored / "
            "added the note, mentioning 'judge-probe' or the body text); "
            "(+3) the list-back includes a row titled 'judge-probe' — "
            "proves the read path works and the new row is visible; "
            "(+2) no fabricated columns — Scout doesn't invent columns "
            "(owner, author, tags that weren't set) or hallucinate values "
            "that aren't in the DB. Historical rows with real titles from "
            "prior runs DO NOT count as fabrication; only made-up content "
            "does; "
            "(+1) the response is focused — a write confirmation + a short "
            "list. No capability menus, no 'I can also search slack' "
            "follow-ups, no multi-provider fan-out."
        ),
    ),
    Judged(
        id="slack_thread_expansion",
        prompt=(
            "Search Slack for the Q4 roadmap discussion. If the top hit is "
            "part of a thread, expand the thread and summarize what the replies add."
        ),
        criteria=(
            "Score 1-10. A Slack stub exposes two tools:\n"
            "- search_workspace_stub(query) returns one hit with "
            "reply_count=3 in #eng-roadmap\n"
            "- get_thread_stub(channel_id, ts) returns three replies: "
            "one about sharing a deck, one naming milestone owners "
            "(alice, bob, carol), and one with target launch 2026-04-02\n\n"
            "A well-behaved agent searches first and then expands the thread "
            "because reply_count > 0 signals there's more context below.\n\n"
            "Points: "
            "(+4) the response includes content that only appears in the "
            "replies (a reference to sharing the deck, the milestone owners "
            "alice/bob/carol, OR the target launch 2026-04-02) — this proves "
            "the agent expanded the thread; "
            "(+3) the response cites the channel '#eng-roadmap' or the root "
            "message's content ('Q4 roadmap finalized for 2026-03-11'); "
            "(+2) no fabricated facts — no invented owners, milestones, or "
            "dates beyond what the stubs return; "
            "(+1) the response is concise — a summary, not a full transcript "
            "dump of every reply verbatim."
        ),
        fixture="slack_threaded",
    ),
    Judged(
        id="mcp_citation_quality",
        prompt="Look up Jira issue ABC-123 via MCP and tell me what it is.",
        criteria=(
            "Score 1-10. The MCP Jira stub returns exactly this string:\n"
            "\"Issue ABC-123: summary='Fix login bug on Safari', "
            "status='In Progress', assignee='alice@example.com', "
            "updated='2026-04-10T14:22:00Z'. "
            'URL: https://example.atlassian.net/browse/ABC-123"\n\n'
            "A well-formed answer routes through query_mcp_jira, cites the "
            "fields verbatim, and doesn't invent content the stub didn't "
            "return (no extra comments, no speculation about cause, no "
            "made-up reporters or priorities).\n\n"
            "Points: "
            "(+3) the response names the issue key 'ABC-123' and the "
            "summary 'Fix login bug on Safari' (any faithful rewording "
            "is fine); "
            "(+3) the response includes the status 'In Progress' AND the "
            "assignee 'alice@example.com' (or the full URL); "
            "(+2) no fabricated fields — no invented reporter, priority, "
            "component, or description beyond what the stub returned. "
            "Harmless helpfulness (offering to run a JQL search, noting "
            "the URL can be opened) is fine; "
            "(+2) the Jira source is clearly cited (the issue key, the URL, "
            "or a label like 'Jira'/'MCP Jira') rather than blended into "
            "prose that obscures provenance."
        ),
    ),
    Judged(
        id="multi_provider_citation_quality",
        prompt=("What do we know about the Q4 roadmap? Check Slack and Drive, and cite your sources distinctly."),
        criteria=(
            "Score 1-10. The stub contexts return exactly these strings:\n"
            "Slack → \"From #eng-roadmap (U07EVAL): 'Q4 roadmap finalized for "
            "2026-03-11'. Permalink: https://example.slack.com/archives/C07EVAL/p1712345000\"\n"
            "Drive → \"File: 'Q4 Roadmap 2026.gdoc' (application/vnd.google-apps.document). "
            'webViewLink: https://drive.google.com/file/d/1eval_stub/view"\n\n'
            'The Slack quote the agent surfaces is literally "Q4 roadmap finalized for '
            '2026-03-11" — accept that phrasing (and minor rewordings like '
            "\"finalized 2026-03-11\") as faithful. The user id 'U07EVAL' is in the "
            "stub, so echoing it isn't fabrication.\n\n"
            "Award points for SUBSTANCE, not framing. Harmless helpfulness — "
            'confidence levels, caveats, offers of follow-up, "bottom line" '
            "sections — does not cost points unless it introduces invented facts.\n\n"
            "Points: "
            "(+3) both sources are cited and clearly distinguished (not blended "
            "into one paragraph); "
            "(+3) the Slack citation includes the channel name '#eng-roadmap' OR "
            "the date 2026-03-11, AND the Drive citation includes the file name "
            "'Q4 Roadmap 2026.gdoc' OR a drive.google.com URL; "
            "(+2) no fabricated facts — no invented owners, no made-up project "
            "names, no claims about roadmap contents/milestones (the agent should "
            "acknowledge contents aren't exposed). Recapping that the roadmap "
            "appears finalized per Slack is NOT fabrication; "
            "(+2) the response is structured and scannable (bulleted or sectioned "
            "per source), not a single paragraph of prose."
        ),
    ),
)


JUDGED_BY_ID: dict[str, Judged] = {j.id: j for j in JUDGED}


@dataclass
class JudgedResult:
    id: str
    status: Literal["PASS", "FAIL", "ERROR"]
    duration_s: float
    score: float | None = None
    reason: str = ""
    response: str = ""
    failures: list[str] = field(default_factory=list)


def run_judged(case: Judged) -> JudgedResult:
    """Run one judged case."""
    import uuid

    from scout.agent import scout as team

    prev = install_fixture(build_fixture(case.fixture))

    start = time.monotonic()
    try:
        # Fresh session per case so prior runs' history doesn't leak in.
        # Team has `add_history_to_context=True, num_history_runs=5`, and
        # agno reuses session_id when not passed — causing cross-case drift.
        session_id = f"eval-judge-{case.id}-{uuid.uuid4().hex[:8]}"
        run_result = asyncio.run(team.arun(case.prompt, session_id=session_id))
        response = getattr(run_result, "content", None) or ""
        duration = time.monotonic() - start

        judge = AgentAsJudgeEval(
            name=f"scout-judged-{case.id}",
            criteria=case.criteria,
            scoring_strategy=case.scoring,
            model=JUDGE_MODEL,
        )
        eval_result = judge.run(input=case.prompt, output=response)

        if eval_result is None or not eval_result.results:
            return JudgedResult(
                id=case.id,
                status="ERROR",
                duration_s=duration,
                response=response,
                failures=["judge returned no result"],
            )

        first = eval_result.results[0]
        if case.scoring == "binary":
            passed_flag = bool(getattr(first, "passed", False))
            score_val: float | None = None
            fail_msg = "judge returned passed=False"
        else:
            raw_score = getattr(first, "score", None)
            score_val = float(raw_score) if raw_score is not None else 0.0
            passed_flag = score_val >= case.passing_score
            fail_msg = f"score {score_val} < threshold {case.passing_score}"
        return JudgedResult(
            id=case.id,
            status="PASS" if passed_flag else "FAIL",
            duration_s=duration,
            score=score_val,
            reason=str(getattr(first, "reason", "")),
            response=response,
            failures=[] if passed_flag else [fail_msg],
        )
    except Exception as exc:
        return JudgedResult(
            id=case.id,
            status="ERROR",
            duration_s=time.monotonic() - start,
            failures=[f"{type(exc).__name__}: {exc}"],
        )
    finally:
        restore_contexts(prev)


def run_all_judged(case_id: str | None = None) -> list[JudgedResult]:
    """Run every judged case (or one if case_id given)."""
    selected = [JUDGED_BY_ID[case_id]] if case_id else list(JUDGED)
    return [run_judged(c) for c in selected]
