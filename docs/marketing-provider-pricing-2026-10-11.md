# Managed marketing and provider pricing

Status: draft commercial proposal and tested scenario calculator. These prices do not alter current invoices, subscriptions, or existing integrations. Reviewed 11 October 2026.

## Commercial structure

Keep the software subscription for panel access, seats, contacts, segmentation, campaigns and automation. Add explicit managed-provider capacity: social accounts, email inboxes and domains, email capacity, research credits and audio minutes. AI reasoning uses the separate shared tenant AI allowance. A research operation can therefore consume Firecrawl capacity and AI credits; the UI must explain both before running it. Never describe transcription as the complete cost of a telephone or AI voice call.

HubSpot's published catalog separates marketing contacts from other CRM contacts, limits monthly email sends by contact tier (5×, 10× and 20× across its Marketing Hub editions), and adds shared credits and purchasable capacity. Its catalog lists additional credits at $0.01 each. This is a useful structure, not a price to copy into a South African ISP platform. Commercial terms vary by edition and region; validate the customer's applicable catalog when making comparisons. [HubSpot product catalog](https://legal.hubspot.com/hubspot-product-and-services-catalog). A campaign to 100 recipients consumes 100 sends, rather than one campaign unit. [HubSpot email-send accounting](https://knowledge.hubspot.com/account/which-email-messages-count-towards-my-hubspot-account-s-email-send-limit).

For OminiDome, use opt-in marketing-contact capacities of 500 / 2,000 / 10,000 as a draft value metric. Storing a CRM contact does not make it a billable marketing contact. Contacts eligible for campaigns must be selected explicitly and subject to consent and suppression checks. Email, social connections, research and voice are separately purchased managed capacity; these proposed contact capacities do not imply unlimited provider usage. Existing published contact/send promises require a versioned review before any migration.

## Provider costs and proposed net prices

The canonical draft lives in `apps/web/lib/platform-pricing.json`, `provider_rate_card`; the Platform Owner tenant usage screen displays its calculated floors. Prices below exclude customer VAT.

| Managed capacity | Conservative provider replacement cost | Proposed OminiDome net price | Scope |
|---|---:|---:|---|
| Deepgram transcription | $0.0058/audio minute | R0.59/audio minute | Nova-3 multilingual streaming baseline; prerecorded can cost less |
| Firecrawl | $0.005/provider credit | R0.49/provider credit | Hobby top-up replacement cost; buy in a pack, not tiny payment transactions |
| Zernio social connection | $6/account/month | R499/account/month | First paid account band; other metered services excluded |
| AgentMail inbox | $2/inbox/month | R179/inbox/month | Marginal managed capacity |
| AgentMail custom domain | $2/domain/month | R179/domain/month | Provider capacity; domain registration excluded |
| AgentMail email capacity | $2/1,000 emails/month | R179/1,000 emails/month | Monthly capacity ceiling, not provider billing per delivered email |

[Deepgram pricing](https://deepgram.com/pricing): distinguish streaming from prerecorded, monolingual from multilingual, extra channels and analysis add-ons. TTS character usage, LLM calls, PSTN minutes and telephone numbers need separate entries before publishing a full voice-call price.

[Firecrawl pricing](https://www.firecrawl.dev/pricing): Hobby is $19 monthly for 5,000 credits; a $5 top-up buys 1,000 credits. Basic pages, search results, extraction formats and browser time consume different quantities. Agent mode has dynamic pricing and needs its own maximum-budget authorization. Scrape errors can still consume provider credits even when no useful customer output is produced; record the provider cost while releasing a failed-work customer reservation according to policy.

[Zernio pricing](https://docs.zernio.com/pricing): the first two connected accounts are free at the provider-account level; the next eight are $6 each, then a lower graduated band applies. This is shared procurement capacity, not two free accounts for every tenant. X API calls, metered messaging, managed ads, numbers, calls, SMS, WhatsApp and media ad spend remain separate costs. Charge account-days and prorate connection changes rather than counting each API call as a paid social account.

[AgentMail pricing](https://www.agentmail.to/pricing): Developer starts at $20/month; extra inboxes, domains and blocks of 1,000 monthly emails are $2/month each. Its base subscription, storage and daily sending limits must be reconciled. [AgentMail capacity explanation](https://www.agentmail.to/blog/pay-as-you-go) describes capacity purchased in increments, not automatic per-message billing. Count provider-used email volume separately from customer campaign recipients, including inbound email where applicable. Do not pretend an SMTP campaign, an invoice reminder and an inbox provisioning action have the same unit.

## Profit floor

This review uses a **scenario**, not a live FX quotation: R20/USD, a 15% currency buffer and a 65% target contribution margin. Small per-unit support/hosting allocations are included in the rate card and must be replaced with measured costs. The 65% target is OminiDome's proposed policy, not a claimed industry rule or guaranteed net profit.

Let `C` be provider cost converted to ZAR with the currency buffer, plus allocated delivery cost. Let `N` be purchased units sharing one payment; fixed payment cost must be divided by those units. With customer VAT `v`, payment percentage `p`, fee VAT `f`, fixed fee `F` and target margin `m`:

`minimum net unit price = (C + F × (1 + f) / N) / (1 − m − p × (1 + v) × (1 + f))`.

The default scenario conservatively treats payment-fee VAT as a cost; change this only after Finance confirms tax treatment. Paystack South Africa lists 2.9% + R1 for local card transactions, excluding VAT; EFT and international rates differ. No South African fee cap is assumed. [Paystack ZA pricing](https://paystack.com/za/pricing).

For Zernio the scenario gives a floor around R479/account/month and a proposed R499 price. A stronger FX rate assumption can invalidate that floor; the calculator flags rates below target when FX changes. R899 cannot fund unrestricted social accounts: even the provider's 10-account graduated total of $48 becomes R1,104 with this currency buffer, before email, research, hosting, support and payment fees. Volume discounts improve realized margin after they are earned; never use a future discount as today's guaranteed cost.

Provider free tiers, trial credits and promotional rates do not fund permanent customer promises. Fixed subscriptions must be fully allocated across active paying tenants, with a minimum procurement coverage budget when volumes are low. The present nominal allocations do not prove fixed-cost recovery. For example, a $20 email subscription costs R460 in this buffered scenario regardless of how many tenants share it. Actual provider receipts and tenant counts are required to certify total margin.

For a dedicated managed-email offering, propose a **R1,599/month minimum**, excluding VAT, covering one AgentMail Developer subscription's capacity (10 inboxes, 10 domains, 10,000 monthly emails and 10 GB). With the full buffered R460 provider base, an illustrative R10 delivery allocation and one card transaction, the 65% floor is about R1,512. Additional capacity uses the R179 rates above. This minimum must be rechecked against measured support/storage cost, daily limits and changed provider terms; it is a proposal, not a checkout product. Pooled procurement may support a lower tenant minimum only after the allocated base cost is demonstrably covered by paying tenants.

Propose prepaid **R590/1,000 transcription minutes** and **R2,450/5,000 Firecrawl credits** rather than per-unit card payments. The research pack covers the present Hobby base subscription and uses the higher top-up replacement-cost model for its floor. Credits represent the provider's native consumption, so advanced extraction or browser work can consume more than one credit per page. Packs expire on their disclosed capacity period, and cannot promise unlimited service or rollover that the procurement plan does not support. These pack/minimum proposals are documented only; the six marginal rate entries remain the calculator's draft input.

## Billing and approval journey

1. Choose software bundle or individual panels and seats.
2. Choose explicit managed-capacity add-ons, displaying native units, period, net price, VAT, expiry and provider daily/concurrency limits. Bring-your-own-key remains a distinct mode; it cannot be silently billed as platform-managed usage.
3. Freeze the exact versioned selection and capacity in a platform invoice/subscription quote. Avoid applying the software's annual discount to provider usage without recomputing its floor. Annual software purchases still receive monthly capacity periods; provider commitments and top-ups have explicit rollover rules.
4. Verify Paystack server-side, then enqueue idempotent Autumn grants. Each tenant has separate meters for audio, research, email and connections alongside shared AI credits. Provisioning retries cannot create duplicate grants.
5. Display remaining capacity, a preflight estimate for bulk work and spend caps. Pause at the limit by default. Organisation Owner may purchase a capacity pack; automatic upgrades or payments require an explicit saved opt-in and cap.
6. Platform Owner reviews procurement cost, FX, fixed-cost recovery and contribution margin before publishing a rate-card version. Admin overrides need a reason, expiry and audit trail and cannot extend paid access implicitly.

Implemented now: draft replacement-cost rates and tested floor calculation, Platform Owner review UI, immutable usage/cost ledger and the verified-payment AI entitlement outbox. Still pending: native provider receipt collection, provider-specific Autumn meters, contact/capacity selection, top-up invoices, reservation enforcement, fixed-cost allocation reconciliation and browser verification. These provider draft prices are intentionally excluded from checkout totals until that complete journey is implemented and validated. No claim of profitable production billing is made yet.
