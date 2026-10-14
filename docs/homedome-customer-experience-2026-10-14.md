# HomeDome customer experience — 14 October 2026

The customer app at http://localhost:3001/home now includes the revised energy view, integration brand gallery, Media, Map and To-do. The IoT backend is deployed locally. The staff/technician frontend sources contain the same components, but their running frontend images have not been rebuilt.

## Energy matches the supplied reference

- Six circular nodes: Grid, Solar, Home, Battery, Gas and Water, with source icons, matching colours and curved connections.
- Grid import/export and battery charge/discharge are shown separately within their nodes.
- Moving dots appear only for fresh, available meter measurements. Signed grid power determines import/export; battery direction uses its distinct cumulative counters rather than assuming a battery power sign convention.
- Offline gateways stop all animation. Measurements older than three minutes do not animate. Reports refresh every 30 seconds while Energy is open.
- Reduced-motion preferences hide moving dots.
- Summary, Electricity, Gas, Water and Now views; totals table, recorded power chart, consumption summaries and day navigation.
- Missing data remains unavailable. Home consumption is calculated only when all required energy-balance counters exist. Grid cost uses the configured rand tariff and remains an estimate, not an invoice.
- Lower consumption cards show measured totals; hourly electricity/gas/water charts are not implemented. The later [room dashboard update](homedome-room-dashboard-2026-10-14.md) adds room tiles and light/control pop-ups, superseding the earlier device-list presentation.

## Integration brands

The gallery displays brand images, search, category and setup-status filters. All 21 Home Assistant brand-image endpoints returned HTTP 200, including Music Assistant and Radio Browser. An image-loading failure falls back to the brand name. A loaded integration is distinguished from a paired device or authorised provider account.

## Media, Map and To-do

Media lists the household's Home Assistant players, with play/pause/stop, previous/next and volume controls. The library browser exposes media sources configured in Home Assistant, including Radio Browser when enabled. Playback targets a selected home player; browser/phone audio playback is not implemented. Only library items verified against the owned gateway may be played; arbitrary URL playback is rejected.

Map displays real Home Assistant zones, people and device trackers with valid coordinates. Selecting Show map loads OpenStreetMap for that location; the UI explains that the location will then be shared with the map provider. No map request is sent before that choice.

To-do reads configured Home Assistant task lists and supports add, complete/reopen, rename and remove, verifying item IDs against the selected list.

These three features are restricted to the home owner. They do not expose locations or tasks through the staff diagnostics feed, support grants or event bus. Gateway credentials stay encrypted server-side.

## What is still required on this pilot

Real sign-in checks confirm that the home is owned by burnibraai@gmail.com. The separate test account can access its customer account but cannot access this private home.

The Home Assistant access token is still unconfigured. Media, Map and To-do currently return the clear connection-required response (HTTP 409) for the owner. Enter the token privately under HomeDome → Connection, then configure compatible players/media providers, location sources and task lists in Home Assistant. Configure energy meters under Energy → Choose meters. No actual device playback or real energy flow has been verified yet.

The gateway remains a local pilot. Physical devices and media players need suitable network reachability; none have been represented as paired during these checks.

## Validation and deployment

- 72 IoT backend tests passed, including fresh/stale/offline flow behaviour, direction, customer isolation, fixed player targeting, arbitrary-media rejection, task IDs and invalid locations.
- 11 customer render/proxy tests passed, including six-node layout, missing data, balanced consumption, invalid chart values, conditional animation and reduced motion.
- Customer TypeScript and production build passed.
- Customer /home and /support returned HTTP 200; unauthenticated media access returned 401.
- Real Supabase sessions: owner media/map/to-do routes returned 409 (connection required), separate test account returned 404. The live brand catalogue returned 21 entries. Support remained limited to the customer-facing agent.
- Customer app restarted as PID 3228. Latest IoT rollback stamp: 20261014060608.
- The backend overlay copies about 3 MiB of existing source without dependency installation or image pulls. Its deployment guard now retains a 512 MiB reserve plus eight source copies; the full web rebuild retains the 3 GiB requirement. Windows C: had about 1.06 GiB free at completion.
- Browser click testing was unavailable because an earlier automatic approval review blocked browser interaction. Validation covers source, rendering, build and HTTP/API behaviour, not a completed interactive browser walkthrough.
- Project RAG recall was performed; it returned zero matching memory/knowledge entries. Implementation was grounded in the repository and the official Home Assistant API.
- These source changes are not committed or pushed.

API references: [WebSocket service actions](https://developers.home-assistant.io/docs/api/websocket/), [To-do integration](https://www.home-assistant.io/integrations/todo/), [Radio Browser](https://www.home-assistant.io/integrations/radio_browser/), and [Home Assistant media-source commands](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/media_source/http.py).

