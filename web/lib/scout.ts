// API client for Scout's AgentOS backend.
//
// All requests go to NEXT_PUBLIC_SCOUT_API_URL (defaults to http://localhost:8000).
// AgentOS already allows http://localhost:3000 in its CORS list.

export const SCOUT_API_URL =
  process.env.NEXT_PUBLIC_SCOUT_API_URL || "http://localhost:8000";

export const SCOUT_USER_ID =
  process.env.NEXT_PUBLIC_SCOUT_USER_ID || "scout-web-user";

export type ContextStatus = {
  id: string;
  name: string;
  ok: boolean;
  detail: string;
};

export type ContextAnswer = {
  text: string | null;
  results: Array<{
    id: string;
    name: string;
    uri: string | null;
    source: string | null;
    snippet: string | null;
  }>;
};

export type AgentRunResponse = {
  run_id?: string;
  session_id?: string;
  content?: string;
  [k: string]: unknown;
};

export async function listContexts(): Promise<ContextStatus[]> {
  const res = await fetch(`${SCOUT_API_URL}/contexts`, {
    method: "GET",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`/contexts ${res.status}`);
  return res.json();
}

export async function queryContext(
  contextId: string,
  question: string,
): Promise<ContextAnswer> {
  const res = await fetch(
    `${SCOUT_API_URL}/contexts/${encodeURIComponent(contextId)}/query`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, user_id: SCOUT_USER_ID }),
    },
  );
  if (!res.ok) throw new Error(`/contexts/${contextId}/query ${res.status}`);
  return res.json();
}

// One automatic retry on transient failures (intermittent SSL handshake errors
// from upstream Google APIs surface as ssl WRONG_VERSION_NUMBER on the first
// call after warmup). Briefing cards use this; chat does not.
export async function queryContextWithRetry(
  contextId: string,
  question: string,
): Promise<ContextAnswer> {
  try {
    const ans = await queryContext(contextId, question);
    if (looksLikeTransientError(ans.text || "")) {
      return queryContext(contextId, question);
    }
    return ans;
  } catch (err) {
    return queryContext(contextId, question);
  }
}

function looksLikeTransientError(text: string): boolean {
  if (!text) return false;
  const t = text.toLowerCase();
  return (
    t.includes("wrong_version_number") ||
    t.includes("ssl error") ||
    t.includes("ssl: ") ||
    t.includes("connection reset") ||
    (t.includes("failed") && t.includes("retry"))
  );
}

// Raw Google Calendar event shape — only the fields the week view actually
// reads. The endpoint passes through Google's response unchanged.
export type CalendarEvent = {
  id: string;
  summary?: string;
  description?: string;
  htmlLink?: string;
  hangoutLink?: string;
  location?: string;
  status?: string;
  start: { dateTime?: string; date?: string; timeZone?: string };
  end: { dateTime?: string; date?: string; timeZone?: string };
  attendees?: Array<{ email?: string; displayName?: string; responseStatus?: string }>;
  conferenceData?: { entryPoints?: Array<{ uri?: string; entryPointType?: string }> };
};

export type UnreadEmail = {
  id: string;
  thread_id?: string;
  from: string | null;
  subject: string | null;
  date: string | null;
  snippet: string | null;
};

export type EmailMessage = {
  id: string;
  thread_id: string;
  from: string | null;
  to: string | null;
  cc: string | null;
  subject: string | null;
  date: string | null;
  snippet: string | null;
  is_unread: boolean;
  body_text: string;
};

export type EmailThread = {
  id: string;
  messages: EmailMessage[];
};

export async function fetchEmailThread(threadId: string): Promise<EmailThread> {
  const res = await fetch(
    `${SCOUT_API_URL}/gmail/thread/${encodeURIComponent(threadId)}`,
    { cache: "no-store" },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `/gmail/thread ${res.status}`);
  }
  return res.json();
}

export async function markEmail(
  messageId: string,
  action: "read" | "unread",
): Promise<void> {
  const res = await fetch(
    `${SCOUT_API_URL}/gmail/message/${encodeURIComponent(messageId)}/mark`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action }),
    },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `mark ${action} ${res.status}`);
  }
}

export async function fetchUnreadEmails(count = 8): Promise<UnreadEmail[]> {
  const url = new URL(`${SCOUT_API_URL}/gmail/unread`);
  url.searchParams.set("count", String(count));
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `/gmail/unread ${res.status}`);
  }
  const data = (await res.json()) as { emails: UnreadEmail[] };
  return data.emails ?? [];
}

export type Followup = {
  id: number;
  title: string;
  notes: string | null;
  due_at: string | null;
  status: "pending" | "done" | "dropped";
  tags: string[];
  created_at: string;
};

