<div align="center">

# MeetStream SDK for Python

**Send AI bots into Zoom, Google Meet and Microsoft Teams.** Record, transcribe, summarize and stream meetings, and run [voice agents](#build-tracks) that talk back.

[![PyPI](https://img.shields.io/pypi/v/meetstream-sdk?style=flat-square&color=fd6316)](https://pypi.org/project/meetstream-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/meetstream-sdk?style=flat-square)](https://pypi.org/project/meetstream-sdk/)
[![Docs](https://img.shields.io/badge/docs-docs.meetstream.ai-45689f?style=flat-square)](https://docs.meetstream.ai)
[![Typed](https://img.shields.io/badge/typed-py.typed-3178c6?style=flat-square)](#typed)
[![License](https://img.shields.io/badge/license-MIT-867c72?style=flat-square)](LICENSE)

</div>

```bash
pip install meetstream-sdk
```

Python 3.8+. Sync and async. Ships type information.

## Build tracks

Pick a track before you write code. Guide: [Integration paths](https://docs.meetstream.ai/guides/introduction/integration-paths).

| Track | What it is | Price per meeting hour |
|---|---|---|
| **1. Recording bot** | The bot joins Zoom, Google Meet or Microsoft Teams, records and transcribes. **1a. Non-realtime (post-call):** wait for the bot to finish, then get the transcript, recordings and participants; webhooks tell you when. **1b. Real-time (live):** live transcription webhook, real-time audio WebSocket, meeting control socket, chat, raise or lower hand. Start here unless you want an agent in the meeting. | Bot price |
| **2. Bridge server** (your own stack, local) | The bot connects out to your server over two WebSockets: meeting audio in, and audio, chat and images out. You run your own speech-to-text, LLM and text-to-speech, free local models included. | Bot price only |
| **3. Agents API infra** (hosted by MeetStream) | MeetStream hosts the voice agent (API name: MIA). **3a.** MeetStream's own, default keys. **3b.** Bring your own agent infra (LiveKit): coming soon. **3c.** Bring your own keys. **3d.** Local agent (your own agent CLI): coming soon. | Bot price + $0.25 agent infrastructure + the models you pick |

Bot price: $0.35 per recording hour ($0.25 at volume). The MeetStream transcription add-on is $0.10 per hour; it is waived when you use your own provider key. See [pricing](https://meetstream.ai/pricing).

Want an agent but not sure which track? Run your own stack (track 2, any models, local ones included), or let MeetStream host it (track 3a or 3c, no infrastructure work).

### Track 1: Recording bot

First decide: do you need the transcript **after the call** (1a), or something **during the call** (1b)?

**1a. Non-realtime transcription (post-call):** create a bot, wait for webhooks, then read the transcript, recordings and participants.

```python
import os
from meetstream import MeetStream

meetstream = MeetStream()  # reads MEETSTREAM_API_KEY

# 1. Send the bot. Only meeting_link is required.
bot = meetstream.bots.create({
    "meeting_link": "https://meet.google.com/abc-defg-hij",
    "bot_name": "Notetaker",
    "video_required": False,  # audio only (the API default); send True only when video is needed
    "callback_url": "https://you.example.com/webhook?token=" + os.environ["MEETSTREAM_WEBHOOK_SECRET"],  # 2. lifecycle webhooks (unsigned: check the token)
    "recording_config": {
        "transcript": {"provider": {"meetstream": {"language": "auto"}}}  # no provider key needed
        # Recording video? Add "video_layout": "speaker_view" (the API defaults to grid_view).
    },
})

# 3. Bounded wait for the transcript (also stops at once if it failed).
transcript = meetstream.transcripts.wait_for(bot["transcript_id"])
audio = meetstream.bots.audio(bot["bot_id"])
people = meetstream.bots.participants(bot["bot_id"])
```

**1b. Real-time transcription (live):** use the live transcription webhook (`live_transcription_required` with a `*_streaming` provider), the real-time audio WebSocket (`live_audio_required`), the meeting control socket (`socket_connection_url`), chat (`bots.send_message`) and raise or lower hand (`bots.raise_hand` / `bots.lower_hand`, which is `POST /api/v1/bots/{bot_id}/send_command` with `{"command": "raise_hand"}`).

```python
meetstream.bots.create({
    "meeting_link": "https://zoom.us/j/123456789",
    "recording_config": {"transcript": {"provider": {"meetstream_streaming": {"transcription_mode": "sentence"}}}},
    "live_transcription_required": {"webhook_url": "https://you.example.com/live"},
})
meetstream.bots.raise_hand(bot_id)  # the bot must be in the meeting (409 otherwise)
```

`transcription_mode` on a `*_streaming` provider is `raw` (the default: interim POSTs with `is_final: false`, then the final one), `sentence` (finals only) or `word_level` (one word per POST). Type the POST body with `meetstream.types.LiveTranscriptPayload` and keep only final text with `is_final_segment(payload)`. `meeting_captions` sends `LiveCaptionPayload` (`{"type": "caption", "bot_id", "caption": {"text", "speakerName"}}`) instead. Live transcript POSTs are not signed: protect the URL with a token (see [Webhooks](#webhooks)).

Get a key at [app.meetstream.ai/api-key](https://app.meetstream.ai/api-key).

### Track 2: Bridge server (your own stack, local)

The bot opens two WebSockets to your server: live meeting audio comes in on `live_audio_required.websocket_url`, and the meeting control socket (`socket_connection_url.websocket_url`) carries the audio, chat, images and interrupts that you send back. Your server runs the speech-to-text, LLM and text-to-speech. MeetStream charges the bot price only: no agent infrastructure and no model tokens. To run the bridge on a laptop, expose it with a local tunnel (for example ngrok or cloudflared) and use the tunnel's `wss://` URL.

```python
meetstream.bots.create({
    "meeting_link": "https://meet.google.com/abc-defg-hij",
    "bot_name": "Assistant",
    "live_audio_required": {"websocket_url": "wss://your-tunnel.example.com/bridge/audio"},  # audio in
    "socket_connection_url": {"websocket_url": "wss://your-tunnel.example.com/bridge"},      # audio, chat, images out
})
```

Models you can use (free to run locally; check each model's license before commercial use):

- Speech-to-text: whisper.cpp or faster-whisper (Whisper models), NVIDIA Parakeet (parakeet-mlx on Apple silicon), Vosk, Moonshine.
- LLM: a local model through Ollama, LM Studio or llama.cpp (Llama, Qwen, Gemma, Mistral), or the model of the harness you already use.
- Text-to-speech: Piper, Kokoro, Chatterbox, macOS `say`.

Starter: [MeetStream Bridge](https://github.com/meetstream-ai/meetstream-agent) (FastAPI, OpenAI Realtime by default; swap in local models). Guides: [Bridge server architecture](https://docs.meetstream.ai/guides/websockets/bridge-server-architecture), [Real-time audio streaming](https://docs.meetstream.ai/guides/websockets/real-time-audio-streaming), [Meeting control patterns](https://docs.meetstream.ai/guides/websockets/meeting-control-patterns).

### Track 3: Agents API infra (hosted by MeetStream)

MeetStream hosts the voice agent (API name: MIA). 1. Save an agent config. 2. Send a bot with its `agent_config_id`. Nothing else is needed on the bot.

```python
agent = meetstream.mia.create({
    "agent_name": "Meeting assistant",
    "mode": "pipeline",
    "transcriber": {"provider": "deepgram", "model": "nova-3", "key_source": "meetstream"},
    "model": {"provider": "openai", "model": "gpt-4.1", "key_source": "meetstream",
              "system_prompt": "You are a helpful meeting assistant. Keep answers short.",
              "first_message": "Hi, I'm an AI assistant on this call."},
    "voice": {"provider": "openai", "voice_id": "coral", "key_source": "meetstream"},
})

meetstream.bots.create({"meeting_link": meeting_link, "agent_config_id": agent["agent_config_id"]})
```

- **3a. MeetStream's own, default keys.** Set `"key_source": "meetstream"` on each pipeline section (`transcriber`, `model`, `voice`), with no `api_key`. Inbuilt keys work in pipeline mode only: Deepgram (speech-to-text) and OpenAI (LLM and voice). Realtime mode runs on OpenAI and needs your own OpenAI key. Any other provider: bring your own key (3c). The easiest choice if you want MeetStream to host everything.
- **3b. Bring your own agent infra (LiveKit).** Coming soon. Not available yet.
- **3c. Bring your own keys.** Add your provider keys (OpenAI, Anthropic, Deepgram, ElevenLabs and others in the docs) under Integrations, and pick any supported model. Use `"key_source": "user"` or leave it out. Your provider bills you for model usage.
- **3d. Local agent (your own agent CLI).** Coming soon. Not available in production yet. Your own agent (for example Claude Code, Codex or Hermes) will write what the voice agent says, through `meetstream setup` and `meetstream agent serve` over the MeetStream relay (no tunnel) and `model.provider: "local_agent"`. When it ships, meeting speech will reach an agent that has access to your computer and terminal, so a participant can try prompt injection: use the lowest access level.
- **Price:** bot price + $0.25 agent infrastructure + the per-hour price of each model you pick (with 3c, your provider bills the models). The dashboard agent editor shows the rate before the bot runs. See [Voice agent pricing and keys](https://docs.meetstream.ai/guides/mia/pricing-and-keys) and the [MIA API guide](https://docs.meetstream.ai/guides/mia/mia-api-guide).

If inbuilt keys are not on for your account yet, the API answers `400` with `MeetStream-managed keys are not available for <section>. Use your own key.` Check with `is_inbuilt_keys_unavailable(e)`, then use your own key for that section (3c). Do not retry the same request.

A hosted agent bot takes only `agent_config_id`. Never add `live_audio_required` or `socket_connection_url` to it: that is the usual cause of a silent agent. A bridge server (track 2) is a separate bot.

## Async client

```python
from meetstream import AsyncMeetStream

async with AsyncMeetStream() as meetstream:
    bot = await meetstream.bots.create({"meeting_link": "https://zoom.us/j/123"})
    status = await meetstream.bots.status(bot["bot_id"])
```

## Why this SDK

The MeetStream API has a handful of behaviours that look like bugs until you know them. This SDK encodes all of them so you do not rediscover them in production.

| The trap | What the SDK does |
|---|---|
| **`202` sits inside the 2xx range** and means "not ready yet", not success | Raises `NotReadyError` instead of handing you an empty body |
| **`507` looks like a failure** but is an idempotent replay | Returns the original resource as success |
| **Streaming-only providers return `202` forever** - no post-call transcript ever exists | `wait_for()` is always bounded and tells you exactly why it gave up |
| **Transcripts are keyed by `transcript_id`**, not `bot_id` | `transcripts.get()` takes the right id |
| **Segments use `transcript`, not `text`** | Documented at every call site |
| **`remove_bot` is a `GET`**, and `202` there means "stop in progress" | `bots.remove()` handles both and returns the stop state |
| **Large speaker timelines come back as a download link** | `bots.speaker_timeline(bot_id, download=True)` always returns the timeline |
| **REST uses `Token`, the MCP server uses `Bearer`** | Correct scheme sent automatically |
| **MIA takes only `agent_config_id`** | Extra bridge fields are the usual cause of a silent agent |

## What you can do

<details open>
<summary><b>Bots</b> - lifecycle, media, live interaction</summary>

```python
meetstream.bots.create(params, idempotency_key=uuid)
meetstream.bots.list()
meetstream.bots.get(bot_id)           # same record as detail()
meetstream.bots.status(bot_id)
meetstream.bots.detail(bot_id)        # includes transcript_id
meetstream.bots.remove(bot_id)        # leave, keep the data; returns the stop state
meetstream.bots.stop_status(bot_id)   # progress of the stop, without stopping again
meetstream.bots.delete_data(bot_id)   # irreversible

meetstream.bots.audio(bot_id)
meetstream.bots.video(bot_id)
meetstream.bots.audio_streams(bot_id)       # per-participant audio
meetstream.bots.recording_streams(bot_id)   # per-participant video
meetstream.bots.screenshots(bot_id, limit=25, continuation_token=None)
meetstream.bots.screenshot(bot_id, screenshot_id)
meetstream.bots.wait_for_audio(bot_id)      # bounded

meetstream.bots.participants(bot_id)
meetstream.bots.chats(bot_id)
meetstream.bots.speaker_timeline(bot_id, download=True)   # follows the download link for large timelines

meetstream.bots.send_message(bot_id, "Recording has started.", metadata={"source": "app"})  # metadata optional
meetstream.bots.send_image(bot_id, "https://…/slide.png", display_duration=5)
meetstream.bots.send_image(bot_id, img=base64_png, display_duration=5)   # or base64, up to 5 MiB
meetstream.bots.pause_recording(bot_id)     # privacy window
meetstream.bots.resume_recording(bot_id)
meetstream.bots.raise_hand(bot_id)          # Google Meet, Zoom, Teams; response has hand_raised
meetstream.bots.lower_hand(bot_id)
meetstream.bots.send_command(bot_id, "raise_hand")   # the generic form
meetstream.bots.update_mia(bot_id, {"system_prompt": "..."}, wait_for_ack=True)   # live MIA agent
```

`bots.summary()` is deprecated: the API has no summary endpoint. Build summaries from the transcript.

New `create` options, all optional:

```python
meetstream.bots.create({
    "meeting_link": "https://zoom.us/j/123",
    "zoom": {"obf_url": "https://you.example.com/zoom/obf"},  # Zoom: join through your Zoom app with an OBF token
    "storage_id": "eu-archive",          # a storage destination saved in the dashboard
    "bot_camera_stream": {"websocket_url": "wss://you.example.com/signal"},   # your video on the bot's camera
    "automatic_leave": {"recording_permission_denied_timeout": 600},       # Zoom, 60-600
    "recording_config": {
        "transcript": {"provider": {"smallest": {"model": "pulse", "language": "en"}}},  # or smallest_streaming
        "realtime_endpoints": [{
            "type": "webhook", "url": "https://you.example.com/rt",
            "events": ["participant_events.raise_hand", "participant_events.lower_hand"],
        }],
    },
})
```

Zoom bots join through the customer's Zoom app (Meeting SDK) with an OBF token (on behalf of a user who is in the meeting, `zoom.obf_url`) or a ZAK token (a signed-in bot, `zoom.zak_url`), the way Zoom asks Meeting SDK apps to join since 2 March 2026. Setup: [Zoom Marketplace app setup](https://docs.meetstream.ai/guides/app-integrations/zoom-marketplace-app-setup) · [Zoom authenticated bots (ZAK and OBF)](https://docs.meetstream.ai/guides/app-integrations/zoom-authenticated-bots). On Google Meet and Teams, `video_layout` also accepts `"speaker_view_default"` and `"grid_view_default"` (the platform's own view).

</details>

<details open>
<summary><b>Transcripts</b></summary>

```python
meetstream.transcripts.get(transcript_id)
meetstream.transcripts.get_by_bot(bot_id)             # no transcript_id lookup needed
meetstream.transcripts.wait_for(transcript_id, timeout=900)
meetstream.transcripts.list_for_bot(bot_id)
meetstream.transcripts.transcribe_bot_audio(bot_id)   # rescue a streaming-only bot
```

Each segment names the speaker in `participant.name` and holds the text in `words[].text`:

```python
from meetstream import segment_speaker, segment_text

for segment in meetstream.transcripts.get(transcript_id):
    print(f"{segment_speaker(segment)}: {segment_text(segment)}")
```

</details>

<details open>
<summary><b>Calendar</b> - auto-join and scheduling</summary>

```python
meetstream.calendar.connect_google({
    "google_client_id": ..., "google_client_secret": ..., "google_refresh_token": ...,
})
meetstream.calendar.connect_outlook({...})
meetstream.calendar.list()                              # calendars on every connected account
meetstream.calendar.list_connections()                  # connected Google / Outlook accounts
meetstream.calendar.delete_connection("google", "me@acme.com", purge_events=False)
meetstream.calendar.disconnect({"provider": "google", "account_id": "me@acme.com"})
meetstream.calendar.events()
meetstream.calendar.schedule_event(event_id)
meetstream.calendar.list_scheduled_bots()
meetstream.calendar.reschedule_bot(bot_id, "2026-09-01T10:00:00Z")
meetstream.calendar.enable_auto_schedule()
```

</details>

<details open>
<summary><b>Agents API (MIA voice agents)</b></summary>

```python
meetstream.mia.create(config)                     # returns agent_config_id
meetstream.mia.get(agent_config_id)
meetstream.mia.list()
meetstream.mia.update(agent_config_id, {"agent": {"chat_input": True}})  # PUT: send whole blocks
meetstream.mia.delete(agent_config_id)
meetstream.mia.check_local_agent(agent_config_id) # track 3d (local agent), coming soon in production

# Attach it with ONE field. Adding socket_connection_url or
# live_audio_required alongside is the usual cause of a silent agent.
meetstream.bots.create({"meeting_link": meeting_link, "agent_config_id": agent_config_id,
                        "agent_config_params": {"customer": "Ana"}})

# Change a running agent. The saved config does not change.
meetstream.mia.update_live(bot_id, {"system_prompt": "..."}, wait_for_ack=True)  # same as bots.update_mia
```

Agent options from API v1.10.0:

```python
meetstream.mia.create({
    "agent_name": "Presenter",
    "mode": "pipeline",
    "transcriber": {"provider": "deepgram", "language": "es"},  # honoured; unset, "multi" or "auto" = detect
    "model": {"provider": "openai", "model": "gpt-4.1"},        # a vision-capable model for "screen"
    "voice": {"provider": "openai", "voice_id": "coral"},
    "agent": {
        "tools": ["screen"],            # Google Meet: present and work a live web page
        "chat_input": True,             # chat messages that name the agent are requests
        "quiet_actions": True,          # act without talking through each step
        "speak_only_when_asked": True,  # speak only when addressed by name
    },
})
```

The local agent (track 3d, `model.provider: "local_agent"`) is coming soon in production; see [Track 3](#track-3-agents-api-infra-hosted-by-meetstream).

Claude works as the LLM in pipeline mode with your Anthropic key: `"model": {"provider": "anthropic", "model": "claude-sonnet-5-5", "reasoning_effort": "low"}`.

`boostwords` on the transcriber fixes most "it mishears our company name" complaints, and `mcp_servers` is what turns a talking bot into one that can do work mid-call. Secrets come back masked (`****` plus the last four characters); sending a masked value back in `mia.update()` keeps the stored secret.

</details>

<details open>
<summary><b>Billing</b></summary>

```python
from meetstream import BalanceUnavailableError

try:
    balance = meetstream.billing.balance()  # GET /billing/balance, read only
    print(balance["balance_usd"])           # decimal string such as "12.34", or None for invoice accounts
except BalanceUnavailableError as e:
    print("See your balance at", e.billing_url)
```

The balance endpoint is available when it is on for your account. Until then it answers `404`, which the SDK raises as `BalanceUnavailableError` (not retried). Top up at [app.meetstream.ai/billing](https://app.meetstream.ai/billing). A create with low credits returns `403` `Low credits please recharge`; do not retry it in a loop.

</details>

<details>
<summary><b>Integrations</b> - Google and Teams signed-in bots, authenticated Zoom joins, Zoom Meeting Direct Connect, your own storage</summary>

```python
meetstream.google_logins.create_domain({...})
meetstream.google_logins.create({...})

# Teams signed-in bots: one concurrent bot per Microsoft account; bot_name is not applied
meetstream.teams_logins.create_domain({"domain": "bots.acme.com", "name": "Acme bots", "login_mode": "always"})
meetstream.teams_logins.create({
    "domain": "bots.acme.com",
    "email": "bot1@bots.acme.com",
    "password": os.environ["TEAMS_BOT_PASSWORD"],  # write-only, never returned
})
meetstream.bots.create({
    "meeting_link": "https://teams.microsoft.com/l/meetup-join/...",
    "bot_name": "Notetaker",  # required, though the Microsoft account's own name is shown
    "teams": {"login_required": True, "teams_login_domain": "bots.acme.com"},
})

# Authenticated Zoom joins: each URL is an HTTPS endpoint on your server that returns a fresh token
meetstream.bots.create({"meeting_link": link, "bot_name": "Notetaker", "zoom": {"zak_url": "https://you.example.com/zoom/zak"}})
meetstream.bots.create({"meeting_link": link, "bot_name": "Notetaker", "zoom": {"obf_url": "https://you.example.com/zoom/obf"}})

# Zoom Meeting Direct Connect: record a Zoom meeting with no bot in it, through your own Zoom app
session = meetstream.meeting_direct_connect.create({"zoom_rtms": {...}})   # from Zoom's meeting.rtms_started webhook
meetstream.meeting_direct_connect.get(session["bot_id"])
meetstream.meeting_direct_connect.leave(session["bot_id"])

# Your own storage: save destinations in the dashboard, then choose one per bot
meetstream.bots.create({"meeting_link": link, "storage_id": "eu-archive"})
```

`meetstream.storage` is deprecated: the routes it calls are not served by the API. Use `storage_id` instead.

Teams setup (dedicated Microsoft 365 tenant, account requirements, errors): [Teams signed-in bots guide](https://docs.meetstream.ai/guides/app-integrations/teams-signed-in-bots).

</details>

## Webhooks

**Only workspace webhook endpoints are signed.** They carry `X-MeetStream-Signature: sha256=<hex HMAC-SHA256 of the raw body>` and `X-MeetStream-Timestamp` (an ISO 8601 UTC string, for example `2026-11-19T14:30:00Z`). Per-bot `callback_url` deliveries and live transcript POSTs (`live_transcription_required.webhook_url`) are **never signed**. Do not run `parse_webhook` on them: it rejects every delivery.

**Per-bot `callback_url` and live URLs: put a secret token in the URL.**

```python
import hmac, os
from flask import Flask, request

SECRET = os.environ["MEETSTREAM_WEBHOOK_SECRET"]
# bots.create({..., "callback_url": f"https://you.example.com/webhook?token={SECRET}"})

@app.post("/webhook")
def webhook():
    if not hmac.compare_digest(request.args.get("token", ""), SECRET):
        return "", 401
    event = request.get_json()
    return "", 200
```

**Workspace webhook endpoints: verify the signature.** Pass the **raw** body - re-serializing a parsed dict changes key order and the signature will never match.

```python
from flask import Flask, request
from meetstream import parse_webhook, is_terminal, stop_reason, describe_stop

app = Flask(__name__)

@app.post("/webhook")
def webhook():
    try:
        event = parse_webhook(
            request.get_data(),                      # raw bytes, not request.json
            request.headers.get("X-MeetStream-Signature", ""),
            os.environ["WEBHOOK_SECRET"],
            timestamp=request.headers.get("X-MeetStream-Timestamp"),  # must match the signed body's timestamp
            tolerance_seconds=300,                   # optional replay window, off when not set
        )
    except ValueError:
        return "", 401

    if is_terminal(event):
        print(stop_reason(event), describe_stop(event))
    return "", 200   # ack fast, process async
```

Replay protection relies on the `timestamp` field inside the signed body: the HMAC covers the body, not the `X-MeetStream-Timestamp` header. With `tolerance_seconds` set, the delivery is rejected when the body's `timestamp` is missing or outside the window, or when the header is passed and does not match it.

**Raised hands** arrive as `participant_events.raise_hand` and `participant_events.lower_hand`, only on the realtime endpoints that list them in `events` (never on workspace webhooks). `hand_event(event)` returns `"raise_hand"`, `"lower_hand"` or `None`.

**Terminals are two-layer.** Every ending arrives once as `event: "bot.stopped"`, and `bot_event` says why: `bot.stopped`, `bot.kicked`, `bot.notallowed`, `bot.denied` or `bot.failed`. Not admitted, denied and failed carry `status_code: 500`. `stop_reason(event)` reads it for you (a kick and a clean exit both report `bot_status: "Stopped"`, so don't branch on that). `bot.error` is *not* terminal; the bot keeps running. `bot.done` is the final event on every path, streaming-only bots included. Every event carries a `timestamp`.

### MIA custom functions

A MIA agent calls each `agent.custom_functions` entry (annotate it with `meetstream.types.CustomFunction`) with the body `{"name", "bot": {"bot_id", "dynamic_vars", "agent_id"?, "speaker"?}, "args"}` and the `X-Bot-ID` header (`X-Agent-ID` when known). With `payload_args_only: true` the body is only `args`. `parse_custom_function_call` reads the shape you state (envelope by default; pass `payload_args_only=True` for an args-only function). It never guesses the shape from the body: arguments come from the model and could imitate an envelope. `bot_id` comes from the `X-Bot-ID` header first, and from `bot.bot_id` only in envelope mode when the header is missing.

```python
from meetstream import parse_custom_function_call

@app.post("/tools/lookup-order")
def lookup_order():
    call = parse_custom_function_call(request.get_data(), request.headers)
    return {"status": "shipped", "order_id": call["args"].get("order_id")}
```

**Every field, `X-Bot-ID` included, is unauthenticated.** These calls are not signed. Put a secret token in the function's `headers` (for example `{"Authorization": "Bearer <your secret>"}`) and check it in your endpoint before you trust the call.

## Errors

```python
from meetstream import NotReadyError, TranscriptFailedError, RateLimitError, BadRequestError, MeetStreamError

try:
    meetstream.transcripts.get(transcript_id)
except NotReadyError:
    ...                                  # 202 - poll again
except TranscriptFailedError as e:
    print(e.status, e.transcript_status, e.reason)  # 422: final; fix the cause, then transcribe_bot_audio()
except RateLimitError as e:
    time.sleep(e.retry_after or 5)       # from Retry-After; e.body has limit and window
except BadRequestError as e:
    print(e.message, e.code)             # the API's own message, and its code when sent
except MeetStreamError as e:
    print(e.status, e.request_id)
```

`e.message` reads the body's `message`, then `error`, then a bare string body. Prepaid accounts have a per-minute and per-hour limit on bot creates; over it the API answers 429 and creates no bot. A failed transcript answers `422` and raises `TranscriptFailedError` with `status`, `transcript_status`, `transcript_id` and `reason` (for example the provider rejected the API key, or a usage limit was reached). It is final and not retried: fix the cause, then call `transcripts.transcribe_bot_audio(bot_id)`.

`AuthenticationError` (401) means the header never arrived. `PermissionError` (403) means the key itself was rejected. That distinction saves a lot of debugging.

## Configuration

```python
meetstream = MeetStream(
    api_key=os.environ["MEETSTREAM_API_KEY"],
    base_url="https://api.meetstream.ai/api/v1",
    timeout=60.0,
    max_retries=2,          # 408, 429, 5xx and a 409 that sends Retry-After; honours Retry-After up to 60 s
    default_headers={},
    http_client=my_httpx_client,
)
```

| Variable | Purpose |
|---|---|
| `MEETSTREAM_API_KEY` | Your key. Required unless passed explicitly |
| `MEETSTREAM_API_URL` | Override the API base |

Anything not yet wrapped is reachable through the raw transport:

```python
meetstream.http.get("/some/new/endpoint")
```

## Typed

The package ships `py.typed`, so mypy and pyright pick up its annotations with no stub package. `meetstream.types` has optional `TypedDict`s for request and response shapes (`CreateBotParams`, `ZoomOptions`, `CreateMiaParams`, `MiaModelConfig`, `KeySource`, `MiaLocalAgentConfig`, `BillingBalance`, `SpeakerTimelineDownload` and more). Methods still take and return plain dicts.

## Also available

| | What | Where |
|:--:|---|---|
| 🔌 | **MCP server** - 19 tools for any MCP client, hosted: add the URL and sign in | [`https://mcp.meetstream.ai/mcp`](https://docs.meetstream.ai/build-with-ai/meetstream-mcp-server) |
| 📦 | **TypeScript SDK** | [`@meetstream/sdk`](https://www.npmjs.com/package/@meetstream/sdk) |
| ⌨️ | **CLI** - `meetstream`, one binary: `npm install -g @meetstream/cli`, `pipx install meetstream-cli` or `brew install meetstream-ai/tap/meetstream`; agents call `meetstream <command> --json --no-input` | [meetstream-ai/cli](https://github.com/meetstream-ai/cli) |
| 🧪 | **Labs** - runnable templates | [labs](https://github.com/meetstream-ai/labs) |

## What's new in 1.4.0

- **Agents API:** `mia.get`, `mia.check_local_agent`, `mia.update_live` (with `wait_for_ack`).
- **Keys:** `key_source` (`"meetstream"` or `"user"`) on `transcriber`, `model` and `voice`, and `is_inbuilt_keys_unavailable(e)`.
- **Local agent (track 3d, coming soon in production):** `model.provider: "local_agent"` with `MiaLocalAgentConfig`.
- **API v1.10.0 agent options:** `agent.tools` (`screen`), `agent.chat_input`, `agent.quiet_actions`, `agent.speak_only_when_asked`, `agent.desktop`, and `transcriber.language`.
- **Failed transcripts:** a `422` from `get_transcript` raises `TranscriptFailedError` with `status`, `transcript_status` and `reason`.
- **Billing:** `billing.balance()` for `GET /billing/balance`, available when the endpoint is on for your account; a `404` raises `BalanceUnavailableError`, which points to the billing page.

Full history: [CHANGELOG.md](CHANGELOG.md).

## Latest docs

- [Integration paths](https://docs.meetstream.ai/guides/introduction/integration-paths): recording bot, bridge server, Agents API infra
- [Bridge server architecture](https://docs.meetstream.ai/guides/websockets/bridge-server-architecture) · [Real-time audio streaming](https://docs.meetstream.ai/guides/websockets/real-time-audio-streaming) · [Meeting control patterns](https://docs.meetstream.ai/guides/websockets/meeting-control-patterns)
- [Create your first bot](https://docs.meetstream.ai/guides/get-started/create-your-first-bot) · [Create Bot payload reference](https://docs.meetstream.ai/api-reference/create-bot-payload-reference)
- [Webhooks and events](https://docs.meetstream.ai/guides/webhooks/webhooks-and-events) · [Errors](https://docs.meetstream.ai/errors)
- [MIA API guide](https://docs.meetstream.ai/guides/mia/mia-api-guide) · [Voice agent pricing and keys](https://docs.meetstream.ai/guides/mia/pricing-and-keys) · [MIA screen sharing and custom agents](https://docs.meetstream.ai/guides/features/mia-screen-sharing-and-custom-agents)
- [SDKs](https://docs.meetstream.ai/build-with-ai/sdks) · [OpenAPI](https://docs.meetstream.ai/openapi.json)

For the latest details, fetch the page with `.md` appended, read https://docs.meetstream.ai/llms.txt, or connect the docs MCP server at https://docs.meetstream.ai/_mcp/server. If this README and the docs differ, the docs are correct.

Support: [support@meetstream.ai](mailto:support@meetstream.ai). MIT licensed.
