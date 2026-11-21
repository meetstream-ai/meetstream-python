"""Agents API (MIA): voice agents in the meeting.

The agent rides on a bot: it hears the meeting and answers by voice, in the
chat, or with silent tool calls.

Flow: save an agent config here, then pass the returned ``agent_config_id`` to
``bots.create()``. That single field is all an agent bot needs. To change a
running agent mid-call, use :meth:`Mia.update_live` (same call as
``bots.update_mia()``).

Keys: each pipeline section (``transcriber``, ``model``, ``voice``) uses
MeetStream's inbuilt keys with ``"key_source": "meetstream"`` (no
``api_key``), or your own key (``"user"`` or omitted). While inbuilt keys are
not on for your account, the API answers 400 and
:func:`meetstream.is_inbuilt_keys_unavailable` is true: use your own key for
that section. ``model.provider: "local_agent"`` runs your own agent through the
MeetStream Agent Kit (needs the local agent feature on for your account). See
https://docs.meetstream.ai/guides/mia/pricing-and-keys and
https://docs.meetstream.ai/guides/mia/mia-api-guide.

Secrets come back masked: header values in ``mcp_servers`` and
``custom_functions`` and ``api_key``-like fields read as ``****`` plus the last
four characters. Sending a masked value back in :meth:`Mia.update` keeps the
stored secret.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote


def _live_body(params: Dict[str, Any], wait_for_ack: Optional[bool]) -> Dict[str, Any]:
    body = dict(params)
    if wait_for_ack is not None:
        body["wait_for_ack"] = wait_for_ack
    return body


class Mia:
    """Synchronous agent-config operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Save an agent config. Returns ``{"agent_config_id", "agent_config", ...}``."""
        return self._t.post("/mia", params, **kw)

    def get(self, agent_config_id: str, **kw: Any) -> Any:
        """One agent config by id."""
        return self._t.get("/mia", params={"agent_config_id": agent_config_id}, **kw)

    def list(self, agent_config_id: str = None, **kw: Any) -> Any:  # noqa: RUF013
        """List configs, or fetch one by passing ``agent_config_id``."""
        return self._t.get("/mia", params={"agent_config_id": agent_config_id}, **kw)

    def update(self, agent_config_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        """Update a saved config (``PUT``). Each block you send replaces the stored block."""
        body = dict(params)
        body["agent_config_id"] = agent_config_id
        return self._t.put("/mia", body, **kw)

    def delete(self, agent_config_id: str, **kw: Any) -> Any:
        return self._t.delete("/mia", params={"agent_config_id": agent_config_id}, **kw)

    def check_local_agent(self, agent_config_id: str, **kw: Any) -> Any:
        """Test the connection to your local agent bridge (``model.provider: "local_agent"``).

        Returns ``{"local_agent": {"status": "ok", "latency_ms", "agent", ...}}``,
        or another ``status`` (``login_expired``, ``not_installed``, ``no_token``,
        ``token_rejected``, ``unreachable``, ``bad_url``, ``not_local_agent``).
        """
        return self._t.get("/mia", params={"agent_config_id": agent_config_id, "check": "local_agent"}, **kw)

    def update_live(
        self, bot_id: str, params: Dict[str, Any], *, wait_for_ack: Optional[bool] = None, **kw: Any
    ) -> Any:
        """Update the agent of a bot that is in a meeting. The saved config does not change.

        ``params``: any of ``agent_config_params``, ``system_prompt``,
        ``wake_word_enabled``, ``wake_words``. With ``wait_for_ack=True`` the
        response ``status`` is ``applied``, ``partially_applied``, ``failed``
        or ``accepted`` (no answer in time). Same call as ``bots.update_mia()``.
        """
        return self._t.post(f"/bots/{quote(str(bot_id), safe='')}/update_mia", _live_body(params, wait_for_ack), **kw)


class AsyncMia(Mia):
    """Asynchronous agent-config operations."""

    async def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/mia", params, **kw)

    async def get(self, agent_config_id: str, **kw: Any) -> Any:
        return await self._t.get("/mia", params={"agent_config_id": agent_config_id}, **kw)

    async def list(self, agent_config_id: str = None, **kw: Any) -> Any:  # noqa: RUF013
        return await self._t.get("/mia", params={"agent_config_id": agent_config_id}, **kw)

    async def update(self, agent_config_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        body = dict(params)
        body["agent_config_id"] = agent_config_id
        return await self._t.put("/mia", body, **kw)

    async def delete(self, agent_config_id: str, **kw: Any) -> Any:
        return await self._t.delete("/mia", params={"agent_config_id": agent_config_id}, **kw)

    async def check_local_agent(self, agent_config_id: str, **kw: Any) -> Any:
        return await self._t.get("/mia", params={"agent_config_id": agent_config_id, "check": "local_agent"}, **kw)

    async def update_live(
        self, bot_id: str, params: Dict[str, Any], *, wait_for_ack: Optional[bool] = None, **kw: Any
    ) -> Any:
        return await self._t.post(
            f"/bots/{quote(str(bot_id), safe='')}/update_mia", _live_body(params, wait_for_ack), **kw
        )
