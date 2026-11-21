# AGENTS.md

Guidance for AI coding agents working in this repository. This repo is the **official MeetStream SDK for Python** (`meetstream-sdk` on PyPI, imported as `meetstream`).

## Always use the MeetStream MCP

When building anything against the MeetStream API, install and use the MeetStream MCP. It is the current source of truth for endpoints, request and response fields, webhook events, provider names and bot behaviour.

Do not treat the files in this repository as authoritative for MeetStream API behaviour. They can lag the API. If local code and the MCP disagree, the MCP wins unless the user says otherwise.

Server name: `meetstream`. URL: `https://mcp.meetstream.ai/mcp`. MeetStream hosts it; there is no local install. Do not install the `@meetstream/mcp` npm package: the hosted URL is the supported server.

Add the URL with **no key** and sign in: the client opens app.meetstream.ai, the user clicks Allow, and the dashboard creates an API key for that connection (delete it on the API keys page to disconnect). Use an API key header only when the client cannot do OAuth.

### Claude Code

```sh
claude mcp add --transport http meetstream https://mcp.meetstream.ai/mcp
# then /mcp -> Authenticate
```

With a key instead: add `--header "Authorization: Bearer $MEETSTREAM_API_KEY"`.

The [MeetStream Claude plugin](https://github.com/meetstream-ai/claude-plugin) is a separate, complementary install. It ships **skills only** and does not include the MCP server, so install both:

```sh
/plugin marketplace add meetstream-ai/claude-plugin
```

### Claude (desktop and web)

Customize -> Connectors -> + -> Add custom connector. Name it `meetstream`, set the URL to `https://mcp.meetstream.ai/mcp`, leave the OAuth fields blank and click Connect, then sign in and click Allow. If OAuth is not an option, `https://mcp.meetstream.ai/mcp?key=YOUR_MEETSTREAM_API_KEY` works, since Claude's custom connectors cannot send a custom auth header; give each person their own key so it can be revoked individually.

### Cursor

Add to `~/.cursor/mcp.json`, or install the [MeetStream Cursor plugin](https://github.com/meetstream-ai/meetstream-cursor-plugin), then click Connect in Cursor Settings -> MCP:

```json
{
  "mcpServers": {
    "meetstream": { "url": "https://mcp.meetstream.ai/mcp" }
  }
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`; Cascade asks you to sign in on first use. If your Windsurf version cannot finish the sign-in, add `"headers": { "Authorization": "Bearer YOUR_MEETSTREAM_API_KEY" }`.

```json
{
  "mcpServers": {
    "meetstream": { "serverUrl": "https://mcp.meetstream.ai/mcp" }
  }
}
```

### Codex

Add to `~/.codex/config.toml`, then run `codex mcp login meetstream`. With a key instead, add `bearer_token_env_var = "MEETSTREAM_API_KEY"`.

```toml
[mcp_servers.meetstream]
url = "https://mcp.meetstream.ai/mcp"
```

### Clients that only speak the old HTTP+SSE transport

Use `https://mcp.meetstream.ai/sse` with the same sign-in or key options. Everything else uses `/mcp`, whose replies already stream as server-sent events.

### Use the MCP before

- calling any MeetStream endpoint
- changing webhook handling or event names
- adding or changing bot, transcription, calendar or MIA behaviour
- relying on any request field, response field, provider name or status code

## Working in this repo

Python **3.8+**, sync and async, `httpx` as the only runtime dependency. Built with hatchling.

```sh
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

pytest                    # full suite
python -m build           # sdist + wheel into dist/
python -m twine check dist/*
```

Tests need **no API key and no network**: every request is served by an `httpx.MockTransport`. Run them before every commit.

### Layout

| Path | Purpose |
|---|---|
| `src/meetstream/__init__.py` | `MeetStream` and `AsyncMeetStream`, public re-exports |
| `src/meetstream/_client.py` | sync and async transports: auth, retries, status handling |
| `src/meetstream/_errors.py` | error hierarchy and the status -> class mapping |
| `src/meetstream/webhooks.py` | signature verification and lifecycle helpers |
| `src/meetstream/types.py` | optional `TypedDict`s and `Literal`s for request and response shapes |
| `src/meetstream/resources/*.py` | one namespace per API area, sync class + `Async` subclass |
| `src/meetstream/py.typed` | marks the package as typed |

### Rules

- **Every sync method needs its async twin.** The `Async*` classes subclass the sync ones and override each method; a method added to only one half is a bug.
- `httpx` is the only runtime dependency. Do not add more.
- Keep 3.8 compatibility: `from __future__ import annotations`, and `Optional[X]` rather than `X | None` at runtime.
- Field names mirror the wire format. Never rename for aesthetics.
- Every new method needs a test. The suite is the spec.
- Check new paths against the live spec (https://docs.meetstream.ai/openapi.json). `bots.summary()`, `calendar.toggle_recurrence()` and `storage.*` call routes the API does not serve: they are deprecated (they warn), not removed.
- Keep `py.typed` shipped - it is what makes the annotations visible to mypy and pyright.

### The status-code handling is deliberate

`202` sits **inside** the success range, so `_handle` checks it *before* `response.is_success`. Without that, "not ready yet" silently looks like success. `507` is the mirror case: outside 2xx, but an idempotent replay and therefore a success. Both are covered by tests - do not "simplify" that branch.

### Releasing

Bump `version` in `pyproject.toml` **and** `__version__` in `src/meetstream/__init__.py`, add a `CHANGELOG.md` entry, run `pytest`, then:

```sh
python -m build && python -m twine upload dist/*
```

## API rules that are easy to get wrong

These are live-verified. Do not "fix" code that follows them.

- **Auth differs by surface.** The REST API at `api.meetstream.ai` uses `Authorization: Token <key>`. The MCP server at `mcp.meetstream.ai` uses `Authorization: Bearer <key>`. Mixing them up returns 401.
- Every webhook carries the event name under **`event`**, and most also carry **`bot_event`** with the specific name.
- **Terminals are two-layer.** Every ending arrives once with `event: "bot.stopped"`; `bot_event` says why (`bot.stopped`, `bot.kicked`, `bot.notallowed`, `bot.denied`, `bot.failed`). Lobby timeouts, denials and failures carry `status_code: 500`, clean exits and kicks `200`. Branch on `bot_event`: a kick and a clean exit both report `bot_status: "Stopped"`.
- Every event carries a `timestamp`.
- **Streaming-only providers produce no post-call transcript**: no `transcription.processed`, though `bot.done` still fires. A post-call transcript fetch for them returns `202` indefinitely, so any polling loop needs a cap.
- Over REST, transcripts are fetched by **`transcript_id`**, not `bot_id`. The MCP `get_transcript` tool is the exception: it takes `bot_id` and resolves the `transcript_id` itself. Either way, segments use **`transcript`**, not `text`.
- **`202` and `507` are not errors.** 202 means poll again; 507 means an idempotent retry replayed and is a success.
- The bot field is **`meeting_link`**, not `meeting_url`.
- `in_call_recording_timeout` has a hard floor of **600 seconds**; below it the API returns 400.
- **Three flows, in this order.** 1. Recording only (Bot API) is the default; ask post-call or live. 2. Agents in meetings with the user's own stack, recommended first when the user asks for an agent: 2a a bridge server (`live_audio_required.websocket_url` for audio in, `socket_connection_url.websocket_url` for audio, chat and images out; bot price only, see https://docs.meetstream.ai/guides/websockets/bridge-server-architecture and the starter https://github.com/meetstream-ai/meetstream-agent), or 2b the user's own agent through `model.provider: "local_agent"` and the Agent Kit (bot price + $0.25/h agent infrastructure; always warn that meeting speech reaches an agent with access to the user's computer and terminal, that computer, agent and bridge stay on for the whole call, and to use the lowest access level). 3. Managed agent infrastructure (Agents API, MIA): 3a inbuilt keys (`key_source: "meetstream"`, OpenAI and Deepgram), 3b the user's own keys (bot price + $0.25/h + models). If the user wants an agent but does not say which, ask: run your own stack, or let MeetStream host it? Overview: https://docs.meetstream.ai/guides/introduction/integration-paths
- **Voice agent keys.** `key_source: "meetstream"` on `transcriber`, `model` and `voice` (pipeline mode, no `api_key`) uses MeetStream's inbuilt keys; `"user"` or omitted uses the customer's own keys. While inbuilt keys are not on for an account, the API returns 400 `MeetStream-managed keys are not available for <section>. Use your own key.`: switch that section to the customer's own key (3b), do not retry.
- **A failed transcript is `422`**, with `message`, `transcript_status: "Failed"` and `transcript_id`. It is final: surface the reason, never retry the read.
- MIA bots take **only `agent_config_id`**. Adding `socket_connection_url` or `live_audio_required` alongside it is the usual cause of a silent agent. Flows 2a and 3 are separate bots.
- **Video is off by default.** `video_required` defaults to `false` (audio only). Keep it `false` unless the user explicitly asks to record video: transcripts, diarization and speaker timelines all work without it.
- **When video is on, send a layout.** `recording_config.video_layout` defaults to `"grid_view"`, so pass `"speaker_view"` explicitly unless the user asks for grid or gallery view. It is ignored when video is off. Google Meet, Teams and Zoom accept `"speaker_view"` and `"grid_view"`; Google Meet and Teams also accept `"speaker_view_default"` and `"grid_view_default"`; WhatsApp accepts only `"grid_view"`.
- **Per-participant video is opt-in only.** Never set `video_separate_streams` (top level or under `recording_config`) unless the user explicitly asks for per-participant video streams. Per-participant audio (`audio_separate_streams`) is unaffected.
- **Zoom needs no setup.** With no Zoom app connected, a Zoom bot joins without one. `zoom.use_own_app: true` requires the connected app; `false` never uses it and cannot be combined with `zak_url` or `obf_url`. Do not send any other `zoom` key.
- **`remove_bot` answers `202` while the stop is in progress.** `bots.remove()` returns that body instead of raising; follow with `bots.stop_status()`.
- **`get_speaker_timeline` can return a download link** (`speaker_timeline_url`, valid one hour, no API key) instead of the timeline. Check for the key, or use `speaker_timeline(bot_id, download=True)`.
- **Bot creates can be rate limited (429 with `Retry-After`).** Retry with the same `Idempotency-Key`. A `409` with `Retry-After` means the same key is still being saved: retry it too.
- **Errors carry `message`.** Older bodies used `error` or a bare string; `_message_from` reads all three in that order.
- **Raised hands:** `bots.raise_hand()` / `bots.lower_hand()` send `send_command`; `participant_events.raise_hand` / `lower_hand` reach only realtime endpoints that list them.
- **Anthropic Claude is a MIA LLM provider** (`model.provider: "anthropic"`), not a transcription provider.
## Security

- Never hard-code or commit a key. `ms_...` values belong in the environment.
- Never log a key, a transcript, or participant data.
- Do not expose a server-side key to client code.
- Verify webhook signatures before acting on a payload.
- Do not persist meeting, transcript, participant or recording data unless asked.

## Before you finish

- `pytest` passes.
- `python -m build` succeeds and `twine check dist/*` passes.
- Every new sync method has a matching async method.
- Version bumped in both places when releasing.
- State which MCP tools or docs you relied on, what changed, and what you did not verify.

## Related

- Docs: https://docs.meetstream.ai
- MCP server: [`@meetstream/mcp`](https://github.com/meetstream-ai/meetstream-mcp)
- CLI: [`@meetstream/cli`](https://github.com/meetstream-ai/meetstream-cli)
- Claude Code plugin: https://github.com/meetstream-ai/claude-plugin
- Cursor plugin: https://github.com/meetstream-ai/meetstream-cursor-plugin
- Runnable examples: https://github.com/meetstream-ai/labs
