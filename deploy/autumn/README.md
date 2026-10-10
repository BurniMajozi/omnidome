# Autumn runtime preparation

This directory is preparation for the self-hosted entitlement service. It is not a working deployment or a completed Paystack connector.

Pinned upstream source: `https://github.com/useautumn/autumn.git`, commit `89b5b6dc2653a19b758815d09b109061c70ecc40`.

The Dockerfile uses the upstream Bun runtime and frozen lockfile, without the BuildKit cache mount that the current local Docker installation cannot process. The build context must be a checkout of that upstream commit, not OminiDome's repository root. Dependency installation disables lifecycle scripts, matching upstream's install policy.

The initial local build did not finish and was stopped during the architecture review. This Dockerfile has not been validated as a functioning runtime. PostgreSQL schema setup, cache, Kafka topics, balance workers, queues, organization/API-key initialization, secrets and Stripe-free balance operations all remain to be configured and tested. No service is activated by this file.

See `docs/platform-commercial-architecture-2026-10-10.md` for the cost controls, commercial boundaries and implementation sequence. Define and validate the allowance rate card before enforcing usage limits.
