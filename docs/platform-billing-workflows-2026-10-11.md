# Platform billing workflows — 11 October 2026

Deployed and installed: OmniDome tenant platform billing is now connected to the existing event-driven workflow engine. It concerns tenants paying for OmniDome, not their fibre customers' ISP invoices. Six active starter workflows send private in-app bell notifications to active tenant owners, linking to `/platform-billing`. They perform no AI calls, send no email and make no card charges. Open **Admin → Workflows** to view, edit or disable them.

| Workflow | Automatic trigger | Outcome |
| --- | --- | --- |
| Platform credits running low | `platform.billing.credits.low` | Warn the owner when spendable metered capacity reaches 20% of period capacity or 10 credits. |
| Platform credit limit reached | `platform.billing.credits.exhausted` | Explain that capacity is exhausted or reserved and link to usage/top-up options. |
| Platform credit top-up confirmed | `platform.billing.credits.topped_up` | Confirm the verified credit grant, amount and invoice reference. |
| Platform subscription payment failed | `platform.billing.subscription.payment_failed` | Ask the owner to review the subscription; no automatic retry. |
| Platform plan activated or renewed | `platform.billing.plan.activated` | Confirm paid provisioning and invoice details. |
| Platform payment needs review | `platform.billing.payment.review` | Explain that payment was received but automatic provisioning was withheld. |

## How the connection works

The wallet settlement, paid provisioning and signature-verified Paystack failure handling publish sanitised facts into the existing PostgreSQL transactional outbox. Facts commit together with the business change. A consumer matches the tenant's active workflows by event type, then runs `trigger → owner notification → end`. Billing notices contain no card authorisation, email token or provider customer record.

Low/exhausted events are evaluated after completed prepaid-metered operations. Their thresholds include the monthly allowance, prepaid balance carried into the period, and top-up grants during it; reservations reduce spendable capacity. They are throttled to one event per period and severity. They are not retrospective balance scans, and are suppressed while paid credit metering is unpublished/disabled. Voice and email cut-off/automatic recharge remain pending integrations and do not emit metered events through this path yet.

Duplicate settlements produce no second event. A unique `(workflow_id,event_id)` run index protects against concurrent redelivery. Each owner notification has its own transactional `(run_id,node_id,recipient_id)` claim. Client event intake rejects `platform.billing.*`, and the workflow consumer also checks the internal producer source. This protects against fake payment/credit notices from general website event intake.

The workflow engine also contains the previously reviewed agent list/run tools and durable approval continuation. A read-only agent can finish a response from recorded approved action results without replaying writes. Billing starter workflows themselves need no human approval because they only create owner notifications. Old in-flight steps and parked runs without checkpoints still require review; they are not blindly replayed.

## Tenant management

`GET/POST /api/workflows/templates/billing` lists or installs the starters. Installation is restricted to roles allowed to manage approvals. Deterministic tenant-specific IDs make it idempotent and preserve existing edits and disabled statuses. Admin → Workflows includes an **Install billing workflows** button. Notifications are private to active tenant owners; ordinary staff do not receive a tenant-wide financial broadcast.

The requested live installation targets only the primary tenant `00000000-0000-0000-0000-000000000001`. It does not populate every tenant automatically. Other owners/admins may install the starters in their own tenant through the UI. Low and exhausted alerts become operative when the Platform Owner publishes credit pricing; this deployment does not publish a selling rate.

## Verification

- 44 focused workflow/tool/approval tests passed.
- 17 PostgreSQL wallet and tenant-pricing regressions passed after adding the event producers.
- Four new PostgreSQL integration tests passed: verified payment → event → workflow → private owner notification; low/exhausted bands and throttling; sanitised duplicate failure events; concurrent duplicate-event run claims. They also verify idempotent installation and rejection of an untrusted event source.
- The updated web source TypeScript check passed with only stale generated `.next/dev` references excluded. Python compilation and `git diff --check` passed.
- Live hybrid memory/RAG recall succeeded before deployment.

Deployment and installation succeeded. All six starters are active in the primary tenant. Live manual verification run `14baafa4-9c27-416e-a807-e7fe99b910aa` succeeded and created two private owner notifications headed `[TEST]`, explicitly stating that no real balance or payment changed. Actual paid event paths were exercised in the dedicated PostgreSQL test database; no production Paystack payment was invented for testing.

The Linux web production build passed. After activation, signed Platform Admin and tenant-owner checks passed for usage, panel logs, invoice history and delivery preferences, and `/platform-billing` returned HTTP 200. Running hashes match the final workflow migration, template implementation and billing event producer. The watcher is active. Main rollback images carry `before-20261011175709`; the final small orchestrator overlay adds the tested cascading notice-claim cleanup for workflow deletion. No balance, credit selling price, subscription selection or real payment was changed by verification. Source and helpers remain uncommitted/unpushed in the shared checkout.

Visual browser verification remains outstanding because browser automation was previously rejected by its security policy. API, database, source and build checks establish the behaviour reported here; no authenticated browser check is claimed.

## Operational scope

The deployment stages timestamped rollback images, builds Web with bounded memory/CPU, and recreates only Admin, Billing, agent-orchestrator and Web. The watcher is temporarily paused only during activation, then restored. Additive schema changes are `workflow_runs.checkpoint`, `workflow_runs.event_id`, its unique run index and `workflow_notice_effects`. The helper now deploys the full reviewed orchestrator source so the workflow implementation is included.

Autumn remains optional and Paystack remains the payment gateway. No workflow retries an unknown external side effect, authorises an automatic recharge, issues a refund, activates a disputed plan, or sends a customer message. Customer ISP invoice/dispute/payroll/VAT workflow templates are separate future scope.
