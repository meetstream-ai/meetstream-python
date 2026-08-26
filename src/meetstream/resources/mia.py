"""MIA: MeetStream Infrastructure Agents.

AI participants that listen and speak in a live meeting. MeetStream hosts the
audio bridge, so you host nothing.

Flow: create a config here, then pass the returned ``agent_config_id`` to
``bots.create()``. That single field is all a MIA bot needs.
"""
from __future__ import annotations

from typing import Any, Dict


class Mia:
    """Synchronous MIA agent-config operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Create an agent config. Returns an ``agent_config_id``."""
        return self._t.post("/mia", params, **kw)

    def list(self, agent_config_id: str = None, **kw: Any) -> Any:  # noqa: RUF013
        """List configs, or fetch one by passing ``agent_config_id``."""
        return self._t.get("/mia", params={"agent_config_id": agent_config_id}, **kw)

    def update(self, agent_config_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        body = dict(params)
        body["agent_config_id"] = agent_config_id
        return self._t.put("/mia", body, **kw)

    def delete(self, agent_config_id: str, **kw: Any) -> Any:
        return self._t.delete("/mia", params={"agent_config_id": agent_config_id}, **kw)


class AsyncMia(Mia):
    """Asynchronous MIA agent-config operations."""

    async def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/mia", params, **kw)

    async def list(self, agent_config_id: str = None, **kw: Any) -> Any:  # noqa: RUF013
        return await self._t.get("/mia", params={"agent_config_id": agent_config_id}, **kw)

    async def update(self, agent_config_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        body = dict(params)
        body["agent_config_id"] = agent_config_id
        return await self._t.put("/mia", body, **kw)

    async def delete(self, agent_config_id: str, **kw: Any) -> Any:
        return await self._t.delete("/mia", params={"agent_config_id": agent_config_id}, **kw)
