"""Unraid update coordinator."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypedDict

from homeassistant.core import callback as ha_callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    SUB_ARRAY,
    SUB_CPU,
    SUB_CPU_TELEMETRY,
    SUB_MEMORY,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

    from . import UnraidConfigEntry
    from .api import UnraidApiClient
    from .models import Disk, QueryResponse, Share
    from .websocket import UnraidWebSocketClient

_LOGGER = logging.getLogger(__name__)


class UnraidServerData(TypedDict):  # noqa: D101
    data: QueryResponse
    disks: dict[str, Disk]
    shares: dict[str, Share]


POLL_INTERVAL_DEFAULT = timedelta(minutes=1)
POLL_INTERVAL_WSS_FALLBACK = timedelta(minutes=5)


class UnraidDataUpdateCoordinator(DataUpdateCoordinator[UnraidServerData]):
    """Update Coordinator with hybrid push/poll support."""

    known_disks: set[str]
    known_shares: set[str]

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: UnraidConfigEntry,
        api_client: UnraidApiClient,
        ws_client: UnraidWebSocketClient | None = None,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=POLL_INTERVAL_DEFAULT,
        )
        self.api_client = api_client
        self._ws_client = ws_client
        self._ws_tasks: list[asyncio.Task[None]] = []
        self._ws_connected = False
        self.disk_callbacks: set[Callable[[Disk], None]] = set()
        self.share_callbacks: set[Callable[[Share], None]] = set()

    async def _async_setup(self) -> None:
        self.known_disks: set[str] = set()
        self.known_shares: set[str] = set()
        await self._try_connect_ws()

    async def _async_update_data(self) -> UnraidServerData:
        query_response = await self.api_client.query()
        disks: dict[str, Disk] = {}
        shares: dict[str, Share] = {}
        new_disks: list[str] = []
        new_shares: list[str] = []

        for disk in query_response.array.disks:
            disks[disk.name] = disk
            if disk.name not in self.known_disks:
                self.known_disks.add(disk.name)
                new_disks.append(disk.name)

        for disk in query_response.array.parities:
            disks[disk.name] = disk
            if disk.name not in self.known_disks:
                self.known_disks.add(disk.name)
                new_disks.append(disk.name)

        for disk in query_response.array.caches:
            disks[disk.name] = disk
            if disk.name not in self.known_disks:
                self.known_disks.add(disk.name)
                new_disks.append(disk.name)

        for share in query_response.shares:
            shares[share.name] = share
            if share.name not in self.known_shares:
                self.known_shares.add(share.name)
                new_shares.append(share.name)

        result = UnraidServerData(data=query_response, disks=disks, shares=shares)

        if new_disks or new_shares:
            # Snapshot the currently registered callbacks: a platform that subscribes
            # between now and the task running gets these items from subscribe_*
            # already, so firing at it here too would create every entity twice.
            self.hass.async_create_task(
                self._fire_pending_callbacks(
                    result,
                    new_disks,
                    new_shares,
                    set(self.disk_callbacks),
                    set(self.share_callbacks),
                )
            )

        return result

    async def _fire_pending_callbacks(
        self,
        data: UnraidServerData,
        new_disks: list[str],
        new_shares: list[str],
        disk_callbacks: set[Callable[[Disk], None]],
        share_callbacks: set[Callable[[Share], None]],
    ) -> None:
        """Fire callbacks for newly discovered disks/shares after data is committed."""
        for disk_name in new_disks:
            self._do_callback(disk_callbacks, data["disks"][disk_name])
        for share_name in new_shares:
            self._do_callback(share_callbacks, data["shares"][share_name])

    @ha_callback
    def subscribe_disks(self, callback: Callable[[Disk], None]) -> None:
        self.disk_callbacks.add(callback)
        for disk_name in self.known_disks:
            callback(self.data["disks"][disk_name])

    @ha_callback
    def subscribe_shares(self, callback: Callable[[Share], None]) -> None:
        self.share_callbacks.add(callback)
        for share_name in self.known_shares:
            callback(self.data["shares"][share_name])

    def _do_callback(
        self, callbacks: set[Callable[..., None]], *args: tuple[Any], **kwargs: dict[Any]
    ) -> None:
        for cb in callbacks:
            try:
                cb(*args, **kwargs)
            except Exception:
                _LOGGER.exception("Error in callback")

    # --- WebSocket subscription support ---

    async def _try_connect_ws(self) -> None:
        """Attempt to establish a WebSocket connection and start subscriptions."""
        if self._ws_client is None:
            return
        try:
            await self._ws_client.connect()
            self._ws_connected = True
            self.update_interval = POLL_INTERVAL_WSS_FALLBACK
            _LOGGER.info(
                "WSS connected, polling interval set to %s", POLL_INTERVAL_WSS_FALLBACK
            )
            self._start_subscriptions()
        except Exception:
            _LOGGER.warning(
                "WSS connection failed, using polling at %s", POLL_INTERVAL_DEFAULT
            )
            self._ws_connected = False

    def _start_subscriptions(self) -> None:
        """Start background subscription listener tasks."""
        subscriptions = [
            (SUB_ARRAY, "arraySubscription", self._handle_array_update),
            (SUB_CPU, "systemMetricsCpu", self._handle_cpu_update),
            (SUB_CPU_TELEMETRY, "systemMetricsCpuTelemetry", self._handle_cpu_telemetry_update),
            (SUB_MEMORY, "systemMetricsMemory", self._handle_memory_update),
        ]
        for query, field, handler in subscriptions:
            task = self.hass.async_create_task(
                self._listen_subscription(query, field, handler)
            )
            self._ws_tasks.append(task)

    async def _listen_subscription(
        self,
        query: str,
        field: str,
        handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """Listen to a single subscription and call handler for each message."""
        if self._ws_client is None:
            return
        try:
            async for data in self._ws_client.subscribe(query):
                if field in data:
                    handler(data[field])
                    self.async_set_updated_data(self.data)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.debug("Subscription listener for %s ended", field)
        finally:
            if self._ws_connected:
                self._ws_connected = False
                self.update_interval = POLL_INTERVAL_DEFAULT
                _LOGGER.debug(
                    "WSS subscription lost, reverting to polling at %s",
                    POLL_INTERVAL_DEFAULT,
                )

    def _handle_array_update(self, data: dict[str, Any]) -> None:
        """Handle array subscription update by refreshing via poll."""
        # Array updates are complex (disks, capacity, state) - trigger a full refresh
        self.hass.async_create_task(self.async_request_refresh())

    def _handle_cpu_update(self, data: dict[str, Any]) -> None:
        """Handle CPU utilization subscription update."""
        if self.data and self.data["data"].metrics.cpu:
            self.data["data"].metrics.cpu.percent_total = data.get(
                "percentTotal", self.data["data"].metrics.cpu.percent_total
            )

    def _handle_cpu_telemetry_update(self, data: dict[str, Any]) -> None:
        """Handle CPU telemetry subscription update."""
        if self.data and self.data["data"].info.cpu:
            if "temp" in data:
                self.data["data"].info.cpu.packages.temp = data["temp"]
            if "totalPower" in data:
                self.data["data"].info.cpu.packages.total_power = data["totalPower"]

    def _handle_memory_update(self, data: dict[str, Any]) -> None:
        """Handle memory subscription update."""
        if self.data:
            mem = self.data["data"].metrics.memory
            if "available" in data:
                mem.free = data["available"]
            if "active" in data:
                mem.used = data["active"]
            if "total" in data:
                mem.total = data["total"]
            if "percentTotal" in data:
                mem.percent_total = data["percentTotal"]

    async def async_shutdown(self) -> None:
        """Clean up WebSocket connection on unload."""
        for task in self._ws_tasks:
            task.cancel()
        self._ws_tasks.clear()
        if self._ws_client:
            await self._ws_client.disconnect()
        await super().async_shutdown()
