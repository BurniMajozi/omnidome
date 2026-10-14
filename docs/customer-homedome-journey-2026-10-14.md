# One OmniDome platform, with customer and staff views

Customers should use **one customer app** for their account, billing, support and HomeDome. The staff workspace manages the ISP, customers and support permissions. These views share OmniDome's identity, tenant records and backend services.

| Local address | Purpose |
| --- | --- |
| `localhost:3000` | Staff and platform administration |
| `localhost:3001` | Customer app, including HomeDome and Support |
| `localhost:8123` | Home Assistant gateway setup and advanced home controls |

Home Assistant is the device engine behind HomeDome. Its native Overview screen is currently an advanced gateway interface, not a second ISP/customer platform. I exposed that setup interface separately and left the customer connection unfinished, which made the journey feel like separate products.

## What is now deployed

- The customer Support chat wrapper uses stable Zustand subscriptions. The previous selector created a new object on every read, which can trigger React's external-store render loop.
- Support uses a same-origin authenticated proxy through the platform rather than calling the orchestrator's internal port directly. It allows only the customer-facing agent and derives the customer association from the verified account, discarding browser-supplied customer and tenant IDs.
- A Support error boundary offers retry and return-to-home controls. Ticket-history failures show an explicit message; AI ticket statuses are normalised before rendering.
- The customer's HomeDome view explains its place inside the customer app, hides staff provisioning cards, and labels the native gateway link **Advanced home settings**.
- The local gateway is assigned to the prepared **HomeDome home** owned by `burnibraai@gmail.com`, using the existing customer association **ACC-0000-8E607CBD**. The test login remains a separate portal test account; it is not automatically granted ownership of the home.

## Finish the home connection

1. Refresh the customer app, sign in as `burnibraai@gmail.com`, and open **HomeDome**.
2. Choose **Connect your home**, which opens **Connection**.
3. In **Advanced home settings**, open your Home Assistant profile and create a long-lived access token.
4. Enter it in HomeDome's password-style token field and save. Do not send it in chat. Credential encryption has been verified ready, and the URL is already fixed to the prepared gateway.
5. HomeDome then synchronises supported devices, their assigned rooms, integrations and configured energy meters from that same gateway. Staff access remains subject to the customer's approval.

The token was not configured at the deployment checks, so customer device/energy data could not yet be read. No readings were fabricated to make the interface appear connected.

## What remains to complete the experience

The full native Home Assistant dashboard is **not embedded** in the customer app. HomeDome provides its own supported device, room, energy, integration and consent views. Media, Map and To-do use the household gateway. The latest [room dashboard update](homedome-room-dashboard-2026-10-14.md) adds grouped tiles, control pop-ups, owner-managed rooms and a labelled showcase in both customer and platform views. Empty gateway areas are imported during registry sync. Real media, location, task and device data require a connected gateway; the room showcase and room creation work before connection. See [the earlier customer update](homedome-customer-experience-2026-10-14.md) for energy and brand behaviour.

The next integration work is to finish that gateway connection, include empty areas from its registry, and decide which advanced native screens should be offered within the customer journey. Routine customer tasks should stay inside the customer app; customers should not be directed into staff administration. Production routing and branding should present role-specific customer and staff entry points without exposing development port numbers.

Some existing customer-portal APIs, including its legacy ticket-history request, still need wiring. The Support page now reports that failure instead of presenting an unexplained blank list. This release does not claim that the entire customer app is complete.

## Verification

- Customer production build and TypeScript checks passed; the customer server was restarted on port 3001.
- Six support-proxy tests passed, including tenant/customer context replacement, streaming response forwarding, blocked staff agents, unauthenticated access and unlinked accounts.
- Both registered pilot accounts authenticated through Supabase and received HTTP 200 from the real customer profile and support catalogue endpoints. Staff-agent invocation requests returned HTTP 403. No LLM invocation or outbound customer message was used for these checks; probe sessions were signed out locally.
- The registered Gmail account's authenticated home lookup confirmed ownership of the prepared gateway home. The test account did not acquire home ownership.
- `/support` returned HTTP 200 with the support interface rendered; unauthenticated support API access returned HTTP 401. Full browser interaction testing remains outstanding.
- Gateway credential encryption passed a round-trip check without storing a real token.

The customer-facing changes are deployed locally. Shared HomeDome source labels were updated for staff and technician builds, but their running frontend images were not rebuilt in this fix. Source changes are not yet committed or pushed.
