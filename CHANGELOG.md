# Changelog

All notable changes to `meetstream-sdk`.

## 1.4.1 (2026-11-21)

### Fixed

- Transcript shape. `get_transcript` segments name the speaker in `participant.name` and hold the text in `words[].text`; the docs said `speaker` / `transcript`. New `TranscriptSegment`, `TranscriptWord`, `TranscriptParticipant` and `TranscriptTimestamp` types, and `segment_speaker()`, `segment_text()` and `segment_start()` helpers, which read this shape and the flat `speaker` / `transcript` shape. Tests cover both.
- Zoom wording in docstrings and type comments: Zoom bots join through your Zoom app (Meeting SDK) with an OBF token (`obf_url`) or a ZAK token (`zak_url`). The text no longer says Zoom needs no setup. `zoom.use_own_app` is unchanged.
- README and AGENTS.md state MeetStream's inbuilt keys per mode: Pipeline: OpenAI + Deepgram (Deepgram speech-to-text; OpenAI LLM and voice). Realtime: OpenAI only. Any other provider: bring your own key.

## 1.4.0 (2026-11-21)

Matches MeetStream API v1.10.0. Same surface as `@meetstream/sdk` 1.4.0.

### Added

- Agents API: `mia.get(agent_config_id)`, `mia.check_local_agent(agent_config_id)` (`GET /mia?check=local_agent`), and `mia.update_live(bot_id, params, wait_for_ack=...)` (same call as `bots.update_mia`). Sync and async.
- `key_source` (`"meetstream"` | `"user"`) on `transcriber`, `model` and `voice` (`KeySource`), for MeetStream's inbuilt keys or your own keys. `is_inbuilt_keys_unavailable(e)` detects the `400` the API returns while inbuilt keys are not on for an account.
- `model.provider: "local_agent"` (needs the local agent feature on for the account) with `MiaLocalAgentConfig` (`url`, `label`, `access`, `require_code`, `owner_only`, `owner_names`, `owner_ids`, `timeout_s`).
- Agent options in `MiaAgentOptions`: `tools` (`current_time`, `weather_now`, `screen`), `desktop`, `chat_input`, `quiet_actions`, `speak_only_when_asked`. `MiaTranscriberConfig.language` (unset, `multi` or `auto` = automatic detection), `MiaVoiceConfig`, `CreateMiaParams`, `LocalAgentCheck`. `UpdateMiaParams` gains `wait_for_ack`.
- `TranscriptFailedError`: a `422` from `get_transcript` carries `status`, `transcript_status`, `transcript_id` and `reason`. It is not retried, and `transcripts.wait_for` stops at once.
- `billing.balance()` for `GET /billing/balance` (`BillingBalance`: `customer_type`, `balance_usd`, `currency`). Available when the endpoint is on for the account; a `404` raises `BalanceUnavailableError` (with `billing_url`), not retried.

### Changed

- README opens with the two ways to integrate (Bot API, Agents API), a fastest path for each, the voice agent setups with prices, and a "Latest docs" section.

## 1.3.0 (2026-11-18)

- `bots.raise_hand`, `bots.lower_hand`, `bots.send_command`, and `bots.update_mia` with `wait_for_ack`.
- `bots.get`, `bots.stop_status`, `bots.screenshot`, `bots.speaker_timeline(download=True)`, `transcripts.get_by_bot`.
- `meeting_direct_connect.create`, `get`, `leave` (Zoom Meeting Direct Connect).
- New create fields and providers typed in `meetstream.types`; errors carry `retry_after` and `code`; an in-progress `409` on create is retried with the same key.
- Deprecated: `bots.summary()` and `calendar.toggle_recurrence()`. The API has no route for either.

## 1.2.1 and earlier

See the git history.
