"""Tests run entirely against an injected httpx transport.

No API key and no network required.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from meetstream import (
    AsyncMeetStream,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    MeetStream,
    MeetStreamError,
    NotFoundError,
    NotReadyError,
    PermissionError,
    RateLimitError,
    ServerError,
    describe_stop,
    is_terminal,
    stop_reason,
    parse_webhook,
    verify_webhook_signature,
)


def make_client(responses, **kwargs):
    """Build a MeetStream client whose HTTP layer replays canned responses."""
    calls = []
    queue = list(responses) if isinstance(responses, list) else [responses]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        spec = queue.pop(0) if len(queue) > 1 else queue[0]
        status = spec.get("status", 200)
        body = spec.get("body", {})
        return httpx.Response(status, json=body, headers=spec.get("headers", {}))

    transport = httpx.MockTransport(handler)
    kwargs.setdefault("max_retries", 0)
    client = MeetStream("ms_test", http_client=httpx.Client(transport=transport), **kwargs)
    return client, calls


def make_async_client(responses, **kwargs):
    calls = []
    queue = list(responses) if isinstance(responses, list) else [responses]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        spec = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(spec.get("status", 200), json=spec.get("body", {}))

    transport = httpx.MockTransport(handler)
    kwargs.setdefault("max_retries", 0)
    client = AsyncMeetStream("ms_test", http_client=httpx.AsyncClient(transport=transport), **kwargs)
    return client, calls


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("MEETSTREAM_API_KEY", raising=False)
    with pytest.raises(MeetStreamError):
        MeetStream()


def test_rest_auth_uses_token_scheme_not_bearer():
    client, calls = make_client({"body": {"bot_id": "b1"}})
    client.bots.create({"meeting_link": "https://meet.google.com/a-b-c"})
    assert calls[0].headers["authorization"] == "Token ms_test"


def test_create_bot_posts_meeting_link():
    client, calls = make_client({"status": 201, "body": {"bot_id": "b1", "transcript_id": "t1"}})
    bot = client.bots.create({"meeting_link": "https://zoom.us/j/1", "bot_name": "Notetaker"})
    assert bot["bot_id"] == "b1"
    assert calls[0].url.path.endswith("/bots/create_bot")
    assert json.loads(calls[0].content)["meeting_link"] == "https://zoom.us/j/1"


def test_507_is_an_idempotent_replay_and_succeeds():
    client, _ = make_client({"status": 507, "body": {"bot_id": "original"}})
    bot = client.bots.create({"meeting_link": "x"}, idempotency_key="fixed-uuid")
    assert bot["bot_id"] == "original"


def test_idempotency_key_is_sent_as_header():
    client, calls = make_client({"body": {}})
    client.bots.create({"meeting_link": "x"}, idempotency_key="abc-123")
    assert calls[0].headers["idempotency-key"] == "abc-123"


def test_202_raises_not_ready_rather_than_looking_like_success():
    client, _ = make_client({"status": 202, "body": {"message": "processing"}})
    with pytest.raises(NotReadyError):
        client.transcripts.get("t1")


@pytest.mark.parametrize(
    "status,exc",
    [
        (400, BadRequestError), (401, AuthenticationError), (403, PermissionError),
        (404, NotFoundError), (409, ConflictError), (429, RateLimitError), (503, ServerError),
    ],
)
def test_status_codes_map_to_distinct_errors(status, exc):
    client, _ = make_client({"status": status, "body": {"message": f"fail {status}"}})
    with pytest.raises(exc) as info:
        client.bots.status("b1")
    assert info.value.status == status
    assert info.value.message == f"fail {status}"


def test_remove_is_get_and_delete_data_is_delete():
    client, calls = make_client({"body": {}})
    client.bots.remove("b1")
    client.bots.delete_data("b1")
    assert calls[0].method == "GET" and calls[0].url.path.endswith("/bots/b1/remove_bot")
    assert calls[1].method == "DELETE" and calls[1].url.path.endswith("/bots/b1/delete")


def test_transcript_fetched_by_transcript_id():
    client, calls = make_client({"body": {"transcript": [{"speaker": "Sid", "transcript": "hello"}]}})
    out = client.transcripts.get("t-42")
    assert out["transcript"][0]["transcript"] == "hello"
    assert calls[0].url.path.endswith("/transcript/t-42/get_transcript")


def test_wait_for_gives_up_instead_of_polling_forever():
    client, _ = make_client({"status": 202, "body": {}})
    with pytest.raises(NotReadyError) as info:
        client.transcripts.wait_for("t1", timeout=0.05, interval=0.01)
    assert "streaming-only" in str(info.value)


def test_retries_transient_then_succeeds():
    client, calls = make_client(
        [{"status": 503, "body": {"message": "unavailable"}}, {"status": 200, "body": {"ok": True}}],
        max_retries=3,
    )
    assert client.bots.status("b1")["ok"] is True
    assert len(calls) == 2


def test_does_not_retry_a_400():
    client, calls = make_client(
        {"status": 400, "body": {"message": "meeting_link is required."}}, max_retries=3
    )
    with pytest.raises(BadRequestError):
        client.bots.create({})
    assert len(calls) == 1


def test_mia_create_and_update():
    client, calls = make_client({"body": {"agent_config_id": "agent-1"}})
    cfg = client.mia.create({"agent_name": "Assistant", "mode": "pipeline"})
    assert cfg["agent_config_id"] == "agent-1"
    client.mia.update("agent-1", {"agent_name": "Renamed"})
    assert calls[1].method == "PUT"
    assert json.loads(calls[1].content)["agent_config_id"] == "agent-1"


def test_mia_delete_passes_query_param():
    client, calls = make_client({"body": {}})
    client.mia.delete("agent-1")
    assert calls[0].method == "DELETE"
    assert calls[0].url.params["agent_config_id"] == "agent-1"


def test_reschedule_uses_scheduled_join_time():
    client, calls = make_client({"body": {}})
    client.calendar.reschedule_bot("b1", "2026-09-01T10:00:00Z")
    assert calls[0].method == "PATCH"
    assert json.loads(calls[0].content)["scheduled_join_time"] == "2026-09-01T10:00:00Z"


def test_storage_set_targets_admin_configs():
    client, calls = make_client({"body": {}})
    client.storage.set({"provider": "aws", "bucket_name": "b"})
    assert calls[0].method == "PUT"
    assert calls[0].url.params["config_type"] == "storage"


def test_base_url_override():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={})

    client = MeetStream(
        "k",
        base_url="https://staging.example.com/api/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.bots.list()
    assert str(calls[0].url) == "https://staging.example.com/api/v1/bots"


def test_context_manager_closes():
    client, _ = make_client({"body": {}})
    with client as c:
        c.bots.list()


# --------------------------------------------------------------- async ----

async def test_async_client_works():
    client, calls = make_async_client({"body": {"bot_id": "b1"}})
    bot = await client.bots.create({"meeting_link": "https://zoom.us/j/1"})
    assert bot["bot_id"] == "b1"
    assert calls[0].headers["authorization"] == "Token ms_test"
    await client.aclose()


async def test_async_202_raises_not_ready():
    client, _ = make_async_client({"status": 202, "body": {}})
    with pytest.raises(NotReadyError):
        await client.transcripts.get("t1")
    await client.aclose()


# ------------------------------------------------------------- webhooks ---

SECRET = "whsec_test"
BODY = json.dumps({"event": "bot.stopped", "bot_event": "bot.notallowed", "bot_id": "b1", "bot_status": "NotAllowed", "status_code": 500, "timestamp": "2026-06-16T06:28:14.445Z"})
SIG = hmac.new(SECRET.encode(), BODY.encode(), hashlib.sha256).hexdigest()


def test_valid_signature_verifies_in_both_forms():
    assert verify_webhook_signature(BODY, SIG, SECRET) is True
    assert verify_webhook_signature(BODY, f"sha256={SIG}", SECRET) is True
    assert verify_webhook_signature(BODY.encode(), SIG, SECRET) is True


def test_tampered_body_or_wrong_secret_fails():
    assert verify_webhook_signature(BODY + " ", SIG, SECRET) is False
    assert verify_webhook_signature(BODY, SIG, "wrong") is False
    assert verify_webhook_signature(BODY, "short", SECRET) is False
    assert verify_webhook_signature(BODY, "", SECRET) is False


def test_parse_webhook_refuses_forged_payload():
    with pytest.raises(ValueError):
        parse_webhook(BODY, "bad", SECRET)
    assert parse_webhook(BODY, SIG, SECRET)["event"] == "bot.stopped"


def test_terminal_event_detection():
    assert is_terminal({"event": "bot.stopped"}) is True
    assert is_terminal({"event": "bot.error"}) is False
    assert is_terminal({"event": "bot.done"}) is False


# Shapes taken from captured production webhooks (Jun 2026).
def test_describe_stop_reads_bot_event():
    assert "normally" in describe_stop({"event": "bot.stopped", "bot_event": "bot.stopped", "bot_status": "Stopped", "status_code": 200})
    assert "removed" in describe_stop({"event": "bot.stopped", "bot_event": "bot.kicked", "bot_status": "Stopped", "status_code": 200})
    assert "waiting room" in describe_stop({"event": "bot.stopped", "bot_event": "bot.notallowed", "bot_status": "NotAllowed", "status_code": 500})
    assert "refused" in describe_stop({"event": "bot.stopped", "bot_event": "bot.denied", "bot_status": "Denied", "status_code": 500})
    assert "crashed" in describe_stop({"event": "bot.stopped", "bot_event": "bot.failed", "bot_status": "FAILED", "status_code": 500})


def test_stop_reason_falls_back_to_bot_status_case_insensitively():
    assert stop_reason({"event": "bot.stopped", "bot_status": "NotAllowed"}) == "bot.notallowed"
    assert stop_reason({"event": "bot.stopped", "bot_status": "Denied"}) == "bot.denied"
    assert stop_reason({"event": "bot.stopped", "bot_status": "ERROR"}) == "bot.failed"
    assert stop_reason({"event": "bot.stopped", "bot_status": "Failed"}) == "bot.failed"
    assert stop_reason({"event": "bot.stopped", "bot_status": "Stopped"}) == "bot.stopped"


def test_kick_is_distinguishable_from_clean_exit():
    kick = {"event": "bot.stopped", "bot_event": "bot.kicked", "bot_status": "Stopped"}
    clean = {"event": "bot.stopped", "bot_event": "bot.stopped", "bot_status": "Stopped"}
    assert stop_reason(kick) != stop_reason(clean)

