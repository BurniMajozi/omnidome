"""Setup catalogue: installed HA integrations are detected, not installed by OmniDome."""
INTEGRATIONS = [
    ("alexa", "Amazon Alexa", "Voice", "Link an Alexa account; cloud subscription or manual skill setup may be required."),
    ("esphome", "ESPHome", "Devices", "A configured ESPHome device reachable from Home Assistant."),
    ("google_assistant", "Google Assistant", "Voice", "Link a Google account; cloud subscription or manual project setup may be required."),
    ("cast", "Google Cast", "Media", "A compatible Cast device on a reachable network."),
    ("homekit", "HomeKit Bridge", "Bridge", "Pair Home Assistant's bridge with Apple Home."),
    ("tradfri", "IKEA TRÅDFRI", "Lighting", "A supported IKEA gateway and devices."),
    ("knx", "KNX", "Building", "A reachable KNX/IP interface or router."),
    ("lutron_caseta", "Lutron Caséta", "Lighting", "A supported Lutron Smart Bridge."),
    ("matter", "Matter", "Devices", "Matter Server and compatible devices; Thread devices also need a border router."),
    ("mqtt", "MQTT", "Sensors", "An MQTT broker, credentials and configured devices."),
    ("music_assistant", "Music Assistant", "Media", "A reachable Music Assistant server with your music providers and players configured."),
    ("radio_browser", "Radio Browser", "Media", "Enable Radio Browser in Home Assistant and select a compatible media player."),
    ("hue", "Philips Hue", "Lighting", "A Hue bridge paired with Home Assistant."),
    ("plex", "Plex Media Server", "Media", "An authorized Plex account and reachable server."),
    ("shelly", "Shelly", "Devices", "A supported Shelly device reachable on the home network."),
    ("smartthings", "SmartThings", "Devices", "Authorize the customer's SmartThings account."),
    ("sonos", "Sonos", "Media", "Sonos players with appropriate local network connectivity."),
    ("zwave_js", "Z-Wave", "Sensors", "Z-Wave JS server and a compatible Z-Wave adapter."),
    ("zha", "Zigbee Home Automation", "Sensors", "A compatible Zigbee coordinator and paired devices."),
    ("imou", "Imou", "Cameras", "Open Platform App ID, App secret, matching region and authorized devices; cloud quotas apply."),
    ("onvif", "ONVIF", "Cameras", "A compatible camera, device credentials and local connectivity."),
]


GUIDED_SETUP = {"imou", "onvif"}  # keep in sync with routes/integration_setup.GUIDED


def catalogue(components):
    installed = {item.split(".")[0] for item in components or []}
    return [{"id": domain, "name": name, "category": category, "requirement": requirement,
        "status": "loaded" if domain in installed else "setup_required", "guided": domain in GUIDED_SETUP,
        "logo_url": f"https://brands.home-assistant.io/_/{domain}/icon.png",
        "docs_url": f"https://www.home-assistant.io/integrations/{domain}/"}
        for domain, name, category, requirement in INTEGRATIONS]
