# Chat clarification and forecasting repair

## Confirmed question failure

The live logs show three `ask_user` calls with the header `Retry Workflow` (14 characters), using both two and four options. The runtime validator capped headers at 12. It rejected the requests before persisting a pending question or emitting the question-card event, then returned an inaccurate generic option-count error. Duplicate descriptions were not the cause; the labels were distinct.

The backend header limit is now 24, matching the chat event parser. The advertised tool schema is generated from the runtime validator, with JSON references inlined for provider compatibility. Validation errors now identify the failing field without echoing input. The agent prompt directs it to fix the named field instead of exposing schema debugging to the user. Question ownership, answer validation and human approval boundaries are unchanged.

The orchestrator fix is deployed. Rollback image: `omnidome-chat-agent-orchestrator:before-20261012192543`. Nine clarification tests passed, including both reported request shapes, live progress, durable answers across workers, cancellation and owner/tenant checks. No web rebuild was needed for this failure.

## Forecast findings

The earlier response read current finance totals and weighted sales pipeline. It did not invoke a time-series forecast. The tenant's forecast queue was empty, and no local forecaster image or model volume was present. The Amazon adapter existed as optional source code, rather than a verified deployed model.

Agents now have `forecast.catalog`, `forecast.runs` and approval-gated `forecast.request` tools connected to the existing FNO intelligence APIs. A queued job is explicitly distinguished from a completed forecast. The prompt distinguishes a weighted-pipeline scenario from a statistical time-series forecast. Thirty-three forecaster tests passed, covering backtesting, intervals, provenance, stale history, queue processing, empty-queue efficiency, the current Amazon API signature and fallback. Together with the nine clarification tests, 42 tests passed.

Signed live checks confirmed all three tools, the approval gate on queue requests, 18 catalogue metrics and the empty run queue. The stored monthly Sales/CRM metrics contain one completed period (September 2026), against a 12-period minimum. Billing aging and pipeline snapshots are dimensional snapshots, not substitutes for monthly revenue history. The algorithm must refuse this insufficient history instead of relabelling current balances or weighted pipeline as a model forecast.

## Amazon runtime verification

The configured local model is [Amazon Chronos-Bolt small](https://github.com/amazon-science/chronos-forecasting), running on CPU and compared against statistical baselines. Real offline inference passed in both the standalone image and the configured Compose environment: six finite predictions, ordered 80% intervals, model version `2.3.2+9ca0ebbe`. The lower-error backtested model wins; installing Chronos does not force it to replace a better baseline.

Real inference uncovered two issues that mocked tests missed: the current Transformers 5 release attempted to access an unavailable accelerator on CPU Torch 2.6, and the Chronos adapter used the old `context=` keyword rather than the current `inputs` argument. Dependencies are now pinned to CPU Torch 2.6.0, Chronos Forecasting 2.3.2, Transformers 4.57.1 and Hugging Face Hub 0.36.0. The adapter uses a positional input compatible with both argument names, reports its installed package version, and rounds quantile levels to avoid a false range warning at 80%.

The local runtime is installed as `omnidome-forecaster:latest`, with weights in `omnidome_forecast_models`. `omnidome-forecast.timer` is active and checks approved queued requests every five minutes. An empty queue skips model loading. A read-only dry-run on the real monthly Sales history correctly returned `only 1 usable periods; 12 required` and wrote no forecasts. The queue worker started successfully with no queued requests.

Chronos-2 is supported by the adapter and its input/shape regression test, but its real weights have not been downloaded or verified in this repair. No customer history or forecast result is fabricated when data is missing or stale. The existing platform services were preserved; no Ubuntu restart was needed. Browser interaction testing remains unverified after the earlier automation rejection, but the failed question requests were demonstrably rejected before reaching the UI.
