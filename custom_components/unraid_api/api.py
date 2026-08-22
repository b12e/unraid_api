"""API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .const import QUERY
from .models import QueryResponse

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


def _format_errors(errors: Any) -> str:
    """Build a readable message from a GraphQL errors array."""
    if not isinstance(errors, list):
        return str(errors)

    messages = []
    for entry in errors:
        message = entry.get("message") if isinstance(entry, dict) else None
        messages.append(str(message) if message else str(entry))
    return ", ".join(messages) or "Unknown GraphQL error"


class UnraidGraphQLError(Exception):
    """Raised when the response contains errors."""


class UnraidApiClient:
    """Unraid GraphQL API Client."""

    def __init__(self, host: str, api_key: str, session: ClientSession) -> None:
        self.host = host.rstrip("/")
        self.endpoint = self.host + "/graphql"
        self.api_key = api_key
        self.session = session

    async def call_api(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict:
        import json        
        payload = {"query": query, "variables": variables or {}}

        response = await self.session.post(
            self.endpoint,
            data=json.dumps(payload),
            headers={
                "x-api-key": self.api_key,
                "Origin": self.host,
                "content-type": "application/json",
            },
        )
        result = await response.json()

        if result.get("errors"):
            error_msg = _format_errors(result["errors"])
            _LOGGER.error("Error in query response: %s", error_msg)
            raise UnraidGraphQLError(error_msg)

        if "data" not in result:
            msg = f"Unexpected response without data: {result}"
            raise UnraidGraphQLError(msg)
        return result["data"]

    async def query(self) -> QueryResponse:
        response = await self.call_api(QUERY)
        return QueryResponse.model_validate(response)
