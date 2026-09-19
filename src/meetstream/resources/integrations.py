"""Google and Teams signed-in bots, Zoom OAuth, and bring-your-own-bucket storage."""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote


def _p(value: str) -> str:
    return quote(str(value), safe="")


def _with_domain(domain: Optional[str], kw: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a ``domain`` filter into the request's query params."""
    if domain is None:
        return kw
    params = dict(kw.pop("params", None) or {})
    params["domain"] = domain
    return {**kw, "params": params}


class GoogleLogins:
    """Google signed-in bots.

    A signed-in bot authenticates as a real Workspace user before joining,
    which is the fix for a Google Meet bot getting stuck in the lobby as an
    unverified guest.

    Capacity rule of thumb: logins = peak concurrent Google Meet sessions / 20.
    MeetStream distributes bots across them round-robin.
    """

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create_domain(self, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.post("/google-login-domains", params, **kw)

    def list_domains(self, **kw: Any) -> Any:
        return self._t.get("/google-login-domains", **kw)

    def get_domain(self, domain: str, **kw: Any) -> Any:
        return self._t.get(f"/google-login-domains/{_p(domain)}", **kw)

    def update_domain(self, domain: str, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.patch(f"/google-login-domains/{_p(domain)}", params, **kw)

    def delete_domain(self, domain: str, **kw: Any) -> Any:
        return self._t.delete(f"/google-login-domains/{_p(domain)}", **kw)

    def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.post("/google-logins", params, **kw)

    def list(self, domain: Optional[str] = None, **kw: Any) -> Any:
        """List Google logins, optionally filtered to one registered ``domain``."""
        return self._t.get("/google-logins", **_with_domain(domain, kw))

    def update(self, login_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.patch(f"/google-logins/{_p(login_id)}", params, **kw)

    def delete(self, login_id: str, **kw: Any) -> Any:
        return self._t.delete(f"/google-logins/{_p(login_id)}", **kw)


class TeamsLogins:
    """Microsoft Teams signed-in bots.

    A signed-in Teams bot joins as a real Microsoft 365 work or school account
    (not teams.live.com) instead of an anonymous guest. Register a login
    domain, add accounts under it, then create bots with
    ``"teams": {"login_required": True, "teams_login_domain": domain}``.

    - One concurrent bot per Teams account. Register N accounts for N
      concurrent bots; when every account is busy, create returns 429.
    - ``bot_name`` and ``bot_image_url`` are not applied on a signed-in Teams
      join: the bot shows the Microsoft account's own display name and picture.
    - Passwords are write-only and never returned by any endpoint. Read them
      from an env var or secret store; never hardcode or log them.
    - ``login_mode`` currently supports ``"always"`` only for Teams.

    Guide: https://docs.meetstream.ai/guides/app-integrations/teams-signed-in-bots
    """

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create_domain(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Register a login domain. Body: ``{domain, name?, login_mode?: "always"}``."""
        return self._t.post("/teams-login-domains", params, **kw)

    def list_domains(self, **kw: Any) -> Any:
        """Returns ``{"domains": [...]}`` with login counts per domain."""
        return self._t.get("/teams-login-domains", **kw)

    def get_domain(self, domain: str, **kw: Any) -> Any:
        """One domain, including its logins (no passwords)."""
        return self._t.get(f"/teams-login-domains/{_p(domain)}", **kw)

    def update_domain(self, domain: str, params: Dict[str, Any], **kw: Any) -> Any:
        """Body: ``{name?, login_mode?}``."""
        return self._t.patch(f"/teams-login-domains/{_p(domain)}", params, **kw)

    def delete_domain(self, domain: str, **kw: Any) -> Any:
        """Deletes the domain and every login under it."""
        return self._t.delete(f"/teams-login-domains/{_p(domain)}", **kw)

    def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Add a Microsoft account. Body: ``{domain, email, password, is_active?}``.

        The password is write-only.
        """
        return self._t.post("/teams-logins", params, **kw)

    def list(self, domain: str, **kw: Any) -> Any:
        """List the logins under one domain. The domain is required by the API."""
        return self._t.get("/teams-logins", **_with_domain(domain, kw))

    def get(self, login_id: str, **kw: Any) -> Any:
        return self._t.get(f"/teams-logins/{_p(login_id)}", **kw)

    def update(self, login_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        """Body: ``{password?, is_active?}``. A new password also reactivates a deactivated account."""
        return self._t.patch(f"/teams-logins/{_p(login_id)}", params, **kw)

    def delete(self, login_id: str, **kw: Any) -> Any:
        return self._t.delete(f"/teams-logins/{_p(login_id)}", **kw)


class Zoom:
    """Zoom OAuth connections.

    .. deprecated:: 1.1.0
        These ``/zoom/oauth/*`` endpoints were removed from the MeetStream API
        reference. For authenticated Zoom joins, pass ``zoom={"zak_url": ...}``
        or ``zoom={"obf_url": ...}`` to ``bots.create`` instead. Kept for
        backwards compatibility.
    """

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def authorize_url(self, **kw: Any) -> Any:
        return self._t.get("/zoom/oauth/authorize-url", **kw)

    def create_connection(self, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.post("/zoom/oauth/connections", params, **kw)

    def list_connections(self, **kw: Any) -> Any:
        return self._t.get("/zoom/oauth/connections", **kw)

    def get_connection(self, zoom_user_id: str, **kw: Any) -> Any:
        return self._t.get(f"/zoom/oauth/connections/{_p(zoom_user_id)}", **kw)

    def delete_connection(self, zoom_user_id: str, **kw: Any) -> Any:
        return self._t.delete(f"/zoom/oauth/connections/{_p(zoom_user_id)}", **kw)


class Storage:
    """Bring-your-own-bucket storage.

    Two things to know before enabling this. It stores cloud credentials on
    your MeetStream account, so use a dedicated IAM user scoped to one bucket,
    never a root key. And with ``access_mode="write_only"`` MeetStream writes to
    your bucket but its own fetch endpoints return 403 for that media - you read
    it from your bucket, not from the API.

    Objects land under ``{prefix}/{bot_id}_<file>``.
    """

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def set(self, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.put("/admin/configs", params, params={"config_type": "storage"}, **kw)

    def get(self, **kw: Any) -> Any:
        return self._t.get("/admin/configs", **kw)

    def delete(self, key_name: str = "aws", **kw: Any) -> Any:
        return self._t.delete("/admin/configs", params={"key_name": key_name}, **kw)


class AsyncGoogleLogins(GoogleLogins):
    """Asynchronous Google signed-in bot operations."""

    async def create_domain(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/google-login-domains", params, **kw)

    async def list_domains(self, **kw: Any) -> Any:
        return await self._t.get("/google-login-domains", **kw)

    async def get_domain(self, domain: str, **kw: Any) -> Any:
        return await self._t.get(f"/google-login-domains/{_p(domain)}", **kw)

    async def update_domain(self, domain: str, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.patch(f"/google-login-domains/{_p(domain)}", params, **kw)

    async def delete_domain(self, domain: str, **kw: Any) -> Any:
        return await self._t.delete(f"/google-login-domains/{_p(domain)}", **kw)

    async def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/google-logins", params, **kw)

    async def list(self, domain: Optional[str] = None, **kw: Any) -> Any:
        return await self._t.get("/google-logins", **_with_domain(domain, kw))

    async def update(self, login_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.patch(f"/google-logins/{_p(login_id)}", params, **kw)

    async def delete(self, login_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/google-logins/{_p(login_id)}", **kw)


class AsyncTeamsLogins(TeamsLogins):
    """Asynchronous Microsoft Teams signed-in bot operations. See :class:`TeamsLogins`."""

    async def create_domain(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/teams-login-domains", params, **kw)

    async def list_domains(self, **kw: Any) -> Any:
        return await self._t.get("/teams-login-domains", **kw)

    async def get_domain(self, domain: str, **kw: Any) -> Any:
        return await self._t.get(f"/teams-login-domains/{_p(domain)}", **kw)

    async def update_domain(self, domain: str, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.patch(f"/teams-login-domains/{_p(domain)}", params, **kw)

    async def delete_domain(self, domain: str, **kw: Any) -> Any:
        return await self._t.delete(f"/teams-login-domains/{_p(domain)}", **kw)

    async def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/teams-logins", params, **kw)

    async def list(self, domain: str, **kw: Any) -> Any:
        return await self._t.get("/teams-logins", **_with_domain(domain, kw))

    async def get(self, login_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/teams-logins/{_p(login_id)}", **kw)

    async def update(self, login_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.patch(f"/teams-logins/{_p(login_id)}", params, **kw)

    async def delete(self, login_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/teams-logins/{_p(login_id)}", **kw)


class AsyncZoom(Zoom):
    """Asynchronous Zoom OAuth operations. Deprecated, see :class:`Zoom`."""

    async def authorize_url(self, **kw: Any) -> Any:
        return await self._t.get("/zoom/oauth/authorize-url", **kw)

    async def create_connection(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/zoom/oauth/connections", params, **kw)

    async def list_connections(self, **kw: Any) -> Any:
        return await self._t.get("/zoom/oauth/connections", **kw)

    async def get_connection(self, zoom_user_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/zoom/oauth/connections/{_p(zoom_user_id)}", **kw)

    async def delete_connection(self, zoom_user_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/zoom/oauth/connections/{_p(zoom_user_id)}", **kw)


class AsyncStorage(Storage):
    """Asynchronous storage-config operations."""

    async def set(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.put("/admin/configs", params, params={"config_type": "storage"}, **kw)

    async def get(self, **kw: Any) -> Any:
        return await self._t.get("/admin/configs", **kw)

    async def delete(self, key_name: str = "aws", **kw: Any) -> Any:
        return await self._t.delete("/admin/configs", params={"key_name": key_name}, **kw)
