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
    AGENT_ID_HEADER,
    BOT_ID_HEADER,
    PARTICIPANT_HAND_EVENTS,
    is_final_segment,
    parse_custom_function_call,
    AsyncMeetStream,
    AuthenticationError,
    BadRequestError,
    BalanceUnavailableError,
    TranscriptFailedError,
    is_inbuilt_keys_unavailable,
    ConflictError,
    MeetStream,
    MeetStreamError,
    NotFoundError,
    NotReadyError,
    PermissionError,
    RateLimitError,
    ServerError,
    describe_stop,
    hand_event,
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
        return httpx.Response(spec.get("status", 200), json=spec.get("body", {}), headers=spec.get("headers", {}))

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
    with pytest.warns(DeprecationWarning, match="storage_id"):
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


# ------------------------------------------------------ signed-in logins ---

def _req(call):
    path = call.url.path
    prefix = "/api/v1"
    if path.startswith(prefix):
        path = path[len(prefix):]
    return (
        call.method,
        path,
        dict(call.url.params),
        json.loads(call.content) if call.content else None,
    )


def test_teams_logins_domain_methods():
    client, calls = make_client({"body": {}})
    client.teams_logins.create_domain({"domain": "bots.acme.com", "name": "Acme", "login_mode": "always"})
    client.teams_logins.list_domains()
    client.teams_logins.get_domain("bots.acme.com")
    client.teams_logins.update_domain("bots.acme.com", {"name": "Renamed"})
    client.teams_logins.delete_domain("bots.acme.com")
    assert [_req(c) for c in calls] == [
        ("POST", "/teams-login-domains", {}, {"domain": "bots.acme.com", "name": "Acme", "login_mode": "always"}),
        ("GET", "/teams-login-domains", {}, None),
        ("GET", "/teams-login-domains/bots.acme.com", {}, None),
        ("PATCH", "/teams-login-domains/bots.acme.com", {}, {"name": "Renamed"}),
        ("DELETE", "/teams-login-domains/bots.acme.com", {}, None),
    ]


def test_teams_logins_login_methods():
    client, calls = make_client({"body": {}})
    client.teams_logins.create({"domain": "bots.acme.com", "email": "bot1@bots.acme.com", "password": "placeholder"})
    client.teams_logins.list("bots.acme.com")
    client.teams_logins.get("login-1")
    client.teams_logins.update("login-1", {"is_active": False})
    client.teams_logins.delete("login-1")
    assert [_req(c) for c in calls] == [
        ("POST", "/teams-logins", {}, {"domain": "bots.acme.com", "email": "bot1@bots.acme.com", "password": "placeholder"}),
        ("GET", "/teams-logins", {"domain": "bots.acme.com"}, None),
        ("GET", "/teams-logins/login-1", {}, None),
        ("PATCH", "/teams-logins/login-1", {}, {"is_active": False}),
        ("DELETE", "/teams-logins/login-1", {}, None),
    ]


def test_teams_logins_list_requires_domain():
    client, _ = make_client({"body": {}})
    with pytest.raises(TypeError):
        client.teams_logins.list()


def test_google_logins_list_accepts_optional_domain():
    client, calls = make_client({"body": {}})
    client.google_logins.list()
    client.google_logins.list("acme.com")
    client.google_logins.list(domain="acme.com")
    assert [(c.method, c.url.path.split("/api/v1")[-1], dict(c.url.params)) for c in calls] == [
        ("GET", "/google-logins", {}),
        ("GET", "/google-logins", {"domain": "acme.com"}),
        ("GET", "/google-logins", {"domain": "acme.com"}),
    ]


def test_create_bot_passes_teams_block_through_unchanged():
    client, calls = make_client({"status": 201, "body": {"bot_id": "b1"}})
    teams = {"login_required": True, "teams_login_domain": "bots.acme.com", "sign_in_email": "bot1@bots.acme.com", "strict_email": False}
    client.bots.create({"meeting_link": "https://teams.microsoft.com/l/meetup-join/x", "teams": teams})
    assert json.loads(calls[0].content)["teams"] == teams


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


async def test_async_teams_logins_all_methods():
    client, calls = make_async_client({"body": {}})
    t = client.teams_logins
    await t.create_domain({"domain": "bots.acme.com"})
    await t.list_domains()
    await t.get_domain("bots.acme.com")
    await t.update_domain("bots.acme.com", {"name": "Renamed"})
    await t.delete_domain("bots.acme.com")
    await t.create({"domain": "bots.acme.com", "email": "bot1@bots.acme.com", "password": "placeholder"})
    await t.list("bots.acme.com")
    await t.get("login-1")
    await t.update("login-1", {"password": "placeholder-2"})
    await t.delete("login-1")
    assert [_req(c) for c in calls] == [
        ("POST", "/teams-login-domains", {}, {"domain": "bots.acme.com"}),
        ("GET", "/teams-login-domains", {}, None),
        ("GET", "/teams-login-domains/bots.acme.com", {}, None),
        ("PATCH", "/teams-login-domains/bots.acme.com", {}, {"name": "Renamed"}),
        ("DELETE", "/teams-login-domains/bots.acme.com", {}, None),
        ("POST", "/teams-logins", {}, {"domain": "bots.acme.com", "email": "bot1@bots.acme.com", "password": "placeholder"}),
        ("GET", "/teams-logins", {"domain": "bots.acme.com"}, None),
        ("GET", "/teams-logins/login-1", {}, None),
        ("PATCH", "/teams-logins/login-1", {}, {"password": "placeholder-2"}),
        ("DELETE", "/teams-logins/login-1", {}, None),
    ]
    await client.aclose()


