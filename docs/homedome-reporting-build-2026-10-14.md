# HomeDome reporting implementation

## Experience contract

Customers stay in HomeDome: Home → Energy → Reports. Reports explain consumption and comfort over time, with a labelled sample mode while sensors are unavailable. The primary commercial action is **Upgrade reporting**. Sample values must never be stored as household telemetry, presented as real savings or used for billing.

The interface uses the existing light customer theme and dark tenant theme. Controls wrap at phone width; the chart scales to its container. A native dialog provides the plan comparison, keyboard focus handling and Escape dismissal. Chart values are also available in a table and CSV; calendar gaps retain their positions and negative measurements render correctly.

Tenant administrators manage commercial upgrade requests separately from private household reports. They can mark requests contacted or closed. Admin status does not bypass household consent, and queue actions never activate an entitlement or take payment.

## Built

- A Reports tab in the shared customer, platform and technician HomeDome sources.
- Sample energy, water and room-temperature charts, clearly marked as illustrative September 2026 data. Samples live in the UI only.
- Real report endpoints using available household observations or imported Recorder statistics. Included history is bounded to 30 days and 20 sensor series.
- Seven-, fourteen- and thirty-day views, sensor selection, readable daily-value tables and CSV export labelled with the data source.
- An owner-only historical import using the existing encrypted Home Assistant connection and its authenticated WebSocket API. The importer selects supported synced sensors, accepts only bounded numeric statistics and reconciles repeated imports without duplicate rows.
- Missing values, long observation gaps and counter resets do not become zero usage or fabricated consumption. Observation averages are explicitly distinguished from Recorder time-weighted statistics.
- An upgrade comparison dialog and persistent owner-only request. The ISP receives commercial metadata in a tenant-scoped request queue, without access to sensor readings.

Advanced reporting pricing is not published, and no paid HomeDome reporting entitlement exists yet. The CTA records interest for an ISP quote; it clearly states that no charge is taken and no paid service is activated. Twelve-month history, forecasts, scheduled summaries and anomaly alerts are described as forthcoming, not working features. Paystack checkout and recurring paid provisioning remain the next commercial phase.

No sensors are needed to explore the sample charts or request an upgrade. Genuine imports, device accuracy and forecast validation remain deferred until hardware is available.

## Validation and deployment

Deployed locally on 14 October 2026 after the user asked to proceed. No migration/compaction operation was active; the existing guarded deployment's disk-reserve check passed. Claude's read-only disk scan was left running. IoT and web were updated; no WSL shutdown or unrelated service restart was performed.

Open **HomeDome → Reports** in the customer app or platform IoT workspace. Without sensors, the owner sees labelled sample charts automatically and can explore the periods, daily-value table and sample CSV. **Upgrade reporting** opens the included/advanced comparison and saves an upgrade request. Authorized tenant admins use **Manage reporting upgrades** to review requests, mark them contacted or close them. Actual household reports still require ownership or customer-approved diagnostics access.

The first deployment detected an existing integration route's `viewer` gate incompatibility and automatically rolled back to healthy services. The helper now accepts that authenticated read tier, and a startup regression test covers application route registration. The corrected deployment succeeded with rollback stamp **20261014131921**; the platform frontend image is `omnidome-homedome-web:reports-20261014130520`.

The customer proxy now rejects the tenant commercial queue and hides administrative capabilities even if a platform admin signs into the customer app. The same authorized admin can still use the queue through the tenant platform. Owner upgrade requests remain available through the customer proxy.

Validation: **89 backend tests**, **23 frontend/proxy checks**, and **16 real PostgreSQL checks** passed. PostgreSQL probe rows were rolled back. Both frontend webpack production builds passed, and the customer strict TypeScript check passed. The platform retains its existing broad TypeScript-skip setting; shared reporting components were checked through the customer build. The default customer Turbopack command was incompatible with the existing webpack configuration; the explicit webpack build succeeded.

Live verified Supabase checks: the assigned owner received reports **200**; the separate account linked to the same CRM customer received household reports **403**. Both customer-app sessions received tenant queue **403** with admin controls hidden. Their authorized tenant-platform sessions received queue **200**. Customer `/home` and platform `/dashboard/home-dome` both returned **200**.

Browser attachment still fails with a missing kernel-asset path, so no interactive browser walkthrough is claimed. Component rendering, chart geometry, server builds and API checks are used instead.

Build outputs are preserved on D:. The customer runtime remains beside its app so Node can resolve dependencies; only its cache and standalone output use junctions. Local web and technician `.next` outputs also use junctions. The project Python `site-packages` directory was moved intact to D: with a junction at its original path, and SQLAlchemy, asyncpg, pytest and HTTPX imports passed afterward. No unrelated service was restarted.

Reporting is deployed and API verification is complete. Refresh the customer app and platform to load the latest bundles. Physical sensor testing remains deferred, and no browser walkthrough is claimed. Pricing, paid activation and advanced forecasting/scheduling remain the separate commercial phase described above. Reporting changes have not been committed or pushed.
