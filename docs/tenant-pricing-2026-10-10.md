# Tenant pricing and ownership

The platform now distinguishes **Platform Owner** from **Organisation Owner / Organisation Admin**. Bundle and modular pricing feed the same server-calculated tenant selection, panel provisioning and platform invoice. The pricing and administration screens share the same catalogue and selection controls.

## Roles

| Display name | Existing role key | Scope |
| --- | --- | --- |
| Platform Owner | `platform_admin` | All organisations; tenant creation, commercial pricing, panel grants and platform administration |
| Organisation Owner | `owner` | One organisation; ownership and lifecycle duties, all of its enabled panels |
| Organisation Admin | `org_admin` | One organisation; team administration and all of its enabled panels |
| Organisation member | Tenant roles such as `org_user` | Inherits that tenant's available panels; role permissions still govern operations |

No organisation owner was automatically promoted to platform ownership. The existing platform role remains the global authority, and the existing tenant owner remains compatible with ownership transfers and last-owner protections. All user identities remain associated with a tenant through the authoritative admin membership record.

Ordinary active members can now read their own tenant's panel list. Cross-tenant reads are denied. An empty or failed entitlement lookup no longer makes every panel visible. Organisation owners/admins receive module permissions, while the enabled tenant module rows remain the upper limit on access. Knowledge/RAG retrieval also intersects non-platform callers with the tenant's enabled panels, including organisation administrators; private memory ownership rules still apply.

## User journey

1. **Public pricing:** choose Professional, Enterprise, Starter, Growth or individual modules. The selected plan, module tiers and billing period carry to `/checkout`.
2. **Admin creation:** the Platform Owner uses the same bundle/module selector, seat count and panel checkboxes when creating an organisation. Its Organisation Owner can be invited through the existing invitation flow. A platform invoice is created from that choice.
3. **Admin editing:** open **Plan, panels & invoices** on a tenant card. Changing a bundled panel switches the selection to modular pricing. Saving applies the Platform Owner's access decision immediately and creates an invoice; it does not charge a card.
4. **Organisation billing:** Organisation Admin/Owner can review their plan and saved invoices in Admin's module section or `/checkout`. Tenant-initiated purchases provision access only after verified payment. New organisations still require Platform Owner provisioning and an invitation; this change does not introduce anonymous self-registration.
5. **Invoice or subscription:** review/download the invoice first. Choose a one-off payment or opt into recurring billing. The gateway uses the saved invoice amount and currency, rather than browser-supplied amounts.

`apps/web/lib/platform-pricing.json` is the shared versioned catalogue. The public page, shared selector and Python quote engine all use it. Prices cover the existing 14 commercial panels, including canonical aliases `service → support`, `talent → hr` and `call-center → call_center`.

Professional monthly is R3,500 net / R4,025 including 15% VAT. Annually, the existing 20% discount gives R2,800 net per month, invoiced for 12 months: R33,600 net + R5,040 VAT = **R38,640 upfront**. Extra seats and additional modules appear in the invoice. The VAT rate is configurable through `PLATFORM_VAT_RATE`.

Legacy tenants retain negotiated settings until the Platform Owner explicitly saves a catalogue selection. Existing seat editing remains available for those tenants; catalogue-backed tenants change seats through pricing so their invoices stay aligned. Analytics, Inventory, IoT and other panels without public catalogue prices can be granted as manual platform exceptions through the existing module checkboxes. No price was invented for them.

## Payment records and verification

Platform SaaS billing uses `platform_orders` and `platform_subscriptions`, separate from invoices owed by an ISP's fibre customers. Every order freezes a quote, tenant, revision, intent and globally unique reference. Idempotency keys prevent repeated requests from creating repeated invoices.

Admin delegates checkout and verification to Billing through signed service calls. These endpoints bypass the ISP Billing panel entitlement, so an organisation can buy a plan without already purchasing that panel. They still require authenticated Organisation Admin/Owner or authoritative Platform Owner access, plus the matching tenant.

Paystack checkout initialization uses the stored amount and a server-created recurring plan when selected. Browser callbacks only request verification. Successful payment requires the matching reference, currency, amount and provider status. Signed Paystack webhooks route platform charges separately from existing ISP charges. Renewal charges create separate frozen invoices, repeated deliveries are idempotent, and cancellation retains subscription history. Abandoned pending subscriptions can be cancelled; a late subscription creation event disables the cancelled provider subscription.

A payment against an older commercial revision, a cancelled renewal, or a seat limit below current occupied seats is retained as `payment_review`. It cannot silently overwrite the administrator's current choice. Review and refund resolution remain manual; this change does not issue automatic refunds or prorated subscription adjustments. Cancel an existing recurring plan before starting a replacement.

Provider behavior follows the official [Paystack transaction API](https://paystack.com/docs/api/transaction/), [subscription API](https://paystack.com/docs/api/subscription/) and [webhook verification documentation](https://paystack.com/docs/payments/webhooks/). No real checkout was initialized, no payment was submitted and no live recurring subscription was created during verification.

## Validation

- Admin, quote and existing webhook checks: **92 passed** against a dedicated PostgreSQL `*_test` database.
- Pricing/subscription and knowledge access checks: **31 passed**, including renewal deduplication and cancellation.
- Final pricing edge cases: **11 passed**, including ordinary-user denial, cross-tenant denial, mismatched amounts, stale revisions, seat growth and integer ISP plan IDs.
- Full Billing suite: **277 passed**. Test references were made tenant-unique so repeat suite runs cannot collide with earlier webhook receipts.
- Web source TypeScript check passed. The normal unfiltered local check contains stale `.next` references to a removed deck harness; a source-only configuration and the Docker production build passed.
- Local route/API checks passed for `/pricing`, `/checkout`, `/api/pricing/catalog`, tenant pricing and module reads. The public annual quote returned R38,640; a supplied client price was rejected with 422.
- The live RAG service was consulted before completing this work and returned grounded citations without degradation. Following service recreation, one early probe saw a temporary DNS failure to the knowledge store; a retry after startup returned 200 with three citations.

Visual browser inspection remains outstanding: the browser tool rejected the existing tab because its current URL used a blocked protocol. There was no alternate-browser workaround. Phone layout and real Paystack checkout should still be exercised interactively before a public rollout.

## Local deployment and handoff

Updated local WSL images: Admin, Billing, tenant memory, FNO intelligence, agent orchestrator and Web. The build uses the existing configured dependencies and Paystack credentials. Backups are tagged `pre-tenant-pricing` and `pre-pricing-final`. The deployment restores running services and the local watchdog.

The earlier RAG-grounded agent takeover is checkpointed in local commit `f78e36a6`; its detailed handoff is `docs/agent-takeover-2026-10-10.md`. This pricing work is a separate local checkpoint. No remote push has been performed for these checkpoints.

Separate edits arrived in agent orchestration, BI tests and the skills catalogue during this work. They are preserved in the working tree and excluded from the tenant-pricing checkpoint. The untracked `.codex/` workspace tools are also retained.
