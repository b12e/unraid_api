"""API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .const import QUERY
from .models import QueryResponse

if TYPE_CHECKING:
    from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)


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
        response = await self.session.post(
            self.endpoint,
            json={"query": query, "variables": variables or {}},
            headers={
                "x-api-key": self.api_key,
                "Origin": self.host,
            },
        )
        result = await response.json()

        import json        
        payload = {"query": query, "variables": variables or {}}
    
        # Generate equivalent curl command for debugging
        curl_headers = " ".join([f'-H "{k}: {v}"' for k, v in {
            "x-api-key": "***masked***",
            "Origin": self.host,
            "Content-Type": "application/json",
        }.items()])
    
        curl_command = f"""curl -X POST {self.endpoint} {curl_headers} -d '{json.dumps(payload)}'"""
    
        _LOGGER.error("%s", curl_command)
        result_string = json.dumps(result, indent=2)
        _LOGGER.error("Response JSON: %s", result_string)

        if "errors" in result:
            error_msg = ", ".join(entry.get("message") for entry in result["errors"])
            _LOGGER.error("Error in query response: %s", error_msg)
            raise UnraidGraphQLError(error_msg)
        return result["data"]

    async def query(self) -> QueryResponse:
        response = await self.call_api(QUERY)
        return QueryResponse.model_validate(response)
