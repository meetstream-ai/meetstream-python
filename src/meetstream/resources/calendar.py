"""Calendar connection, event sync, scheduling and auto-join."""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote


def _p(value: str) -> str:
    return quote(str(value), safe="")


class Calendar:
    """Synchronous calendar operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def list(self, **kw: Any) -> Any:
        return self._t.get("/calendar", **kw)

    def connect_google(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Connect a Google calendar with OAuth credentials."""
        return self._t.post("/calendar/create_calendar", params, **kw)

    def connect_outlook(self, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.post("/calendar/create_outlook_calendar", params, **kw)

    def disconnect(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return self._t.post("/calendar/disconnect", params or {}, **kw)

    def events(self, **kw: Any) -> Any:
        return self._t.get("/calendar/events", **kw)

    def schedule_event(self, event_id: str, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return self._t.post(f"/calendar/schedule/{_p(event_id)}", body or {}, **kw)

    def unschedule_event(self, event_id: str, **kw: Any) -> Any:
        return self._t.delete(f"/calendar/schedule/{_p(event_id)}", **kw)

    def list_scheduled_bots(self, **kw: Any) -> Any:
        return self._t.get("/calendar/scheduled_bots", **kw)

    def reschedule_bot(self, bot_id: str, scheduled_join_time: str, **kw: Any) -> Any:
        """Move a scheduled bot.

        The body field is ``scheduled_join_time``; ``join_at`` is create-bot only.
        """
        return self._t.patch(
            f"/calendar/scheduled_bots/{_p(bot_id)}", {"scheduled_join_time": scheduled_join_time}, **kw
        )

    def delete_scheduled_bot(self, bot_id: str, **kw: Any) -> Any:
        return self._t.delete(f"/calendar/scheduled_bots/{_p(bot_id)}", **kw)

    def enable_auto_schedule(self, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return self._t.post("/calendar/auto-schedule/enable", body or {}, **kw)

    def disable_auto_schedule(self, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return self._t.post("/calendar/auto-schedule/disable", body or {}, **kw)

    def auto_schedule_settings(self, **kw: Any) -> Any:
        return self._t.get("/calendar/auto-schedule/settings", **kw)

    def toggle_recurrence(self, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return self._t.post("/calendar/toggle-recurrence", body or {}, **kw)


class AsyncCalendar(Calendar):
    """Asynchronous calendar operations."""

    async def list(self, **kw: Any) -> Any:
        return await self._t.get("/calendar", **kw)

    async def connect_google(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/calendar/create_calendar", params, **kw)

    async def connect_outlook(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/calendar/create_outlook_calendar", params, **kw)

    async def disconnect(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.post("/calendar/disconnect", params or {}, **kw)

    async def events(self, **kw: Any) -> Any:
        return await self._t.get("/calendar/events", **kw)

    async def schedule_event(self, event_id: str, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.post(f"/calendar/schedule/{_p(event_id)}", body or {}, **kw)

    async def unschedule_event(self, event_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/calendar/schedule/{_p(event_id)}", **kw)

    async def list_scheduled_bots(self, **kw: Any) -> Any:
        return await self._t.get("/calendar/scheduled_bots", **kw)

    async def reschedule_bot(self, bot_id: str, scheduled_join_time: str, **kw: Any) -> Any:
        return await self._t.patch(
            f"/calendar/scheduled_bots/{_p(bot_id)}", {"scheduled_join_time": scheduled_join_time}, **kw
        )

    async def delete_scheduled_bot(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/calendar/scheduled_bots/{_p(bot_id)}", **kw)

    async def enable_auto_schedule(self, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.post("/calendar/auto-schedule/enable", body or {}, **kw)

    async def disable_auto_schedule(self, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.post("/calendar/auto-schedule/disable", body or {}, **kw)

    async def auto_schedule_settings(self, **kw: Any) -> Any:
        return await self._t.get("/calendar/auto-schedule/settings", **kw)

    async def toggle_recurrence(self, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.post("/calendar/toggle-recurrence", body or {}, **kw)