async def test_async_google_logins_list_domain():
    client, calls = make_async_client({"body": {}})
    await client.google_logins.list("acme.com")
    assert dict(calls[0].url.params) == {"domain": "acme.com"}
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



# Policy: audio only unless asked, speaker view when video is on, per-participant video opt-in.
def test_create_bot_passes_video_policy_fields_through():
    client, calls = make_client({"status": 201, "body": {"bot_id": "b1"}})
    client.bots.create(
        {
            "meeting_link": "https://meet.google.com/x",
            "bot_name": "Notetaker",
            "video_required": True,
            "recording_config": {"video_layout": "speaker_view"},
        }
    )
    sent = json.loads(calls[0].content)
    assert sent["video_required"] is True
    assert sent["recording_config"]["video_layout"] == "speaker_view"
    assert "video_separate_streams" not in sent


# ------------------------------------------------------ API coverage ---

def test_send_command_raise_and_lower_hand():
    client, calls = make_client({"body": {"status": "accepted", "bot_id": "b1", "command": "raise_hand", "hand_raised": True}})
    out = client.bots.raise_hand("b1")
    client.bots.lower_hand("b1")
    client.bots.send_command("b1", "screenshot")
    client.bots.send_command("b1", "sendmsg", {"message": "hi"})
    assert out["hand_raised"] is True
    assert [_req(c) for c in calls] == [
        ("POST", "/bots/b1/send_command", {}, {"command": "raise_hand"}),
        ("POST", "/bots/b1/send_command", {}, {"command": "lower_hand"}),
        ("POST", "/bots/b1/send_command", {}, {"command": "screenshot"}),
        ("POST", "/bots/b1/send_command", {}, {"message": "hi", "command": "sendmsg"}),
    ]


def test_hand_command_unsupported_platform_exposes_code():
    client, _ = make_client({"status": 400, "body": {"message": "Not supported on WhatsApp.", "code": "unsupported_on_whatsapp"}})
    with pytest.raises(BadRequestError) as info:
        client.bots.raise_hand("b1")
    assert info.value.code == "unsupported_on_whatsapp"
    assert info.value.message == "Not supported on WhatsApp."


def test_hand_command_bot_not_in_meeting_is_conflict_and_not_retried():
    client, calls = make_client({"status": 409, "body": {"message": "Bot is not in the meeting"}}, max_retries=3)
    with pytest.raises(ConflictError):
        client.bots.raise_hand("b1")
    assert len(calls) == 1


def test_update_mia_with_and_without_wait_for_ack():
    client, calls = make_client({"body": {"status": "applied", "bot_id": "b1", "command": "update_mia", "applied": ["system_prompt"]}})
    out = client.bots.update_mia("b1", {"system_prompt": "Be brief."}, wait_for_ack=True)
    client.bots.update_mia("b1", {"wake_words": ["hey acme"]})
    assert out["status"] == "applied"
    assert [_req(c) for c in calls] == [
        ("POST", "/bots/b1/update_mia", {}, {"system_prompt": "Be brief.", "wait_for_ack": True}),
        ("POST", "/bots/b1/update_mia", {}, {"wake_words": ["hey acme"]}),
    ]


def test_get_bot_stop_status_and_get_transcript_by_bot():
    client, calls = make_client({"body": {}})
    client.bots.get("b1")
    client.bots.stop_status("b1")
    client.transcripts.get_by_bot("b1")
    client.transcripts.get_by_bot("b1", raw=True)
    assert [_req(c) for c in calls] == [
        ("GET", "/bots/b1", {}, None),
        ("GET", "/bots/b1/stop_status", {}, None),
        ("GET", "/bots/b1/get_transcript", {"raw": "false"}, None),
        ("GET", "/bots/b1/get_transcript", {"raw": "true"}, None),
    ]


def test_remove_returns_202_stop_in_progress_instead_of_raising():
    body = {"bot_id": "b1", "status": "graceful_exit_in_progress", "bot_status": "InMeeting"}
    client, calls = make_client({"status": 202, "body": body})
    assert client.bots.remove("b1") == body
    assert client.bots.stop_status("b1") == body
    assert calls[0].method == "GET" and calls[0].url.path.endswith("/bots/b1/remove_bot")


def test_screenshots_use_the_live_route_and_pass_paging_params():
    client, calls = make_client({"body": {"screenshots": []}})
    client.bots.screenshots("b1")
    client.bots.screenshots("b1", limit=10, continuation_token="tok", meta="m", action="prev")
    client.bots.screenshot("b1", "20261101T101010000Z_abc")
    assert [_req(c) for c in calls] == [
        ("GET", "/bots/b1/screenshots", {}, None),
        ("GET", "/bots/b1/screenshots", {"limit": "10", "continuation_token": "tok", "action": "prev", "meta": "m"}, None),
        ("GET", "/bots/b1/screenshots/20261101T101010000Z_abc", {}, None),
    ]


