"""Account billing. Read only. Top up at https://app.meetstream.ai/billing."""
from __future__ import annotations

from typing import Any

from .._errors import BalanceUnavailableError, NotFoundError

_UNAVAILABLE = (
    "The balance endpoint is not available for this account yet. "
    "See your balance at https://app.meetstream.ai/billing"
)


def _unavailable(exc: NotFoundError) -> BalanceUnavailableError:
    return BalanceUnavailableError(_UNAVAILABLE, status=exc.status, body=exc.body, request_id=exc.request_id)


class Billing:
    """Synchronous billing reads."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def balance(self, **kw: Any) -> Any:
        """Your prepaid balance: ``{"customer_type", "balance_usd", "currency"}``.

        ``balance_usd`` is a decimal string such as ``"12.34"``, or ``None`` for
        accounts billed by invoice. Available when the balance endpoint is on
        for your account; until then the API answers 404 and this raises
        :class:`~meetstream.BalanceUnavailableError` (not retried).
        """
        try:
            return self._t.get("/billing/balance", **kw)
        except NotFoundError as exc:
            raise _unavailable(exc) from None


class AsyncBilling(Billing):
    """Asynchronous billing reads."""

    async def balance(self, **kw: Any) -> Any:
        try:
            return await self._t.get("/billing/balance", **kw)
        except NotFoundError as exc:
            raise _unavailable(exc) from None
