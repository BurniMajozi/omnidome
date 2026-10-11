# Isolated Autumn runtime

The runtime image and isolated PostgreSQL schema were prepared locally. Live Stripe-free entitlement validation remains required before bridge activation. Paystack remains the payment processor; the adapter allowlists entitlement operations and rejects paid attach calls.

Pinned upstream source: `https://github.com/useautumn/autumn.git`, commit `89b5b6dc2653a19b758815d09b109061c70ecc40`.

The Dockerfile uses the upstream Bun runtime and frozen lockfile, without the BuildKit cache mount that the current local Docker installation cannot process. The build context must be a checkout of that upstream commit, not OminiDome's repository root. Dependency installation disables lifecycle scripts, matching upstream's install policy.

The dependency installation finished successfully and its completed container was recovered using `recover-image.py`, omitting disposable cache/Git files. `recovered.Dockerfile` repaired the missing temporary directory. A clean reproducible build remains to be verified on adequate hardware.

Run `python3 deploy/autumn/bootstrap.py` inside WSL from this checkout. It validates configuration, reuses managed credentials, initializes isolated storage/topics/schema, seeds an organization and hashed server key, and starts services. It never shares OminiDome's application database. Secrets are generated in memory and retained in managed container environments. Back up credentials and volumes through your secret management before production use; do not discard managed containers' credentials while retaining their database.

The API binds to localhost port 8188. Direct balance transport is loopback-only, so API, balance and queue workers share a network namespace. AWS credentials are dummy local emulator values. Catalog invalidations have one partition; the other topics have four. The initial unused four-partition catalog topic is retained. Schema setup runs drizzle-kit directly with Bun because the image has no Node binary.

Memory limits and one queue worker bound local consumption. Kafka health uses TCP readiness; explicit metadata/topic operations validate Kafka during bootstrap. Infrastructure wait is bounded. The full stack and loaded Ollama models have caused WSL resource pressure; ensure spare memory before starting all services. `python3 deploy/autumn/diagnose.py` prints bounded, redacted diagnostics.

Run `python3 deploy/autumn/probe.py` after startup. It validates grant/dedup/reservation/release using a synthetic customer and removes the balance. No real tenant balance or payment is changed. Keep reconciliation inactive until this passes. Existing legacy plans must not receive automatic grants. Durable processing is in `services/common/autumn_worker.py`; customer debit/enforcement and top-ups remain separate work.

See [current rollout](../../docs/commercial-shadow-rollout-2026-10-11.md) and [provider pricing](../../docs/marketing-provider-pricing-2026-10-11.md) for progress and commercial limits.