def test_summary_is_deprecated():
    client, calls = make_client({"body": {}})
    with pytest.warns(DeprecationWarning, match="no summary endpoint") as rec:
        client.bots.summary("b1")
    assert calls[0].url.path.endswith("/bots/b1/summary")
    assert "get_transcript" in str(rec[0].message)
    assert rec[0].filename == __file__


def _timeline_client(api_body, file_body):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "files.example.com":
            return httpx.Response(200, json=file_body)
        return httpx.Response(200, json=api_body)

    client = MeetStream("ms_test", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return client, calls


TIMELINE_URL = {
    "bot_id": "b1",
    "speaker_timeline_url": "https://files.example.com/t.json?X-Amz-Signature=abc",
    "size_bytes": 8421337,
    "truncated": False,
}


def test_speaker_timeline_returns_download_shape_unless_asked_to_download():
    client, calls = _timeline_client(TIMELINE_URL, [{"name": "Sid"}])
    assert client.bots.speaker_timeline("b1") == TIMELINE_URL
    assert len(calls) == 1


def test_speaker_timeline_download_fetches_without_the_api_key():
    client, calls = _timeline_client(TIMELINE_URL, [{"name": "Sid"}])
    assert client.bots.speaker_timeline("b1", download=True) == [{"name": "Sid"}]
    assert calls[1].url.host == "files.example.com"
    assert "authorization" not in calls[1].headers


def test_speaker_timeline_download_leaves_inline_body_alone():
    client, calls = _timeline_client([{"name": "Sid"}], None)
    assert client.bots.speaker_timeline("b1", download=True) == [{"name": "Sid"}]
    assert len(calls) == 1


def test_speaker_timeline_download_refuses_non_https_url():
    client, _ = _timeline_client(dict(TIMELINE_URL, speaker_timeline_url="http://files.example.com/t.json"), None)
    with pytest.raises(MeetStreamError):
        client.bots.speaker_timeline("b1", download=True)


def test_calendar_routes_match_the_api():
    client, calls = make_client({"body": {}})
    client.calendar.list()
    client.calendar.list(provider="google", account_id="a@acme.com")
    client.calendar.disconnect()
    client.calendar.disconnect({"provider": "google", "account_id": "a@acme.com", "purge_events": False})
    client.calendar.list_connections(limit=10, cursor="c1")
    client.calendar.get_connection("google", "a@acme.com")
    client.calendar.delete_connection("outlook", "b@acme.com", purge_events=False)
    assert [_req(c) for c in calls] == [
        ("GET", "/calendar/calendars", {}, None),
        ("GET", "/calendar/calendars", {"provider": "google", "account_id": "a@acme.com"}, None),
        ("DELETE", "/calendar/disconnect", {}, None),
        ("DELETE", "/calendar/disconnect", {"provider": "google", "account_id": "a@acme.com", "purge_events": "false"}, None),
        ("GET", "/calendar/connections", {"limit": "10", "cursor": "c1"}, None),
        ("GET", "/calendar/connections/google/a@acme.com", {}, None),
        ("DELETE", "/calendar/connections/outlook/b@acme.com", {"purge_events": "false"}, None),
    ]
    assert calls[5].url.raw_path.endswith(b"/calendar/connections/google/a%40acme.com")


def test_toggle_recurrence_is_deprecated():
    client, _ = make_client({"body": {}})
    with pytest.warns(DeprecationWarning):
        client.calendar.toggle_recurrence()


def test_google_logins_get():
    client, calls = make_client({"body": {}})
    client.google_logins.get("login-1")
    assert _req(calls[0]) == ("GET", "/google-logins/login-1", {}, None)


def test_meeting_direct_connect_routes():
    client, calls = make_client({"body": {}})
    rtms = {"zoom_rtms": {"meeting_uuid": "u", "rtms_stream_id": "s", "server_urls": "wss://x.zoom.us", "signature": "f" * 64}}
    client.meeting_direct_connect.create(rtms)
    client.meeting_direct_connect.get("b1")
    client.meeting_direct_connect.leave("b1")
    assert [_req(c) for c in calls] == [
        ("POST", "/meeting_direct_connect", {}, rtms),
        ("GET", "/meeting_direct_connect/b1", {}, None),
        ("POST", "/meeting_direct_connect/b1/leave", {}, {}),
    ]


def test_create_bot_passes_new_fields_through_unchanged():
    from meetstream.types import CreateBotParams

    params: CreateBotParams = {
        "meeting_link": "https://zoom.us/j/1",
        "zoom": {"use_own_app": False},
        "storage_id": "eu-bucket_1",
        "bot_camera_stream": {"websocket_url": "wss://cam.example.com/signal"},
        "automatic_leave": {"recording_permission_denied_timeout": 600},
        "recording_config": {
            "video_layout": "speaker_view_default",
            "transcript": {"provider": {"smallest": {"model": "pulse", "language": "en", "diarize": True}}},
            "realtime_endpoints": [
                {"type": "webhook", "url": "https://you.example.com/rt", "events": list(PARTICIPANT_HAND_EVENTS)}
            ],
        },
    }
    client, calls = make_client({"status": 201, "body": {"bot_id": "b1"}})
    client.bots.create(params)
    assert json.loads(calls[0].content) == params


def test_mia_create_with_anthropic_provider():
    client, calls = make_client({"body": {"agent_config_id": "agent-1"}})
    model = {"provider": "anthropic", "model": "claude-sonnet-5-5", "reasoning_effort": "low", "tool_choice": "auto"}
    client.mia.create({"agent_name": "Claude", "mode": "pipeline", "model": model})
    assert json.loads(calls[0].content)["model"] == model


# ---------------------------------------------------- errors and retries ---

def test_rate_limit_surfaces_retry_after_and_body():
    body = {"error": "rate_limit_exceeded", "message": "Too many bots", "limit": 5, "window": "minute", "retry_after": 37}
    client, _ = make_client({"status": 429, "body": body, "headers": {"Retry-After": "37"}})
    with pytest.raises(RateLimitError) as info:
        client.bots.create({"meeting_link": "x"})
    assert info.value.retry_after == 37.0
    assert info.value.message == "Too many bots"
    assert info.value.body["window"] == "minute"


def test_retry_after_falls_back_to_body_when_header_missing():
    client, _ = make_client({"status": 429, "body": {"message": "slow down", "retry_after": 12}})
    with pytest.raises(RateLimitError) as info:
        client.bots.status("b1")
    assert info.value.retry_after == 12.0


def test_429_retry_honours_retry_after(monkeypatch):
    slept = []
    monkeypatch.setattr("meetstream._client.time.sleep", slept.append)
    client, calls = make_client(
        [{"status": 429, "body": {"message": "slow"}, "headers": {"Retry-After": "3"}}, {"body": {"ok": True}}],
        max_retries=2,
    )
    assert client.bots.status("b1")["ok"] is True
    assert slept == [3.0] and len(calls) == 2


def test_long_retry_after_is_raised_not_slept(monkeypatch):
    slept = []
    monkeypatch.setattr("meetstream._client.time.sleep", slept.append)
    client, calls = make_client({"status": 429, "body": {"message": "hourly"}, "headers": {"Retry-After": "1800"}}, max_retries=3)
    with pytest.raises(RateLimitError) as info:
        client.bots.create({"meeting_link": "x"})
    assert info.value.retry_after == 1800.0
    assert slept == [] and len(calls) == 1


def test_409_with_retry_after_is_retried_with_the_same_idempotency_key(monkeypatch):
    slept = []
    monkeypatch.setattr("meetstream._client.time.sleep", slept.append)
    client, calls = make_client(
        [{"status": 409, "body": {"message": "in progress"}, "headers": {"Retry-After": "2"}}, {"status": 507, "body": {"bot_id": "orig"}}],
        max_retries=2,
    )
    bot = client.bots.create({"meeting_link": "x"}, idempotency_key="k-1")
    assert bot["bot_id"] == "orig"
    assert slept == [2.0]
    assert [c.headers["idempotency-key"] for c in calls] == ["k-1", "k-1"]


@pytest.mark.parametrize(
    "body,expected",
    [
        ({"message": "Manifest file not found."}, "Manifest file not found."),
        ({"error": "Bot not found"}, "Bot not found"),
        ({"error": "Invalid JSON body", "detail": "Expecting value"}, "Invalid JSON body"),
        ("Bot not found.", "Bot not found."),
        ({}, "MeetStream API returned HTTP 404"),
    ],
)
def test_error_message_reads_message_then_error_then_bare_string(body, expected):
    client, _ = make_client({"status": 404, "body": body})
    with pytest.raises(NotFoundError) as info:
        client.bots.audio("b1")
    assert info.value.message == expected
    assert info.value.code is None


# ------------------------------------------------------------ webhooks ---

def test_hand_event_helper():
    assert hand_event({"event": "participant_events.raise_hand"}) == "raise_hand"
    assert hand_event({"event": "participant_events.lower_hand"}) == "lower_hand"
    assert hand_event({"event": "participant_events.join"}) is None
    assert hand_event({}) is None


# --------------------------------------------------------- async parity ---

async def test_async_new_bot_methods():
    client, calls = make_async_client({"body": {}})
    await client.bots.get("b1")
    await client.bots.stop_status("b1")
    await client.bots.raise_hand("b1")
    await client.bots.lower_hand("b1")
    await client.bots.send_command("b1", "interrupt")
    await client.bots.update_mia("b1", {"system_prompt": "x"}, wait_for_ack=True)
    await client.bots.screenshots("b1", limit=5)
    await client.bots.screenshot("b1", "s1")
    await client.transcripts.get_by_bot("b1")
    await client.google_logins.get("login-1")
    await client.meeting_direct_connect.create({"zoom_rtms": {}})
    await client.meeting_direct_connect.get("b1")
    await client.meeting_direct_connect.leave("b1")
    assert [_req(c) for c in calls] == [
        ("GET", "/bots/b1", {}, None),
        ("GET", "/bots/b1/stop_status", {}, None),
        ("POST", "/bots/b1/send_command", {}, {"command": "raise_hand"}),
        ("POST", "/bots/b1/send_command", {}, {"command": "lower_hand"}),
        ("POST", "/bots/b1/send_command", {}, {"command": "interrupt"}),
        ("POST", "/bots/b1/update_mia", {}, {"system_prompt": "x", "wait_for_ack": True}),
        ("GET", "/bots/b1/screenshots", {"limit": "5"}, None),
        ("GET", "/bots/b1/screenshots/s1", {}, None),
        ("GET", "/bots/b1/get_transcript", {"raw": "false"}, None),
        ("GET", "/google-logins/login-1", {}, None),
        ("POST", "/meeting_direct_connect", {}, {"zoom_rtms": {}}),
        ("GET", "/meeting_direct_connect/b1", {}, None),
        ("POST", "/meeting_direct_connect/b1/leave", {}, {}),
    ]
    await client.aclose()


async def test_async_calendar_routes_match_the_api():
    client, calls = make_async_client({"body": {}})
    await client.calendar.list(provider="outlook")
    await client.calendar.disconnect({"purge_events": False})
    await client.calendar.list_connections()
    await client.calendar.get_connection("google", "a@acme.com")
    await client.calendar.delete_connection("google", "a@acme.com")
    assert [_req(c) for c in calls] == [
        ("GET", "/calendar/calendars", {"provider": "outlook"}, None),
        ("DELETE", "/calendar/disconnect", {"purge_events": "false"}, None),
        ("GET", "/calendar/connections", {}, None),
        ("GET", "/calendar/connections/google/a@acme.com", {}, None),
        ("DELETE", "/calendar/connections/google/a@acme.com", {}, None),
    ]
    await client.aclose()


async def test_async_remove_returns_202_body():
    body = {"bot_id": "b1", "status": "graceful_exit_in_progress"}
    client, _ = make_async_client({"status": 202, "body": body})
    assert await client.bots.remove("b1") == body
    await client.aclose()


async def test_async_speaker_timeline_download():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "files.example.com":
            return httpx.Response(200, json=[{"name": "Sid"}])
        return httpx.Response(200, json=TIMELINE_URL)

    client = AsyncMeetStream("ms_test", max_retries=0, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await client.bots.speaker_timeline("b1", download=True) == [{"name": "Sid"}]
    assert "authorization" not in calls[1].headers
    await client.aclose()


async def test_async_429_retry_honours_retry_after(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    client, calls = make_async_client(
        [{"status": 429, "body": {"message": "slow"}, "headers": {"Retry-After": "4"}}, {"body": {"ok": True}}],
        max_retries=2,
    )
    assert (await client.bots.status("b1"))["ok"] is True
    assert slept == [4.0] and len(calls) == 2
    await client.aclose()


async def test_async_deprecations_warn():
    client, calls = make_async_client({"body": {}})
    with pytest.warns(DeprecationWarning, match="no summary endpoint"):
        await client.bots.summary("b1")
    assert calls[0].url.path.endswith("/bots/b1/summary")
    with pytest.warns(DeprecationWarning):
        await client.calendar.toggle_recurrence()
    with pytest.warns(DeprecationWarning):
        await client.storage.get()
    await client.aclose()



# --------------------------------------------------------- 1.4.0: Agents API


def _body(req):
    return json.loads(req.content) if req.content else None


def test_mia_get_fetches_one_config():
    client, calls = make_client({"body": {"AgentConfigID": "a1"}})
    assert client.mia.get("a1")["AgentConfigID"] == "a1"
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/api/v1/mia"
    assert calls[0].url.params["agent_config_id"] == "a1"


def test_mia_create_sends_key_source_and_no_api_key():
    client, calls = make_client({"status": 201, "body": {"agent_config_id": "a2"}})
    out = client.mia.create({
        "agent_name": "Inbuilt keys",
        "mode": "pipeline",
        "transcriber": {"provider": "deepgram", "language": "es", "key_source": "meetstream"},
        "model": {"provider": "openai", "model": "gpt-4.1", "key_source": "meetstream"},
        "voice": {"provider": "openai", "voice_id": "coral", "key_source": "meetstream"},
    })
    assert out["agent_config_id"] == "a2"
    body = _body(calls[0])
    assert [body[k]["key_source"] for k in ("transcriber", "model", "voice")] == ["meetstream"] * 3
    assert body["transcriber"]["language"] == "es"
    assert "api_key" not in body["model"]


def test_mia_create_local_agent_and_v1_10_agent_options():
    client, calls = make_client({"status": 201, "body": {"agent_config_id": "a3"}})
    client.mia.create({
        "agent_name": "Mine",
        "mode": "pipeline",
        "transcriber": {"provider": "deepgram", "key_source": "user"},
        "voice": {"provider": "openai", "voice_id": "coral"},
        "model": {"provider": "local_agent", "local_agent": {"url": "https://bridge.example.com", "access": "readonly"}},
        "agent": {"tools": ["screen"], "chat_input": True, "quiet_actions": True, "speak_only_when_asked": True},
    })
    body = _body(calls[0])
    assert body["model"] == {"provider": "local_agent", "local_agent": {"url": "https://bridge.example.com", "access": "readonly"}}
    assert body["agent"] == {"tools": ["screen"], "chat_input": True, "quiet_actions": True, "speak_only_when_asked": True}


def test_mia_check_local_agent():
    client, calls = make_client({"body": {"local_agent": {"status": "ok", "latency_ms": 40}}})
    assert client.mia.check_local_agent("a3")["local_agent"]["status"] == "ok"
    assert calls[0].url.path == "/api/v1/mia"
    assert dict(calls[0].url.params) == {"agent_config_id": "a3", "check": "local_agent"}


def test_mia_update_live_posts_update_mia_with_wait_for_ack():
    client, calls = make_client({"body": {"status": "partially_applied", "bot_id": "b1", "command": "update_mia"}})
    out = client.mia.update_live("b1", {"wake_words": ["hey acme"]}, wait_for_ack=True)
    assert out["status"] == "partially_applied"
    assert calls[0].method == "POST"
    assert calls[0].url.path == "/api/v1/bots/b1/update_mia"
    assert _body(calls[0]) == {"wake_words": ["hey acme"], "wait_for_ack": True}


def test_create_bot_with_agent_config_id_only():
    client, calls = make_client({"status": 201, "body": {"bot_id": "b9"}})
    client.bots.create({"meeting_link": "https://meet.google.com/a-b-c", "agent_config_id": "a1"})
    body = _body(calls[0])
    assert body["agent_config_id"] == "a1"
    assert "socket_connection_url" not in body and "live_audio_required" not in body


def test_inbuilt_keys_unavailable_is_detected():
    client, _ = make_client({"status": 400, "body": {"message": "MeetStream-managed keys are not available for voice. Use your own key."}})
    with pytest.raises(BadRequestError) as info:
        client.mia.create({"agent_name": "x", "mode": "pipeline", "voice": {"provider": "openai", "key_source": "meetstream"}})
    assert is_inbuilt_keys_unavailable(info.value)
    assert not is_inbuilt_keys_unavailable(BadRequestError("API key not configured for: openai"))


# ------------------------------------------------- 1.4.0: failed transcript

FAILED = {
    "message": "Transcript processing failed: provider authentication was rejected. Check the API key.",
    "transcript_status": "Failed",
    "transcript_id": "t1",
}


def test_422_failed_transcript_is_typed_and_not_retried():
    client, calls = make_client({"status": 422, "body": FAILED}, max_retries=2)
    with pytest.raises(TranscriptFailedError) as info:
        client.transcripts.get("t1")
    err = info.value
    assert isinstance(err, MeetStreamError)
    assert err.status == 422
    assert err.transcript_status == "Failed"
    assert err.transcript_id == "t1"
    assert err.reason == "provider authentication was rejected. Check the API key."
    assert len(calls) == 1


def test_get_by_bot_and_wait_for_stop_on_failed_transcript():
    client, calls = make_client({"status": 422, "body": FAILED})
    with pytest.raises(TranscriptFailedError):
        client.transcripts.get_by_bot("b1")
    with pytest.raises(TranscriptFailedError):
        client.transcripts.wait_for("t1", timeout=5, interval=0.01)
    assert len(calls) == 2


def test_422_without_transcript_status_is_plain_error():
    client, _ = make_client({"status": 422, "body": {"message": "Unprocessable"}})
    with pytest.raises(MeetStreamError) as info:
        client.bots.status("b1")
    assert not isinstance(info.value, TranscriptFailedError)


# ----------------------------------------------------------- 1.4.0: billing


def test_billing_balance_reads_the_route():
    client, calls = make_client({"body": {"customer_type": "pay_as_you_go", "balance_usd": "12.34", "currency": "USD"}})
    assert client.billing.balance()["balance_usd"] == "12.34"
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/api/v1/billing/balance"


def test_billing_balance_invoice_account_is_none():
    client, _ = make_client({"body": {"customer_type": "invoice", "balance_usd": None, "currency": "USD"}})
    assert client.billing.balance()["balance_usd"] is None


def test_billing_balance_404_is_balance_unavailable_and_not_retried():
    client, calls = make_client({"status": 404, "body": {"message": "Route not found"}}, max_retries=2)
    with pytest.raises(BalanceUnavailableError) as info:
        client.billing.balance()
    assert isinstance(info.value, NotFoundError)
    assert info.value.billing_url == "https://app.meetstream.ai/billing"
    assert "app.meetstream.ai/billing" in info.value.message
    assert len(calls) == 1


async def test_async_agents_balance_and_failed_transcript():
    client, calls = make_async_client([
        {"body": {"AgentConfigID": "a1"}},
        {"body": {"local_agent": {"status": "unreachable"}}},
        {"body": {"status": "accepted", "bot_id": "b1", "command": "update_mia"}},
        {"status": 404, "body": {"message": "Route not found"}},
        {"status": 422, "body": FAILED},
    ])
    assert (await client.mia.get("a1"))["AgentConfigID"] == "a1"
    assert (await client.mia.check_local_agent("a1"))["local_agent"]["status"] == "unreachable"
    await client.mia.update_live("b1", {"system_prompt": "x"}, wait_for_ack=False)
    with pytest.raises(BalanceUnavailableError):
        await client.billing.balance()
    with pytest.raises(TranscriptFailedError):
        await client.transcripts.get("t1")
    assert _body(calls[2]) == {"system_prompt": "x", "wait_for_ack": False}
    assert calls[1].url.params["check"] == "local_agent"


# Live shape, captured from a `meetstream` provider transcript:
# participant.name + words[].text, with no flat speaker/transcript field.
LIVE_SEGMENTS = [
    {
        "participant": {"id": 100, "name": "Nav", "platform": "desktop"},
        "words": [
            {"text": "I'll", "start_timestamp": {"relative": 31.4, "absolute": 31.4},
             "end_timestamp": {"relative": 31.6, "absolute": 31.6}},
            {"text": "write the migration doc by Friday.", "start_timestamp": {"relative": 32.0, "absolute": 32.0},
             "end_timestamp": {"relative": 34.0, "absolute": 34.0}},
        ],
        "language_code": "en",
    },
    {"participant": {"id": 101, "name": "", "platform": "desktop"}, "words": [{"text": ""}]},
]


def test_segment_helpers_read_the_live_shape():
    from meetstream import segment_speaker, segment_start, segment_text

    client, _ = make_client({"body": LIVE_SEGMENTS})
    segments = client.transcripts.get("tr_1")
    assert segment_speaker(segments[0]) == "Nav"
    assert segment_text(segments[0]) == "I'll write the migration doc by Friday."
    assert segment_start(segments[0]) == 31.4
    assert segment_speaker(segments[1]) == "Unknown"
    assert segment_text(segments[1]) == ""
    assert segment_start({}) is None


def test_segment_helpers_still_read_the_flat_shape():
    from meetstream import segment_speaker, segment_start, segment_text

    flat = {"speaker": "Alice", "transcript": "hello there", "start_time": 0}
    assert segment_speaker(flat) == "Alice"
    assert segment_text(flat) == "hello there"
    assert segment_start(flat) == 0.0


# MS-2488: SDK flow gaps ---------------------------------------------------------

TS_NOW = 1795098600.0  # 2026-11-19T14:30:00Z


def _signed(body):
    raw = json.dumps(body)
    return raw, hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()


def test_timestamp_tolerance_is_off_by_default():
    assert verify_webhook_signature(BODY, SIG, SECRET) is True
    assert verify_webhook_signature(BODY, SIG, SECRET, timestamp="not a date") is True


def test_timestamp_tolerance_header_and_body_match_and_fresh_accepted():
    raw, sig = _signed({"event": "bot.joining", "bot_id": "b1", "timestamp": "2026-11-19T14:28:00Z"})
    kw = dict(timestamp="2026-11-19T14:28:00Z", tolerance_seconds=300, now=TS_NOW)
    assert verify_webhook_signature(raw, "sha256=" + sig, SECRET, **kw) is True
    assert verify_webhook_signature(raw.encode(), sig, SECRET, **kw) is True
    assert parse_webhook(raw, sig, SECRET, **kw)["bot_id"] == "b1"
    # Same instant, other ISO spelling.
    assert verify_webhook_signature(raw, sig, SECRET, timestamp="2026-11-19T14:28:00.000+00:00",
                                    tolerance_seconds=300, now=TS_NOW) is True
    # No header: the signed body alone decides.
    assert verify_webhook_signature(raw, sig, SECRET, tolerance_seconds=300, now=TS_NOW) is True
    # Future timestamp inside the window (clock skew).
    raw2, sig2 = _signed({"timestamp": "2026-11-19T14:31:00Z"})
    assert verify_webhook_signature(raw2, sig2, SECRET, tolerance_seconds=300, now=TS_NOW) is True


def test_timestamp_tolerance_replayed_old_body_with_fresh_header_rejected():
    raw, sig = _signed({"event": "bot.joining", "timestamp": "2026-11-19T14:00:00Z"})
    kw = dict(timestamp="2026-11-19T14:30:00Z", tolerance_seconds=300, now=TS_NOW)
    assert verify_webhook_signature(raw, sig, SECRET, **kw) is False
    with pytest.raises(ValueError):
        parse_webhook(raw, sig, SECRET, **kw)
    # Header matching the old body is still outside the window.
    assert verify_webhook_signature(raw, sig, SECRET, timestamp="2026-11-19T14:00:00Z",
                                    tolerance_seconds=300, now=TS_NOW) is False


def test_timestamp_tolerance_header_differs_from_fresh_body_rejected():
    raw, sig = _signed({"timestamp": "2026-11-19T14:29:00Z"})
    assert verify_webhook_signature(raw, sig, SECRET, timestamp="2026-11-19T14:29:30Z",
                                    tolerance_seconds=300, now=TS_NOW) is False
    assert verify_webhook_signature(raw, sig, SECRET, timestamp="garbage",
                                    tolerance_seconds=300, now=TS_NOW) is False


def test_timestamp_tolerance_rejects_missing_or_bad_body_timestamp():
    raw, sig = _signed({"event": "bot.joining"})
    assert verify_webhook_signature(raw, sig, SECRET, timestamp="2026-11-19T14:30:00Z",
                                    tolerance_seconds=300, now=TS_NOW) is False
    raw, sig = _signed({"timestamp": 1763562600})
    assert verify_webhook_signature(raw, sig, SECRET, tolerance_seconds=300, now=TS_NOW) is False
    not_json = "not json"
    sig = hmac.new(SECRET.encode(), not_json.encode(), hashlib.sha256).hexdigest()
    assert verify_webhook_signature(not_json, sig, SECRET, tolerance_seconds=300, now=TS_NOW) is False
    raw, _ = _signed({"timestamp": "2026-11-19T14:30:00Z"})
    assert verify_webhook_signature(raw, "bad", SECRET, tolerance_seconds=300, now=TS_NOW) is False


def test_is_final_segment():
    base = {"bot_id": "b1", "speakerName": "Ada", "transcript": "hello"}
    assert is_final_segment(dict(base, is_final=False)) is False
    assert is_final_segment(dict(base)) is False
    assert is_final_segment(dict(base, is_final=True)) is True
    assert is_final_segment(dict(base, transcription_mode="raw", is_final=False)) is False
    assert is_final_segment(dict(base, transcription_mode="raw", end_of_turn=True)) is True
    assert is_final_segment(dict(base, transcription_mode="raw", end_of_turn=False)) is False
    assert is_final_segment(dict(base, transcription_mode="sentence", end_of_turn=True)) is True
    assert is_final_segment(dict(base, transcription_mode="sentence")) is True
    assert is_final_segment(dict(base, transcription_mode="word_level", utterance="")) is True


def test_custom_function_header_names():
    assert BOT_ID_HEADER == "X-Bot-ID"
    assert AGENT_ID_HEADER == "X-Agent-ID"


def test_parse_custom_function_call_envelope():
    body = {"name": "lookup_order", "bot": {"bot_id": "b1", "dynamic_vars": {"tier": "gold"}, "agent_id": "a1"},
            "args": {"order_id": "42"}}
    out = parse_custom_function_call(json.dumps(body), {"x-bot-id": "b1", "x-agent-id": "a1"})
    assert out["name"] == "lookup_order"
    assert out["bot_id"] == "b1"
    assert out["agent_id"] == "a1"
    assert out["args"] == {"order_id": "42"}
    assert out["bot"]["dynamic_vars"] == {"tier": "gold"}
    # bytes and dict bodies, no headers: falls back to the body's bot block
    assert parse_custom_function_call(json.dumps(body).encode())["bot_id"] == "b1"
    assert parse_custom_function_call(body)["agent_id"] == "a1"


def test_parse_custom_function_call_prefers_header():
    body = {"name": "f", "bot": {"bot_id": "from-body"}, "args": {}}
    out = parse_custom_function_call(body, {"X-Bot-ID": "from-header"})
    assert out["bot_id"] == "from-header"
    assert out["agent_id"] is None
    assert parse_custom_function_call(body, httpx.Headers({"x-bot-id": "hx"}))["bot_id"] == "hx"


def test_parse_custom_function_call_payload_args_only():
    out = parse_custom_function_call('{"order_id": "42"}', {"X-Bot-ID": "b1"})
    assert out == {"name": None, "bot_id": "b1", "agent_id": None, "args": {"order_id": "42"}}
    tricky = {"name": "x", "bot": {"bot_id": "y"}, "args": {"z": 1}}
    forced = parse_custom_function_call(tricky, {"x-bot-id": "b1"}, payload_args_only=True)
    assert forced["name"] is None
    assert forced["args"] == tricky
    assert parse_custom_function_call("", {"x-bot-id": "b1"})["args"] == {}


def test_send_message_metadata():
    client, calls = make_client({"body": {"status": "sent"}})
    client.bots.send_message("b1", "hi")
    client.bots.send_message("b1", "hi", metadata={"k": "v"})
    assert json.loads(calls[0].content) == {"message": "hi"}
    assert json.loads(calls[1].content) == {"message": "hi", "metadata": {"k": "v"}}


def test_send_image_img_url_unchanged_and_base64_img():
    client, calls = make_client({"body": {"status": "sent"}})
    client.bots.send_image("b1", "https://x.example/a.png", 5)
    client.bots.send_image("b1", img="aGVsbG8=", display_duration=3, metadata={"k": "v"})
    assert json.loads(calls[0].content) == {"img_url": "https://x.example/a.png", "display_duration": 5}
    assert json.loads(calls[1].content) == {"img": "aGVsbG8=", "display_duration": 3, "metadata": {"k": "v"}}
    with pytest.raises(ValueError):
        client.bots.send_image("b1")


async def test_async_send_message_and_image_parity():
    client, calls = make_async_client({"body": {"status": "sent"}})
    await client.bots.send_message("b1", "hi", metadata={"k": "v"})
    await client.bots.send_image("b1", img="aGVsbG8=", metadata={"k": "v"})
    await client.bots.send_image("b1", "https://x.example/a.png")
    assert json.loads(calls[0].content) == {"message": "hi", "metadata": {"k": "v"}}
    assert json.loads(calls[1].content) == {"img": "aGVsbG8=", "metadata": {"k": "v"}}
    assert json.loads(calls[2].content) == {"img_url": "https://x.example/a.png"}
    with pytest.raises(ValueError):
        await client.bots.send_image("b1")
