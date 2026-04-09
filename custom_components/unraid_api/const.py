"""Constants."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "unraid_api"
PLATFORMS = [Platform.SENSOR]

CONF_SHARES: Final[str] = "shares"
CONF_DRIVES: Final[str] = "drives"
CONF_TEMPERATURE: Final[str] = "temperature"

QUERY = """query Hass {
  server {
    localurl
    name
  }
  array {
    state
    disks {
      name
      status
      temp
      fsSize
      fsFree
      fsUsed
      type
      id
    }
    parities {
      name
      status
      temp
      fsSize
      fsFree
      fsUsed
      type
      id
    }
    caches {
      name
      status
      temp
      fsSize
      fsFree
      fsUsed
      type
      id
    }
    capacity {
      kilobytes {
        free
        used
        total
      }
    }
  }
  shares {
    name
    free
    used
    size
    allocator
    floor
    luksStatus
  }
  metrics {
    memory {
      total
      available
      active
      percentTotal
    }
    cpu {
      percentTotal
    }
    temperature {
      sensors {
        name
        type
        current {
          value
        }
        warning
        critical
      }
      summary {
        average
      }
    }
  }
  info {
    cpu {
      packages {
        temp
        totalPower
      }
    }
    versions {
      core {
        unraid
      }
    }
  }
}
"""

DISK_FRAGMENT = """fragment DiskFields on ArrayDisk {
  name
  status
  temp
  fsSize
  fsFree
  fsUsed
  type
  id
}"""

SUB_ARRAY = """subscription ArrayUpdates {
  arraySubscription {
    state
    disks { ...DiskFields }
    parities { ...DiskFields }
    caches { ...DiskFields }
    capacity {
      kilobytes {
        free
        used
        total
      }
    }
  }
}
""" + DISK_FRAGMENT

SUB_CPU = """subscription CpuUpdates {
  systemMetricsCpu {
    percentTotal
  }
}
"""

SUB_CPU_TELEMETRY = """subscription CpuTelemetryUpdates {
  systemMetricsCpuTelemetry {
    temp
    totalPower
  }
}
"""

SUB_MEMORY = """subscription MemoryUpdates {
  systemMetricsMemory {
    total
    available
    active
    percentTotal
  }
}
"""

SUB_TEMPERATURE = """subscription TemperatureUpdates {
  systemMetricsTemperature {
    sensors {
      name
      type
      current {
        value
      }
      warning
      critical
    }
    summary {
      average
    }
  }
}
"""