export async function fetchFollowups(
  status: "pending" | "done" | "dropped" = "pending",
): Promise<Followup[]> {
  const url = new URL(`${SCOUT_API_URL}/crm/followups`);
  url.searchParams.set("status", status);
  url.searchParams.set("user_id", SCOUT_USER_ID);
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`/crm/followups ${res.status}`);
  const data = (await res.json()) as { followups: Followup[] };
  return data.followups ?? [];
}

export async function createFollowup(input: {
  title: string;
  notes?: string;
  due_at?: string | null;
}): Promise<Followup> {
  const res = await fetch(`${SCOUT_API_URL}/crm/followups`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      title: input.title,
      notes: input.notes || null,
      due_at: input.due_at || null,
      user_id: SCOUT_USER_ID,
    }),
  });
  if (!res.ok) throw new Error(`POST /crm/followups ${res.status}`);
  return res.json();
}

export async function updateFollowupStatus(
  id: number,
  status: "pending" | "done" | "dropped",
): Promise<Followup> {
  const res = await fetch(`${SCOUT_API_URL}/crm/followups/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`PATCH /crm/followups/${id} ${res.status}`);
  return res.json();
}

export async function fetchCalendarEvents(
  fromIso: string,
  toIso: string,
): Promise<CalendarEvent[]> {
  const url = new URL(`${SCOUT_API_URL}/calendar/events`);
  url.searchParams.set("from", fromIso);
  url.searchParams.set("to", toIso);
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      body.error || body.detail || `/calendar/events ${res.status}`,
    );
  }
  const data = (await res.json()) as { events: CalendarEvent[] };
  return data.events ?? [];
}

export async function runAgent(
  message: string,
  sessionId?: string,
): Promise<AgentRunResponse> {
  const form = new FormData();
  form.append("message", message);
  form.append("stream", "false");
  form.append("user_id", SCOUT_USER_ID);
  if (sessionId) form.append("session_id", sessionId);

  const res = await fetch(`${SCOUT_API_URL}/agents/scout/runs`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`/agents/scout/runs ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

// Streaming variant — uses Server-Sent Events from AgentOS. The endpoint
// requires multipart form data which EventSource can't send (it's GET-only),
// so we use fetch + manual SSE parsing on the response body stream.
export type StreamEvent =
  | { kind: "started"; sessionId?: string }
  | { kind: "content"; delta: string }
  | { kind: "tool_started"; name: string }
  | { kind: "tool_completed"; name: string }
  | { kind: "completed" }
  | { kind: "error"; message: string };

export async function streamAgent(
  message: string,
  sessionId: string | undefined,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append("message", message);
  form.append("stream", "true");
  form.append("user_id", SCOUT_USER_ID);
  if (sessionId) form.append("session_id", sessionId);

  const res = await fetch(`${SCOUT_API_URL}/agents/scout/runs`, {
    method: "POST",
    body: form,
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    onEvent({
      kind: "error",
      message: `/agents/scout/runs ${res.status}: ${text.slice(0, 200)}`,
    });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const parsed = parseSseBlock(block);
        if (!parsed) continue;
        dispatchSseEvent(parsed.event, parsed.data, onEvent);
      }
    }
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    onEvent({ kind: "error", message: String((err as Error).message || err) });
  }
}

function parseSseBlock(
  block: string,
): { event: string; data: string } | null {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trimStart();
  }
  if (!data) return null;
  return { event, data };
}

function dispatchSseEvent(
  event: string,
  rawData: string,
  onEvent: (e: StreamEvent) => void,
) {
  let data: { [k: string]: unknown };
  try {
    data = JSON.parse(rawData);
  } catch {
    return;
  }
  switch (event) {
    case "RunStarted":
      onEvent({
        kind: "started",
        sessionId: typeof data.session_id === "string" ? data.session_id : undefined,
      });
      return;
    case "RunContent":
    case "RunIntermediateContent":
      if (typeof data.content === "string" && data.content.length > 0) {
        onEvent({ kind: "content", delta: data.content });
      }
      return;
    case "ToolCallStarted":
      onEvent({ kind: "tool_started", name: extractToolName(data) });
      return;
    case "ToolCallCompleted":
      onEvent({ kind: "tool_completed", name: extractToolName(data) });
      return;
    case "RunCompleted":
      onEvent({ kind: "completed" });
      return;
    case "RunError":
      onEvent({
        kind: "error",
        message:
          typeof data.content === "string" ? data.content : "agent error",
      });
      return;
  }
}

function extractToolName(data: { [k: string]: unknown }): string {
  // ToolCall events carry a `tool` object with a `tool_name` field, or a
  // `tools` array. We only need a label for the status line.
  const tool = data.tool as { tool_name?: string } | undefined;
  if (tool?.tool_name) return tool.tool_name;
  const tools = data.tools as Array<{ tool_name?: string }> | undefined;
  if (tools && tools.length > 0 && tools[0].tool_name) return tools[0].tool_name;
  return "tool";
}
