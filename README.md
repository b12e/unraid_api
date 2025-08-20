# Fork Notes
This fork is a temporary solution while the original maintainer updates the plugin. 

It adds support for RAM statistics - available, in use, total and percentage used. It also enables by default all sensors.

Please refrain from using it in production and stick to the original.


## Prerequisites

- Install the [Unraid Connect Plugin](https://docs.unraid.net/connect/) on your Unraid server
- Enable the [developer mode](https://docs.unraid.net/API/cli/#developer-mode)
- Create an [API Key](https://docs.unraid.net/API/how-to-use-the-api/#creating-an-api-key) with role: "admin" and permissions:

  - array: read
  - info: read
  - shares: read

## Setup

1. Click the button below or use "Add Integration" in Home Assistant and select "Unraid".

    [![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=unraid_api)

2. Enter the URL of the Unraid WebUI and your API Key
3. Select if you want to monitor disk and shares

### Configuration parameters

- Unraid WebUI: URL of the Unraid WebUI (including "http(s)://")
- API Key: API Key for the Unraid API
- Monitor Shares: Create Entities for each Network Share
- Monitor Disks: Create Entities for each Disk
