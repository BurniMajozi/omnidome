# HomeDome reporting: recommendation and provisioning design

Reviewed 14 October 2026. This is a proposal, not an installed reporting service or published price list.

## Recommendation

Yes, we can build this into HomeDome. Use the existing Python backend, Home Assistant's historical statistics and the existing customer interface. Start locally with one connected home; run the shared reporting worker and customer-facing service on the VPS when ready for production. Keep each home's Home Assistant gateway at the home.

Jupyter is optional for the platform team's experiments. Customers should get charts, comparisons, report downloads and scheduled summaries inside HomeDome. They should not need another portal or notebook environment.

Make advanced reporting an optional paid service **per home**, with basic history included. Keep household consent separate from payment and staff permissions. Reuse Paystack and the existing billing infrastructure; no Stripe or additional billing platform is needed for this design.

## What the links actually provide

The [Data Science Portal](https://data.home-assistant.io/) teaches exploration and analysis of Home Assistant data. It supplies a method and examples, rather than a complete reporting product with customer accounts, subscriptions and provisioning. The [data guide](https://data.home-assistant.io/docs/data/) explains states, events, services and context; context is useful when investigating what caused an automation or state change.

The [quick start](https://data.home-assistant.io/docs/quick-start/) uses a JupyterLab add-on and an editable notebook. Our gateway runs Home Assistant Container, so that Supervisor add-on installation journey does not apply. The [Core guide](https://data.home-assistant.io/docs/quick-start-core/) describes a standalone Python environment, but still assumes Ubuntu 18.10. Treat its commands as examples to adapt, not a deployment recipe to copy unchanged.

The [sample notebook repository](https://github.com/home-assistant/home-assistant-notebooks) is reusable subject to its [Apache-2.0 licence and attribution requirements](https://github.com/home-assistant/home-assistant-notebooks/blob/master/LICENSE.md). [HASS-data-detective](https://github.com/robmarkcole/HASS-data-detective) is MIT-licensed; its current README specifies Python 3.12 and explains database-schema-dependent versions. We can study or adapt selected analyses, but must test compatibility with our actual Recorder schema and pin dependencies before using them.

## What we already have, and the missing piece

Source inspection shows HomeDome already has encrypted gateway credentials, household ownership, temporary support consent, device sync, stored sensor readings and energy calculations. The current worker polls every 60 seconds; sensor and binary-sensor observations are stored on change or approximately every five minutes, with 30-day retention. That can support basic trends, but can miss short transitions and does not reproduce Home Assistant's full event history.

The customer Analytics page already calls dashboard/template APIs. It is a general dashboard shell, not yet a verified HomeDome historical reporting pipeline. We can reuse its presentation patterns while adding a home-scoped data source. Existing analytics scheduling and the platform's entitlement/Paystack infrastructure also provide reusable foundations; they still need explicit HomeDome integration.

The running IoT container has Python **3.12.14**, SQLAlchemy and HTTPX. Pandas, NumPy and JupyterLab are absent there. Simple aggregates can use SQL and ordinary Python immediately; add numerical dependencies to a pinned reporting worker only where required. An optional local Jupyter environment should be separate from the live IoT service.

Home Assistant distinguishes raw history from statistics. Supported sensors produce five-minute statistics and hourly long-term aggregates, including measurement min/max/mean or meter growth. Raw history and short-term statistics are normally purged after ten days; long-term statistics are retained. These are different from our own 30-day HomeDome observations. [Statistics documentation](https://data.home-assistant.io/docs/statistics/).

**The important addition is a historical-statistics importer.** Home Assistant 2026.10.1 implements `recorder/list_statistic_ids` and `recorder/statistics_during_period` over its authenticated WebSocket API. Use a version-tested adapter to import selected statistics, rather than exposing the Recorder database to the VPS or browser. These commands are verified in the pinned version's source; future releases require compatibility checks. [Recorder WebSocket implementation](https://github.com/home-assistant/core/blob/2026.10.1/homeassistant/components/recorder/websocket_api.py).

The gateway token was not configured at the last HomeDome verification. Real historical imports, sensor availability and report accuracy therefore remain untested. A room showcase is not evidence that real reporting data exists.

## Reports worth building

| Report | Customer value | Required data |
| --- | --- | --- |
| Energy and cost | Daily/monthly consumption, previous-period comparison, estimated month-end bill | Energy counters and a dated tariff; cost labelled as an estimate |
| Solar and battery | Generation, import/export, self-consumption and charge/discharge trends | Separate compatible meters; avoid counting battery flows twice |
| Water and gas | Consumption trends and unusual overnight use | Valid cumulative meters and units |
| Rooms and comfort | Temperature/humidity trends, time outside customer-selected ranges | Room assignments and supported sensors |
| Device reliability | Unavailable periods, low batteries and stale readings | Actual state transitions; polling-only estimates labelled accordingly |
| Automation history | Trigger, action, result and cause timeline | Additional selected event/context collection; current sync does not provide this |
| Forecast and anomalies | Consumption forecast with uncertainty, unusual usage flags | Sufficient valid history, coverage checks and a tested baseline |

Show freshness, missing periods, units, time zone and coverage beside every report. A gap is not zero. Handle meter resets, corrected statistics and entity renames. Appliance-level costs need appliance meters; room membership alone cannot establish energy consumption or savings.

Start with deterministic summaries and forecasts. The existing forecasting service is a candidate for reuse, but its HomeDome data contract and accuracy must be tested. AI can explain computed results later; it should not invent measurements or run customer-supplied Python/SQL.

## Local versus VPS

| Component | Local pilot | Production |
| --- | --- | --- |
| Home Assistant and Recorder | Current gateway | A gateway per household at the property |
| Collector | Existing IoT service and adapter | Home connector using an authenticated private route or outbound upload |
| Selected reporting data | Existing Postgres | Tenant/home-scoped tables in existing Postgres |
| Scheduled computation | One bounded Python worker | One shared worker with per-home quotas and bounded concurrency |
| Charts and reports | Existing HomeDome app | Same app, served through the VPS |
| Jupyter | Optional operator-only virtual environment | Usually unnecessary; never a notebook server per customer |

Do not put every household into one shared Home Assistant instance. For remote homes, the current localhost gateway URL is insufficient: implement an authenticated outbound connector or private tunnel, with reconnect/backfill. Avoid public database ports and exposing port 8123 or Jupyter as a customer access mechanism.

The 8 GB development machine already runs several services and recently had disk pressure. A single bounded reporting worker is a better first fit than a notebook/container per tenant. Size the VPS from measured households, sensors, retention and job duration, not just the number of ISP tenants.

For scale: 20 hourly sensor series × 24 hours × 365 days = **175,200 rows per home per year**; 100 homes = **17.52 million rows**. This is a row estimate, not a RAM/disk estimate. Measure index, backup and storage overhead before publishing limits. Home Assistant also requires temporary disk space for Recorder maintenance; do not increase raw retention casually. [Recorder documentation](https://www.home-assistant.io/integrations/recorder/).

## Paid opt-in and provisioning

Suggested starting offer, subject to pilot measurements:

| Included HomeDome reporting | Optional advanced reporting |
| --- | --- |
| Current readings and basic energy/room trends | Up to 12 months of selected hourly aggregates |
| Up to 30 days of available HomeDome observations | Comparisons, anomaly alerts and validated forecasts |
| Manual viewing in the app | Scheduled reports and CSV/printable export |
| Clear gateway/data health | Report history and customer-selected delivery schedules |

The 30-day included history is a proposal based on current storage, not a promise of historical backfill for every sensor. Advanced reports can only backfill history that actually exists in Home Assistant.

Charge for managed storage, computation, delivery and support, not for installing Jupyter. Prefer a predictable monthly fee per home with a selected-sensor allowance. Additional sensor/storage packs and optional AI summaries can be separately priced. Do not make routine chart viewing consume AI credits. Offer a local-only reporting mode if customers do not consent to cloud copies; it can work without cloud retention or remote scheduled delivery.

Do not publish a rand price yet. Measure the pilot's cost per home, then calculate `selling price = fully allocated cost / (1 - target gross margin)`. For example, R12 cost at a proposed 70% margin implies R40 before applicable tax: arithmetic only, not a measured cost or recommended launch price. Include hosting, backups, email, payment fees and support; follow the platform's configured VAT status.

Keep two commercial relationships distinct: **OmniDome bills the ISP tenant**, while **the ISP bills its household customer**. Existing platform checkout is tenant-scoped, so it cannot simply be treated as a household checkout. Add a household product/subscription record linked to the ISP's customer invoice/subscription flow, and a separate platform allowance or wholesale charge where needed.

Provisioning should follow this lifecycle:

1. ISP enables the reporting product and price. Customer selects a home, plan, sensors, cloud/local choice, consent, time zone and report schedule.
2. Check gateway connectivity and available statistics. Show unavailable reports before purchase. Never promise battery/solar reporting without the meters.
3. Activate paid service only after verified payment, or an explicit configured trial/admin grant. Deduplicate payment webhooks and provisioning jobs.
4. Save an entitlement scoped to tenant, customer and home, alongside separate consent and selected-series records. Queue a bounded historical import and show progress.
5. Incremental imports use checkpoints and unique source/hour keys. Re-read an overlap to reconcile late corrections; retry safely without duplicate data or charges.
6. Scheduled jobs create stored report results. The UI shows queued, importing, ready, stale or failed states and the last successful data timestamp.
7. Send AgentMail summaries only to verified, opted-in recipients. Use authenticated report links rather than putting private household details in logs or unrestricted attachments.
8. At cancellation/expiry, stop premium jobs according to the paid-through date. Preserve ordinary device controls and local Recorder. Offer export and apply the disclosed cloud retention/deletion policy. Consent withdrawal stops collection immediately and initiates the applicable purge.

Platform and tenant admins may manage the product and provisioning status. Household reports remain owner-scoped; technician or call-centre access requires the appropriate temporary household grant. A paid entitlement never substitutes for consent. Exclude camera frames, private location and to-do content from the reporting dataset by default.

## Implementation order

First connect the pilot gateway and validate a real energy/temperature sensor. Build a selected hourly-statistics importer with coverage and reset handling, then add a HomeDome Reports view shared by customer and staff interfaces. Verify ownership and consent isolation before enabling scheduled exports.

Next add durable scheduled jobs, export and retention controls. Finally wire the per-home paid product, Paystack activation/renewal/expiry and metering; run a measured multi-home pilot before publishing prices. Existing workflow automation can react to report-ready or anomaly events after those events are implemented, with customer messaging and device control still explicitly gated.

Acceptance checks should cover real gateway history, unit conversions, counter resets, late corrections, missing data, time zones, replayed imports, duplicate payment webhooks, expiry, consent withdrawal and cross-home access. No deployment, notebook installation or billing changes were performed for this review.
