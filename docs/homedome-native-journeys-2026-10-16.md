# HomeDome native journeys on the Home Assistant backend

**Principle:** Home Assistant runs inside OmniDome as an engine. Customers and ISP staff never open `localhost:8123`, never make a Home Assistant account and never paste its tokens. Each HA screen a person would otherwise use is rebuilt as a HomeDome journey that calls HA's REST/WebSocket API. Only the operator opens HA itself (break-glass).

The map below is HA's own list of supported "My" pages (<https://my.home-assistant.io/faq/>), i.e. the screens HA considers user journeys.

| HA page(s) | HomeDome journey | Status |
|---|---|---|
| (onboarding) | **Activate your home** (Connection tab): HA onboarding done by HomeDome; an already-onboarded gateway is linked once with its admin login | built 2026-10-16 |
| `integrations`, `config_flow_start`, `integration` | **Integrations → Set up in HomeDome**: HA config flow rendered natively (Imou, ONVIF) | built |
| `devices`, `entities` | Devices list per integration, camera snapshot, PTZ pad, switches/selects/sensors | Imou/ONVIF built; generic devices page next |
| `areas`, `labels` | Rooms (read from HA areas, editable in HomeDome) | rooms built; write-back to HA areas next |
| `energy`, `config_energy` | Energy dashboard + meter picker | built |
| `scenes`, `scripts`, `automations` | Routines (scenes exist; scripts/automations as guided recipes) | scenes only |
| `add_zigbee_device`, `add_zwave_device`, `add_matter_device`, `config_zha`, `config_matter`, `config_zwave_js` | Pairing journeys (need radios; Container install has no add-ons) | not started |
| `backup`, `backup_list` | "Back up my home" for the customer, restore for the operator | not started |
| `repairs`, `updates`, `system_health`, `logs`, `info` | Home health for support (consent-gated diagnostics) | not started |
| `people`, `users`, `zones` | Household members and the home zone | not started |
| `history`, `tools_states`, `tools_statistics` | Device history charts | readings stored; charts partial |
| `voice_assistants`, `tools_assist` | Voice and assistants | not started |
| `config_mqtt`, `config_thread`, `config_modbus`, `config_serial`, `hardware`, `network`, `config_dhcp` etc. | Operator-only: not offered to customers | out of scope |
| `lovelace_dashboards`, `profile*`, `analytics`, `cloud`, `tags`, `helpers`, `blueprints` | Not exposed: HomeDome replaces dashboards and profile | out of scope |

## How a journey is built
1. Find the HA flow: config-entry flow (`/api/config/config_entries/flow`), a registry command over the WebSocket (`config/area_registry/*`, `config/device_registry/*`, `config/entity_registry/*`), or a service call.
2. Add an owner-only, allow-listed IoT route that forwards it, whitelists the response and never stores or echoes secrets.
3. Add a native step-by-step UI in `integration-setup.tsx` style: prerequisites, form, result.
4. Emit a minimal event (`iot.*`) on the event bus and add the journey to the HomeDome guides in `services/iot/ha_reference.py`, so the memory agent and the orchestrator's daily review know it exists.

## Operator notes
- The iot container must be started with `deploy/commercial/shadow.yml` (gateway network + `HOME_DOME_LOCAL_GATEWAY_ENABLED`). A plain `docker compose up iot` silently loses both and Activate fails with "gateway not reachable".
- Port 8123 stays bound to `127.0.0.1` only for the operator.
