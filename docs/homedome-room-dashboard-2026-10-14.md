# HomeDome room dashboard — 14 October 2026

Home now opens a room-based dashboard in both the customer app and the platform IoT HomeDome panel. The layout follows the supplied room/tile/control-pop-up reference.

## Customer experience

- Devices are grouped under room headings, with room icons, temperature/humidity summaries when available, and two-column device tiles at phone width.
- The room/device filters remain above the room sections.
- Selecting a device opens an accessible native modal: brightness controls for dimmable lights, on/off for lights/switches/fans, open/close/position for compatible blinds, scene activation, media controls/navigation and permission-gated camera previews. Sensors open a detail view.
- Mobile pop-ups appear as a bottom sheet; desktop pop-ups are centred. Escape, close and backdrop actions dismiss them; native dialog focus handling is used.
- Off and unavailable states take precedence over retained brightness/position values.
- Create room saves an actual home-scoped layout before a gateway is connected. Owners can assign synced devices from the device pop-up; these assignments survive gateway sync.
- Empty rooms remain visible. Gateway registry areas, including empty ones, are imported when the connected gateway allows registry access.
- Local rooms and assignments are managed in HomeDome; creating or moving a room here does not write a Home Assistant area configuration back to the gateway.

## Showcase

When no real devices are available, Home starts on an explicitly labelled interactive showcase: Living room, Kitchen, Bedroom and Energy. Example values and preview controls are local frontend state, never production device readings or commands.

The My home / View showcase button switches between the actual layout and preview. Creating a room saves a real room and switches to My home. Showcase lights, blinds and media buttons update the preview only; zero brightness means off and zero blind position means closed.

The preview does not require the gateway token. Real device controls still require a connected gateway and owner/approved control access.

## Platform parity

The platform now runs the same room dashboard, Energy, Integrations, Media, Map and To-do components as the customer app. Its HomeDome surface, tiles and pop-ups use the platform's dark colours; the customer app keeps its light presentation. Dark-theme source values and brand images remain readable.

Home Assistant navigation links have been removed from the HomeDome UI, including the prominent dashboard link and gateway setup links. The Connection form remains inside HomeDome for gateway credentials. Other IoT module content remains available.

Technician component source was kept consistent, but its separate running frontend image was not rebuilt in this task.

## Privacy and persistence

Two new tables hold household rooms and assignments. Room creation/assignment requires the actual home owner; room reads require ownership or approved diagnostics. A Platform Owner role does not bypass household privacy. Cross-home room assignments are rejected and duplicate room names are checked case-insensitively under the home lock.

Compatible blind control is bounded to 0–100 and targets the selected household entity. After a real command, the service reads that same entity to update its state. A state-read failure does not retry a command already sent. Locks/alarm actions remain unavailable through these pilot controls.

## Validation and deployment

- 77 IoT tests passed: room creation without a gateway, duplicates, ownership, empty-area import, cross-home assignment, persistence through sync, blind position validation and sanitised state confirmation, alongside the existing energy/privacy suite.
- 17 customer rendering/state/proxy tests passed: showcase landing, grouped/empty real rooms, owner affordances, accurate device states, preview transitions, energy rendering and customer support isolation.
- 13 real PostgreSQL checks passed, including the new room/assignment tables; all probe rows were rolled back.
- Customer TypeScript and production builds passed. The platform production build passed using its existing configuration (which skips its broad TypeScript check); shared HomeDome code was validated by the customer type check.
- Both HomeDome pages and customer Support returned HTTP 200.
- Real owner login: rooms returned 200 before gateway connection. The separate test account was rejected with 403 for room data. Media/Map/To-do correctly require connection and remained owner-only.
- IoT/initial platform deployment rollback stamp: 20261014070609. Final platform frontend rollback stamp: 20261014075039. Customer app restarted as PID 17492.
- The platform compiled in a private build container with output/cache on D:, using the existing runtime dependencies. Only the web and IoT services were updated; PostgreSQL, Home Assistant and the orchestrator were not restarted.
- Browser click/screenshot verification was unavailable: the browser runtime failed during initial attachment with a missing kernel-asset path. Build, render/state and API checks passed; this is not a completed interactive browser walkthrough or physical-device test.
- Project RAG recall was performed and returned zero relevant memory/knowledge entries. Repository/API code was used for implementation.
- Source changes remain uncommitted and unpushed.

Refresh the customer Home page and the platform IoT panel to load the latest bundles. Real gateway pairing is still separate; it is not needed to try the room showcase.

