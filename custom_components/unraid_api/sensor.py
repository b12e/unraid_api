"""The Unraid integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DRIVES, CONF_SHARES, CONF_TEMPERATURE
from .coordinator import UnraidDataUpdateCoordinator
from .models import ArrayDiskType, Disk, Share, TemperatureSensor

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from . import UnraidConfigEntry

_LOGGER = logging.getLogger(__name__)


class UnraidSensorEntityDescription(SensorEntityDescription, frozen_or_thawed=True):
    """Description for Unraid Sensor Entity."""

    value_fn: Callable[[UnraidDataUpdateCoordinator], StateType]
    extra_values_fn: Callable[[UnraidDataUpdateCoordinator], dict[str, Any]] | None = None


class UnraidDiskSensorEntityDescription(SensorEntityDescription, frozen_or_thawed=True):
    """Description for Unraid Disk Sensor Entity."""

    value_fn: Callable[[Disk], StateType]
    extra_values_fn: Callable[[Disk], dict[str, Any]] | None = None


class UnraidShareSensorEntityDescription(SensorEntityDescription, frozen_or_thawed=True):
    """Description for Unraid Share Sensor Entity."""

    value_fn: Callable[[Share], StateType]
    extra_values_fn: Callable[[Share], dict[str, Any]] | None = None


class UnraidTempSensorEntityDescription(SensorEntityDescription, frozen_or_thawed=True):
    """Description for Unraid Temperature Sensor Entity."""

    value_fn: Callable[[TemperatureSensor], StateType]
    extra_values_fn: Callable[[TemperatureSensor], dict[str, Any]] | None = None


def calc_array_usage_percentage(coordinator: UnraidDataUpdateCoordinator) -> StateType:
    """Calculate the array usage percentage."""
    used = coordinator.data["data"].array.capacity.kilobytes.used
    total = coordinator.data["data"].array.capacity.kilobytes.total
    if total == 0:
        return 0
    return round((used / total) * 100, 2)


def calc_disk_usage_percentage(disk: Disk) -> StateType:
    """Calculate the disk usage percentage."""
    if disk.fs_used is None or disk.fs_size is None or disk.fs_size == 0:
        return 0
    return round((disk.fs_used / disk.fs_size) * 100, 2)


SENSOR_DESCRIPTIONS: tuple[UnraidSensorEntityDescription, ...] = (
    UnraidSensorEntityDescription(
        key="array_state",
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda coordinator: coordinator.data["data"].array.state.value.lower(),
        options=[
            "started",
            "stopped",
            "new_array",
            "recon_disk",
            "disable_disk",
            "swap_dsbl",
            "invalid_expansion",
            "parity_not_biggest",
            "too_many_missing_disks",
            "new_disk_too_small",
            "no_data_disks",
        ],
    ),
    UnraidSensorEntityDescription(
        key="array_usage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=calc_array_usage_percentage,
        extra_values_fn=lambda coordinator: {
            "used": coordinator.data["data"].array.capacity.kilobytes.used,
            "free": coordinator.data["data"].array.capacity.kilobytes.free,
            "total": coordinator.data["data"].array.capacity.kilobytes.total,
        },
    ),
    UnraidSensorEntityDescription(
        key="array_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data["data"].array.capacity.kilobytes.free,
    ),
    UnraidSensorEntityDescription(
        key="array_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data["data"].array.capacity.kilobytes.used,
    ),
    UnraidSensorEntityDescription(
        key="ram_used",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data["data"].metrics.memory.used,
    ),
    UnraidSensorEntityDescription(
        key="ram_total",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data["data"].metrics.memory.total,
        entity_registry_enabled_default=False,

    ),
    UnraidSensorEntityDescription(
        key="ram_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data["data"].metrics.memory.free,
    ),
    UnraidSensorEntityDescription(
        key="ram_used_percentage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: coordinator.data["data"].metrics.memory.percent_total,
    ),
    UnraidSensorEntityDescription(
        key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: (
            coordinator.data["data"].metrics.cpu.percent_total
            if coordinator.data["data"].metrics.cpu
            else None
        ),
    ),
    UnraidSensorEntityDescription(
        key="cpu_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: (
            coordinator.data["data"].info.cpu.packages.temp[0]
            if coordinator.data["data"].info.cpu
            and coordinator.data["data"].info.cpu.packages.temp
            else None
        ),
        extra_values_fn=lambda coordinator: (
            {f"package_{i}": t for i, t in enumerate(coordinator.data["data"].info.cpu.packages.temp)}
            if coordinator.data["data"].info.cpu
            and coordinator.data["data"].info.cpu.packages.temp
            else None
        ),
    ),
    UnraidSensorEntityDescription(
        key="cpu_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda coordinator: (
            coordinator.data["data"].info.cpu.packages.total_power
            if coordinator.data["data"].info.cpu
            else None
        ),
    ),
)

DISK_SENSOR_DESCRIPTIONS: tuple[UnraidDiskSensorEntityDescription, ...] = (
    UnraidDiskSensorEntityDescription(
        key="disk_status",
        device_class=SensorDeviceClass.ENUM,
        value_fn=lambda disk: disk.status.value.lower(),
        options=[
            "disk_np",
            "disk_ok",
            "disk_np_missing",
            "disk_invalid",
            "disk_wrong",
            "disk_dsbl",
            "disk_np_dsbl",
            "disk_dsbl_new",
            "disk_new",
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UnraidDiskSensorEntityDescription(
        key="disk_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: disk.temp,
    ),
)

DISK_SENSOR_SPACE_DESCRIPTIONS: tuple[UnraidDiskSensorEntityDescription, ...] = (
    UnraidDiskSensorEntityDescription(
        key="disk_usage",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=calc_disk_usage_percentage,
    ),
    UnraidDiskSensorEntityDescription(
        key="disk_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: disk.fs_free,
    ),
    UnraidDiskSensorEntityDescription(
        key="disk_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda disk: disk.fs_used,
    ),
)

SHARE_SENSOR_DESCRIPTIONS: tuple[UnraidShareSensorEntityDescription, ...] = (
    UnraidShareSensorEntityDescription(
        key="share_free",
        name="free space",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.KILOBYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda share: share.free,
        extra_values_fn=lambda share: {
            "used": share.used,
            "total": share.size,
            "allocator": share.allocator,
            "floor": share.floor,
        },
    ),
)

TEMP_SENSOR_DESCRIPTIONS: tuple[UnraidTempSensorEntityDescription, ...] = (
    UnraidTempSensorEntityDescription(
        key="temp_sensor",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda sensor: sensor.current.value,
        extra_values_fn=lambda sensor: {
            "type": sensor.type,
            "warning": sensor.warning,
            "critical": sensor.critical,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    config_entry: UnraidConfigEntry,
    async_add_entites: AddEntitiesCallback,
) -> None:
    """Set up this integration using config entry."""
    entities = [UnraidSensor(description, config_entry) for description in SENSOR_DESCRIPTIONS]
    async_add_entites(entities)

    @callback
    def add_disk_callback(disk: Disk) -> None:
        _LOGGER.debug("Adding new Disk: %s", disk.name)
        entities: list[UnraidDiskSensor] = [
            UnraidDiskSensor(description, config_entry, disk.name)
            for description in DISK_SENSOR_DESCRIPTIONS
        ]
        if disk.type != ArrayDiskType.Parity:
            entities.extend(
                UnraidDiskSensor(description, config_entry, disk.name)
                for description in DISK_SENSOR_SPACE_DESCRIPTIONS
            )
        async_add_entites(entities)

    @callback
    def add_share_callback(share: Share) -> None:
        _LOGGER.debug("Adding new Share: %s", share.name)
        entities = [
            UnraidShareSensor(description, config_entry, share.name)
            for description in SHARE_SENSOR_DESCRIPTIONS
        ]
        async_add_entites(entities)

    @callback
    def add_temp_sensor_callback(sensor: TemperatureSensor) -> None:
        _LOGGER.debug("Adding new Temperature Sensor: %s", sensor.name)
        entities = [
            UnraidTempSensor(description, config_entry, sensor.name)
            for description in TEMP_SENSOR_DESCRIPTIONS
        ]
        async_add_entites(entities)

    if config_entry.options[CONF_DRIVES]:
        config_entry.runtime_data.coordinator.subscribe_disks(add_disk_callback)
    if config_entry.options[CONF_SHARES]:
        config_entry.runtime_data.coordinator.subscribe_shares(add_share_callback)
    if config_entry.options.get(CONF_TEMPERATURE, True):
        config_entry.runtime_data.coordinator.subscribe_temp_sensors(add_temp_sensor_callback)


class UnraidSensor(CoordinatorEntity[UnraidDataUpdateCoordinator], SensorEntity):
    """Sensor for Unraid Server."""

    entity_description: UnraidSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        description: UnraidSensorEntityDescription,
        config_entry: UnraidConfigEntry,
    ) -> None:
        super().__init__(config_entry.runtime_data.coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.entry_id}-{description.key}"
        self._attr_translation_key = description.key
        self._attr_device_info = config_entry.runtime_data.device_info
        # Explicitly set state_class for statistics
        if description.state_class:
            self._attr_state_class = description.state_class
        if description.device_class:
            self._attr_device_class = description.device_class
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> StateType:
        try:
            value = self.entity_description.value_fn(self.coordinator)
            # Return None for invalid numeric values to prevent statistics corruption
            if value is not None and isinstance(value, (int, float)) and (
                value != value or  # NaN check
                value == float('inf') or
                value == float('-inf')
            ):
                _LOGGER.warning("Invalid numeric value for %s: %s", self.entity_id, value)
                return None
            if value is not None and self.state_class == SensorStateClass.MEASUREMENT:
                _LOGGER.debug("%s value: %s (state_class: %s, available: %s)",
                             self.entity_id, value, self.state_class, self.available)
            return value
        except (KeyError, AttributeError, TypeError, ZeroDivisionError) as err:
            _LOGGER.warning("Error getting value for %s: %s", self.entity_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.extra_values_fn:
            try:
                return self.entity_description.extra_values_fn(self.coordinator)
            except (KeyError, AttributeError, TypeError) as err:
                _LOGGER.debug("Error getting attributes for %s: %s", self.entity_id, err)
                return None
        return None


class UnraidDiskSensor(CoordinatorEntity[UnraidDataUpdateCoordinator], SensorEntity):
    """Sensor for Unraid Disks."""

    entity_description: UnraidDiskSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        description: UnraidDiskSensorEntityDescription,
        config_entry: UnraidConfigEntry,
        disk_name: str,
    ) -> None:
        super().__init__(config_entry.runtime_data.coordinator)
        self.disk_name = disk_name
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.entry_id}-{description.key}-{self.disk_name}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"disk_name": self.disk_name}
        self._attr_device_info = config_entry.runtime_data.device_info
        if description.state_class:
            self._attr_state_class = description.state_class
        if description.device_class:
            self._attr_device_class = description.device_class
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.disk_name in self.coordinator.data.get("disks", {})

    @property
    def native_value(self) -> StateType:
        try:
            if self.disk_name not in self.coordinator.data.get("disks", {}):
                return None
            value = self.entity_description.value_fn(self.coordinator.data["disks"][self.disk_name])
            if value is not None and isinstance(value, (int, float)) and (
                value != value or  # NaN check
                value == float('inf') or
                value == float('-inf')
            ):
                return None
            return value
        except (KeyError, AttributeError, TypeError, ZeroDivisionError) as err:
            _LOGGER.debug("Error getting value for %s: %s", self.entity_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.extra_values_fn:
            try:
                if self.disk_name not in self.coordinator.data.get("disks", {}):
                    return None
                return self.entity_description.extra_values_fn(
                    self.coordinator.data["disks"][self.disk_name]
                )
            except (KeyError, AttributeError, TypeError) as err:
                _LOGGER.debug("Error getting attributes for %s: %s", self.entity_id, err)
                return None
        return None


class UnraidShareSensor(CoordinatorEntity[UnraidDataUpdateCoordinator], SensorEntity):
    """Sensor for Unraid Shares."""

    entity_description: UnraidShareSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        description: UnraidShareSensorEntityDescription,
        config_entry: UnraidConfigEntry,
        share_name: str,
    ) -> None:
        super().__init__(config_entry.runtime_data.coordinator)
        self.share_name = share_name
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.entry_id}-{description.key}-{self.share_name}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"share_name": self.share_name}
        self._attr_device_info = config_entry.runtime_data.device_info
        # Explicitly set state_class for statistics
        if description.state_class:
            self._attr_state_class = description.state_class
        if description.device_class:
            self._attr_device_class = description.device_class
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.share_name in self.coordinator.data.get("shares", {})

    @property
    def native_value(self) -> StateType:
        try:
            if self.share_name not in self.coordinator.data.get("shares", {}):
                return None
            value = self.entity_description.value_fn(self.coordinator.data["shares"][self.share_name])
            # Return None for invalid numeric values to prevent statistics corruption
            if value is not None and isinstance(value, (int, float)) and (
                value != value or  # NaN check
                value == float('inf') or
                value == float('-inf')
            ):
                return None
            return value
        except (KeyError, AttributeError, TypeError, ZeroDivisionError) as err:
            _LOGGER.debug("Error getting value for %s: %s", self.entity_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.extra_values_fn:
            try:
                if self.share_name not in self.coordinator.data.get("shares", {}):
                    return None
                return self.entity_description.extra_values_fn(
                    self.coordinator.data["shares"][self.share_name]
                )
            except (KeyError, AttributeError, TypeError) as err:
                _LOGGER.debug("Error getting attributes for %s: %s", self.entity_id, err)
                return None
        return None


class UnraidTempSensor(CoordinatorEntity[UnraidDataUpdateCoordinator], SensorEntity):
    """Sensor for Unraid Temperature readings."""

    entity_description: UnraidTempSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        description: UnraidTempSensorEntityDescription,
        config_entry: UnraidConfigEntry,
        sensor_name: str,
    ) -> None:
        super().__init__(config_entry.runtime_data.coordinator)
        self.sensor_name = sensor_name
        self.entity_description = description
        self._attr_unique_id = f"{config_entry.entry_id}-{description.key}-{self.sensor_name}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"sensor_name": self.sensor_name}
        self._attr_device_info = config_entry.runtime_data.device_info
        if description.state_class:
            self._attr_state_class = description.state_class
        if description.device_class:
            self._attr_device_class = description.device_class
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement

    def _get_sensor_data(self) -> TemperatureSensor | None:
        """Find this sensor in the temperature metrics data."""
        temp_metrics = self.coordinator.data["data"].metrics.temperature
        if temp_metrics is None:
            return None
        for sensor in temp_metrics.sensors:
            if sensor.name == self.sensor_name:
                return sensor
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._get_sensor_data() is not None

    @property
    def native_value(self) -> StateType:
        try:
            sensor = self._get_sensor_data()
            if sensor is None:
                return None
            value = self.entity_description.value_fn(sensor)
            if value is not None and isinstance(value, (int, float)) and (
                value != value or value == float('inf') or value == float('-inf')
            ):
                return None
            return value
        except (KeyError, AttributeError, TypeError, ZeroDivisionError) as err:
            _LOGGER.debug("Error getting value for %s: %s", self.entity_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.extra_values_fn:
            try:
                sensor = self._get_sensor_data()
                if sensor is None:
                    return None
                return self.entity_description.extra_values_fn(sensor)
            except (KeyError, AttributeError, TypeError) as err:
                _LOGGER.debug("Error getting attributes for %s: %s", self.entity_id, err)
                return None
        return None
