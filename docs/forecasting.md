# Forecasting and metric facts

Connects NUMBERS to the tenant memory. Two deterministic writers, one table (`tenant_metric_facts`), one API
(`POST /api/v1/metrics/facts`, needs `metrics.write`). No LLM writes a number, ever.

```
 governed bi_semantic query ──► bi_metrics_writer ──► ACTUAL facts   (written_by=bi_semantic, method=semantic_query)
                                                          │
                                   services/forecaster ◄──┘  reads actuals, backtests, picks a model
                                          │
                                          └──► FORECAST facts (written_by=forecast_run, lower/upper, model_name+version)
```

## Metric catalog (`services/fno_intelligence/metric_catalog.py`)

Each entry names a governed query (dataset, measure, time dimension, grain). `tests/test_bi_metrics_writer.py` compiles every
entry against the real registry. History needed before any forecast: 12 months / 26 weeks.

| metric_key | dataset . measure | grain | unit | forecast |
|---|---|---|---|---|
| billing.revenue_invoiced.month | billing_invoices . invoiced | month | ZAR | yes |
| billing.revenue_collected.month | billing_invoices . collected (by invoice date) | month | ZAR | yes |
| billing.cash_received.month | billing_payments . payments_received | month | ZAR | yes |
| billing.outstanding_by_aging | billing_invoices . outstanding by aging_bucket | snapshot | ZAR | no |
| billing.mrr_by_plan | billing_subscriptions . mrr by plan | snapshot | ZAR | no |
| billing.cancellations.month | billing_subscriptions . cancelled_subscriptions (cancelled_at) | month | count | yes |
| crm.new_customers.month | crm_customers . customer_count | month | count | yes |
| network.services_activated.month | network_services . service_count (activated_at) | month | count | yes |
| network.sla_breaches.month | network_sla_breaches . breach_count | month | count | yes |
| sales.leads_created.month | sales_leads . lead_count | month | count | yes |
| sales.leads_won.month | sales_leads . won_leads (converted_at) | month | count | yes |
| sales.deals_won.month | sales_pipeline . won_deals (closed_at) | month | count | yes |
| sales.won_value.month | sales_pipeline . won_value (closed_at) | month | ZAR | yes |
| sales.pipeline_value_by_stage | sales_pipeline . open_value by stage | snapshot | ZAR | no |
| support.tickets_opened.week | support_tickets . ticket_count | week | count | yes |
| support.avg_resolution_hours.week | support_tickets . avg_resolution_hours (resolved_at) | week | hours | yes |
| marketing.campaign_sends.month | marketing_campaigns . sent (start_date) | month | count | yes |
| marketing.campaign_conversions.month | marketing_campaigns . conversions (start_date) | month | count | yes |

Churn uses the verified `billing_subscriptions` cancellations; `crm_customers.churned_customers` is a status count with no
churn date, so it is not a time series. Series facts cover COMPLETE periods only (a half-finished month is not an actual).
Additive metrics are zero-filled between the first and last observed bucket; averages are not.

## Actual-fact writer (`bi_metrics_writer.py`)

* `POST /api/fno/bi/metrics/snapshot` (analytics admin) `{metrics?: [...], periods?: n}`; `GET /api/fno/bi/metrics/catalog` (viewer).
* Hook: `bi_semantic.run_query` calls `maybe_record_after_query`; if the query is exactly a catalogued metric it refreshes the facts
  in the background. Best effort, never raises, at most once per tenant+metric per `BI_METRIC_HOOK_MIN_INTERVAL_S` (900 s).
* Daily loop `run_metrics_scheduler` (default ON): once per local day after `BI_METRICS_SNAPSHOT_HOUR` (2), tenants one at a time,
  `BI_METRICS_TENANT_PAUSE_S` (3 s) and `BI_METRICS_METRIC_PAUSE_S` (0.2 s) between units, 8 s statement timeout per query.
  Off with `BI_METRICS_SNAPSHOT_ENABLED=false`. Idle when `TENANT_MEMORY_SERVICE_URL` is unset.
* Idempotent: identity is (tenant, metric, dimensions, period, kind, model_version); reruns update rows in place.
* Write path: HTTP to tenant_memory with the service identity `X-Permissions: metrics.write` (signed by `internal_auth`).
  Agents and LLM tools do not hold that permission.

## Forecaster (`services/forecaster`) - batch job, no API

```
docker compose --profile forecast run --rm forecaster                       # all tenants with actual facts
docker compose --profile forecast run --rm forecaster --tenant <uuid> --metric billing.revenue_invoiced.month --horizon 6
docker compose --profile forecast run --rm forecaster --dry-run -v          # compute and log only
docker compose --profile forecast run --rm forecaster --pending             # execute runs queued via the API
```

Manual trigger: `POST /api/fno/bi/forecast/runs {metrics?, horizon?}` (admin) only inserts a `forecast_runs` row (status `queued`,
deduplicated per tenant); `GET /api/fno/bi/forecast/runs` lists them. The compute happens when `--pending` runs.

