"""Calendar connection, event sync, scheduling and auto-join."""
from __future__ import annotations

import warnings
from typing import Any, Dict, Optional
from urllib.parse import quote

_RECURRENCE_GONE = (
    "calendar.toggle_recurrence() is deprecated: the MeetStream API does not serve this route "
    "and the call returns 404. Use enable_auto_schedule() / disable_auto_schedule()."
)


def _p(value: str) -> str:
    return quote(str(value), safe="")


def _with_params(kw: Dict[str, Any], values: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge query params (skipping ``None``) into the request kwargs."""
    extra = {k: v for k, v in (values or {}).items() if v is not None}
    if not extra:
        return kw
    params = dict(kw.pop("params", None) or {})
    params.update(extra)
    return {**kw, "params": params}


class Calendar:
    """Synchronous calendar operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def list(self, *, provider: Optional[str] = None, account_id: Optional[str] = None, **kw: Any) -> Any:
        """The calendars on every connected Google and Outlook account.

        Narrow with ``provider`` (``"google"`` or ``"outlook"``) and, with it,
        ``account_id`` (the connected account's email).
        """
        return self._t.get("/calendar/calendars", **_with_params(kw, {"provider": provider, "account_id": account_id}))

    def connect_google(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Connect a Google calendar with OAuth credentials."""
        return self._t.post("/calendar/create_calendar", params, **kw)

    def connect_outlook(self, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.post("/calendar/create_outlook_calendar", params, **kw)

    def disconnect(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        """Disconnect a calendar account. This is a DELETE on the API.

        ``params``: ``provider`` (default ``"all"``), ``account_id`` (needed
        when several accounts are connected) and ``purge_events`` (default
        ``True``: synced events and the bots scheduled from them are deleted).
        """
        return self._t.delete("/calendar/disconnect", **_with_params(kw, params))

    def list_connections(self, *, limit: Optional[int] = None, cursor: Optional[str] = None, **kw: Any) -> Any:
        """Connected calendar accounts and their status. Page with ``next_cursor``."""
        return self._t.get("/calendar/connections", **_with_params(kw, {"limit": limit, "cursor": cursor}))

    def get_connection(self, provider: str, account_id: str, **kw: Any) -> Any:
        """One connected account. ``provider`` is ``"google"`` or ``"outlook"``; ``account_id`` is its email."""
        return self._t.get(f"/calendar/connections/{_p(provider)}/{_p(account_id)}", **kw)

    def delete_connection(
        self, provider: str, account_id: str, *, purge_events: Optional[bool] = None, **kw: Any
    ) -> Any:
        """Disconnect one account. By default its synced events and scheduled bots go too."""
        return self._t.delete(
            f"/calendar/connections/{_p(provider)}/{_p(account_id)}",
            **_with_params(kw, {"purge_events": purge_events}),
        )

    def events(self, **kw: Any) -> Any:
        return self._t.get("/calendar/events", **kw)

    def schedule_event(self, event_id: str, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        """Schedule a bot for one event. ``body`` takes the create_bot options (``zoom.use_own_app`` included).

        409 means the occurrence is already scheduled.
        """
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
        """Deprecated: the API does not serve this route, so this returns 404."""
        warnings.warn(_RECURRENCE_GONE, DeprecationWarning, stacklevel=2)
        return self._t.post("/calendar/toggle-recurrence", body or {}, **kw)


class AsyncCalendar(Calendar):
    """Asynchronous calendar operations."""

    async def list(self, *, provider: Optional[str] = None, account_id: Optional[str] = None, **kw: Any) -> Any:
        return await self._t.get(
            "/calendar/calendars", **_with_params(kw, {"provider": provider, "account_id": account_id})
        )

    async def connect_google(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/calendar/create_calendar", params, **kw)

    async def connect_outlook(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/calendar/create_outlook_calendar", params, **kw)

    async def disconnect(self, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.delete("/calendar/disconnect", **_with_params(kw, params))

    async def list_connections(
        self, *, limit: Optional[int] = None, cursor: Optional[str] = None, **kw: Any
    ) -> Any:
        return await self._t.get("/calendar/connections", **_with_params(kw, {"limit": limit, "cursor": cursor}))

    async def get_connection(self, provider: str, account_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/calendar/connections/{_p(provider)}/{_p(account_id)}", **kw)

    async def delete_connection(
        self, provider: str, account_id: str, *, purge_events: Optional[bool] = None, **kw: Any
    ) -> Any:
        return await self._t.delete(
            f"/calendar/connections/{_p(provider)}/{_p(account_id)}",
            **_with_params(kw, {"purge_events": purge_events}),
        )

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
        warnings.warn(_RECURRENCE_GONE, DeprecationWarning, stacklevel=2)
        return await self._t.post("/calendar/toggle-recurrence", body or {}, **kw)
