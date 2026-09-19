"""Google signed-in bots, Zoom OAuth, and bring-your-own-bucket storage."""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote


def _p(value: str) -> str:
    return quote(str(value), safe="")


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

    def list(self, **kw: Any) -> Any:
        return self._t.get("/google-logins", **kw)

    def update(self, login_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        return self._t.patch(f"/google-logins/{_p(login_id)}", params, **kw)

    def delete(self, login_id: str, **kw: Any) -> Any:
        return self._t.delete(f"/google-logins/{_p(login_id)}", **kw)


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

    async def list(self, **kw: Any) -> Any:
        return await self._t.get("/google-logins", **kw)

    async def update(self, login_id: str, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.patch(f"/google-logins/{_p(login_id)}", params, **kw)

    async def delete(self, login_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/google-logins/{_p(login_id)}", **kw)


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