Per series: load actuals, trim leading zeros, gap-fill, enforce minimum history (else emit NOTHING and log why; stale history is
also refused), then rolling-origin backtest (up to 8 origins, horizon min(h, 6)) of: naive, drift, SES, damped Holt, Theta
(all numpy), plus seasonal naive and additive Holt-Winters when there are >= 2 seasons and >= 3 seasonal backtest origins, plus
Chronos if available. Lowest MASE wins (sMAPE breaks ties). Intervals (80%): Chronos quantiles, or for baselines the empirical
quantiles of the winner's backtest errors per horizon step (monotone, small-sample inflated, always containing the point).
Counts, currency and hours are clipped at 0. Fallback is automatic: no torch, no weights, or any Chronos error means baselines.

Fact fields: `kind=forecast`, `written_by=forecast_run`, `model_name` (`baseline-theta`, `chronos-bolt-small`, ...),
`model_version` (`theta-1`, or `<chronos-forecasting version>+<config hash>`), `interval_level=0.8`, `lower_bound/upper_bound`,
`confidence = 1 - backtest sMAPE/100` (an accuracy proxy, NOT a probability) and
`method = "forecast:<model>|smape=8.2|mase=0.71|n=6"`. `model_version` encodes the model identity because the fact upsert does not
update `model_name`; if the winner changes between runs, rows for the same period exist under both versions (see card notes).

Schedule: run weekly after the daily snapshot, e.g. cron `30 3 * * 1 cd /path/omnidome && docker compose --profile forecast run --rm forecaster`
(or `*/15 * * * *  ... forecaster --pending` to serve queued API requests). Weekly series refresh weekly; monthly series gain
nothing from daily runs.

### Models and licensing

* Chronos-Bolt (`amazon/chronos-bolt-tiny|mini|small|base`) and Chronos-2 (`amazon/chronos-2`, 120M): Apache-2.0, CPU capable.
  Default `chronos-bolt-small`. Allow-listed in `chronos_adapter.py`; anything else is refused.
* TimesFM 3.0: NOT used. Its weights are license-restricted (commercial use only through Google Cloud). TimesFM <= 2.5 (Apache-2.0)
  could be added as another adapter behind a flag; it is not implemented.
* Weights are never downloaded by the job (`HF_HUB_OFFLINE=1`). Chronos runs only if the package imports AND
  `$FORECAST_MODEL_DIR/<model>/config.json` exists.

### Build and pull weights (not yet done on this machine)

Image: `docker compose --profile forecast build forecaster` (CPU torch + chronos: roughly 1.5-2 GB, first build downloads ~250 MB torch
wheel plus transformers; `--build-arg WITH_CHRONOS=0` gives a ~250 MB numpy-only image). Memory limit 1.5 GB.
Weights (volume `forecast_models`, one time; approx sizes bolt-tiny 35 MB, mini 90 MB, small 190 MB, base 0.8 GB, chronos-2 0.5 GB):

```
docker compose --profile forecast run --rm --no-deps -e HF_HUB_OFFLINE=0 --entrypoint python forecaster -c \
  "from huggingface_hub import snapshot_download; snapshot_download('amazon/chronos-bolt-small', local_dir='/models/chronos-bolt-small')"
```
(`huggingface_hub` ships with `chronos-forecasting`/transformers.) To avoid the VM during the pull, download on the host and copy into the
volume. On this machine (no GPU, Docker on HDD): keep to bolt-tiny/mini/small, one container at a time.

## Card requirements (coordination note for the knowledge-layer owner; `knowledge/**` was not touched)

`metric_fact_card` already renders value, interval ("80% interval a to b"), model name/version, method, confidence and the source
query. Recommended additions for forecasts:

1. A line "Forecast, not a promise: expected range, not a guarantee" on every `kind=forecast` card, and importance stays `high` only
   if the backtest is decent.
2. Parse `method` (`forecast:<model>|smape=..|mase=..|n=..`) to print "Backtest error: sMAPE 8.2%, MASE 0.71 over 6 origins"; if
   MASE >= 1 (no better than naive) say "low reliability".
3. Show "As of <as_of date>" (the run date) next to the period, and the history cut-off.
4. Dedupe: when several forecast rows exist for the same metric, dimensions and period (different `model_version`s from earlier runs),
   index/recall only the one with the newest `as_of`.
5. The "vs prior period" delta for a forecast should compare with the last ACTUAL, labelled "vs last actual (<period>)".
6. Never present an `actual` and a `forecast` for the same period as the same number; label kind in the card title.

## Verified vs not

Verified here (system Python, no network): catalog compiled against the real registry; snapshot upserts idempotent and tenant scoped;
actual facts validate against `MetricFactIn`, and the permission header is sent; hook best-effort/rate-limited; baselines recover
trend and seasonality; backtest picks the lowest-MASE model; interval coverage sanity; min-history, stale, negative-clipping and
fallback guards; run queue claim; no LLM or torch import in the baseline path.

NOT verified: Chronos/torch and the real weights (the adapter code is written against the documented `chronos-forecasting` API and
only exercised through a fake model); the Docker image has not been built; the live HTTP round trip into tenant_memory on Postgres
(the upsert SQL is Postgres only; tests stub the sink); Postgres-specific paths in `forecast_runs` claiming; the signed-identity
check against a real `INTERNAL_AUTH_SECRET` (the service user id must be acceptable to the tenant_memory auth mode in use).
