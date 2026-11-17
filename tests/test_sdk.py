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
    PARTICIPANT_HAND_EVENTS,
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
    with pytest.warns(DeprecationWarning, match="no summary endpoint"):
        client.bots.summary("b1")
    assert calls[0].url.path.endswith("/bots/b1/summary")


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
    client, _ = make_async_client({"body": {}})
    with pytest.warns(DeprecationWarning):
        await client.bots.summary("b1")
    with pytest.warns(DeprecationWarning):
        await client.calendar.toggle_recurrence()
    with pytest.warns(DeprecationWarning):
        await client.storage.get()
    await client.aclose()

