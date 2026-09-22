<div align="center">

# MeetStream SDK for Python

**Send AI bots into Zoom, Google Meet and Microsoft Teams.** Record, transcribe, summarize and stream meetings, and run [MIA voice agents](#mia-voice-agents) that talk back.

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

## Quickstart

```python
from meetstream import MeetStream

meetstream = MeetStream()  # reads MEETSTREAM_API_KEY

bot = meetstream.bots.create({
    "meeting_link": "https://meet.google.com/abc-defg-hij",
    "bot_name": "Notetaker",
    "video_required": False,  # audio only unless video was asked for; the API defaults to True
    "recording_config": {
        "transcript": {"provider": {"deepgram": {"model": "nova-3", "language": "en"}}}
        # Recording video? Add "video_layout": "speaker_view" (the API defaults to grid_view).
    },
})

# Bounded wait - never spins forever, even on a streaming-only bot.
transcript = meetstream.transcripts.wait_for(bot["transcript_id"])
```

Get a key at [app.meetstream.ai/api-key](https://app.meetstream.ai/api-key).

### Async

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
| **`remove_bot` is a `GET`** | `bots.remove()` handles it |
| **REST uses `Token`, the MCP server uses `Bearer`** | Correct scheme sent automatically |
| **MIA takes only `agent_config_id`** | Extra bridge fields are the usual cause of a silent agent |

## What you can do

<details open>
<summary><b>Bots</b> - lifecycle, media, live interaction</summary>

```python
meetstream.bots.create(params, idempotency_key=uuid)
meetstream.bots.list()
meetstream.bots.status(bot_id)
meetstream.bots.detail(bot_id)        # includes transcript_id
meetstream.bots.summary(bot_id)       # AI summary
meetstream.bots.remove(bot_id)        # leave, keep the data
meetstream.bots.delete_data(bot_id)   # irreversible

meetstream.bots.audio(bot_id)
meetstream.bots.video(bot_id)
meetstream.bots.audio_streams(bot_id)       # per-participant audio
meetstream.bots.recording_streams(bot_id)   # per-participant video
meetstream.bots.screenshots(bot_id)
meetstream.bots.wait_for_audio(bot_id)      # bounded

meetstream.bots.participants(bot_id)
meetstream.bots.chats(bot_id)
meetstream.bots.speaker_timeline(bot_id)

meetstream.bots.send_message(bot_id, "Recording has started.")
meetstream.bots.send_image(bot_id, "https://…/slide.png", display_duration=5)
meetstream.bots.pause_recording(bot_id)     # privacy window
meetstream.bots.resume_recording(bot_id)
```

</details>

<details open>
<summary><b>Transcripts</b></summary>

```python
meetstream.transcripts.get(transcript_id)
meetstream.transcripts.wait_for(transcript_id, timeout=900)
meetstream.transcripts.list_for_bot(bot_id)
meetstream.transcripts.transcribe_bot_audio(bot_id)   # rescue a streaming-only bot
```

</details>

<details open>
<summary><b>Calendar</b> - auto-join and scheduling</summary>

```python
meetstream.calendar.connect_google({
    "google_client_id": ..., "google_client_secret": ..., "google_refresh_token": ...,
})
meetstream.calendar.connect_outlook({...})
meetstream.calendar.events()
meetstream.calendar.schedule_event(event_id)
meetstream.calendar.list_scheduled_bots()
meetstream.calendar.reschedule_bot(bot_id, "2026-09-01T10:00:00Z")
meetstream.calendar.enable_auto_schedule()
```

</details>

<details open>
<summary><b>MIA voice agents</b></summary>

```python
agent = meetstream.mia.create({
    "agent_name": "Meeting Assistant",
    "mode": "pipeline",                    # or "realtime" for speech-to-speech
    "model": {"provider": "openai", "model": "gpt-4.1",
              "first_message": "Hi, I'm an AI assistant on this call."},
    "voice": {"provider": "openai", "voice_id": "nova"},
    "transcriber": {"provider": "deepgram", "model": "nova-3",
                    "boostwords": ["Acme", "MeetStream"]},
    "agent": {"tools": [], "mcp_servers": [], "enable_interruptions": True},
    "wake_word": {"enabled": True, "words": ["hey acme"], "timeout": 30},
})

# Attach it with ONE field. Adding socket_connection_url or
# live_audio_required alongside is the usual cause of a silent agent.
meetstream.bots.create({
    "meeting_link": meeting_link,
    "agent_config_id": agent["agent_config_id"],
})
```

`boostwords` fixes most "it mishears our company name" complaints, and `mcp_servers` is what turns a talking bot into one that can do work mid-call.

</details>

<details>
<summary><b>Integrations</b> - Google and Teams signed-in bots, authenticated Zoom joins, your own S3</summary>

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

meetstream.storage.set({"provider": "aws", "bucket_name": ..., "region": ...})
```

Teams setup (dedicated Microsoft 365 tenant, account requirements, errors): [Teams signed-in bots guide](https://docs.meetstream.ai/guides/app-integrations/teams-signed-in-bots).

</details>

## Webhooks

Verify before you trust. Pass the **raw** body - re-serializing a parsed dict changes key order and the signature will never match.

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
        )
    except ValueError:
        return "", 401

    if is_terminal(event):
        print(stop_reason(event), describe_stop(event))
    return "", 200   # ack fast, process async
```

**Terminals are two-layer.** Every ending arrives once as `event: "bot.stopped"`, and `bot_event` says why: `bot.stopped`, `bot.kicked`, `bot.notallowed`, `bot.denied` or `bot.failed`. Not admitted, denied and failed carry `status_code: 500`. `stop_reason(event)` reads it for you (a kick and a clean exit both report `bot_status: "Stopped"`, so don't branch on that). `bot.error` is *not* terminal; the bot keeps running. `bot.done` is the final event on every path, streaming-only bots included. Every event carries a `timestamp`.

## Errors

```python
from meetstream import NotReadyError, RateLimitError, BadRequestError, MeetStreamError

try:
    meetstream.transcripts.get(transcript_id)
except NotReadyError:
    ...                                  # 202 - poll again
except RateLimitError as e:
    time.sleep(e.retry_after or 5)
except BadRequestError as e:
    print(e.message)                     # the API's own message
except MeetStreamError as e:
    print(e.status, e.request_id)
```

`AuthenticationError` (401) means the header never arrived. `PermissionError` (403) means the key itself was rejected. That distinction saves a lot of debugging.

## Configuration

```python
meetstream = MeetStream(
    api_key=os.environ["MEETSTREAM_API_KEY"],
    base_url="https://api.meetstream.ai/api/v1",
    timeout=60.0,
    max_retries=2,          # 429 and 5xx, exponential backoff, honours Retry-After
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

The package ships `py.typed`, so mypy and pyright pick up its annotations with no stub package.

## Also available

| | What | Where |
|:--:|---|---|
| 🔌 | **MCP server** - 19 tools for any MCP client | [`@meetstream/mcp`](https://www.npmjs.com/package/@meetstream/mcp) |
| 📦 | **TypeScript SDK** | [`@meetstream/sdk`](https://www.npmjs.com/package/@meetstream/sdk) |
| ⌨️ | **CLI** | [`@meetstream/cli`](https://www.npmjs.com/package/@meetstream/cli) |
| 🧪 | **Labs** - runnable templates | [labs](https://github.com/meetstream-ai/labs) |

## Links

[Documentation](https://docs.meetstream.ai) · [API reference](https://docs.meetstream.ai/api-reference/introduction) · [Errors](https://docs.meetstream.ai/errors) · [Webhooks](https://docs.meetstream.ai/guides/webhooks/webhooks-and-events) · [MIA](https://docs.meetstream.ai/guides/mia/create-an-agent) · [support@meetstream.ai](mailto:support@meetstream.ai)

MIT licensed.
