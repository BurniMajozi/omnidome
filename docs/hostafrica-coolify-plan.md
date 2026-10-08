# OmniDome on a HostAfrica VPS with Coolify — plan for ~5 tenants

Drafted 8 October 2026. Prices were read from hostafrica.com (South Africa location) on 8 October 2026 and are in USD per month. HostAfrica shows a 50% promotion on the first month only ("First month, then ..."), so plan on the regular price. Check the USD/ZAR rate and any VAT at checkout.

## 1. What HostAfrica offers

Linux VPS (shared CPU, KVM, NVMe, unlimited traffic up to 1 Gbps, API/CLI access, South Africa/Kenya/Nigeria/Ghana):

| Plan | vCPU | RAM | Disk | Regular price |
|---|---|---|---|---|
| Linux Cloud C4 | 2 | 4 GB | 100 GB | $28.12 |
| Linux Cloud C5 | 4 | 8 GB | 200 GB | $56.24 |
| Linux Cloud C6 | 6 | 12 GB | 300 GB | $84.36 |
| Linux Cloud C7 | 8 | 16 GB | 400 GB | $112.48 |
| Linux Cloud C8 | 12 | 32 GB | 500 GB | $197.32 |

Linux VDS (dedicated RAM, CPU affinity, NVMe):

| Plan | vCPU | RAM | Disk | Regular price |
|---|---|---|---|---|
| VDS Linux S | 3 | 24 GB | 450 GB | $67.50 |
| VDS Linux M | 4 | 32 GB | 600 GB | $90.00 |
| VDS Linux L | 6 | 48 GB | 900 GB | $135.00 |

Add-ons on the VPS line: RAM $4.20/GB, CPU core $4.20, SSD $0.05/GB. Backup plans are sold separately.

## 2. How big does it need to be?

Measured on the local stack on 8 October 2026 (idle, one test tenant): 24 containers use about 2.5 GB of RAM in total, the database is 42 MB. This is a floor, not the 5-tenant figure.

Estimate for 5 active tenants (assumption, to be checked with a load test before launch):

| Item | RAM |
|---|---|
| ~22 Python/FastAPI services (about 120-250 MB each when busy) | 3.0-4.0 GB |
| Next.js web app | 0.5 GB |
| Postgres (shared buffers, connections) | 1.0 GB |
| Hermes agent | 0.4 GB |
| Coolify + Traefik + its own database/redis | 1.0-1.5 GB |
| OS + page cache headroom (30%) | 2.0 GB |
| **Working total** | **about 8-9.5 GB** |

Docker image builds (the Next.js build peaks at several GB) must not run on the production server, or they will starve it. Build in CI (GitHub Actions) and push to a registry, or build on the VPS only with plenty of spare RAM.

## 3. Recommendation

**First choice: VDS Linux S — $67.50/mo (about R1,200 at R18/USD), 3 dedicated vCPU, 24 GB RAM, 450 GB NVMe.**
- Dedicated RAM and CPU affinity means one tenant's busy hour cannot be starved by a neighbour on the host.
- 24 GB covers the whole stack, Coolify, in-place builds and growth to roughly 15-20 tenants.
- It costs less than the 12 GB Cloud C6 ($84.36) and about the same as the 8 GB C5 plus add-ons.
- Infrastructure cost for 5 tenants: about $13.50 (R240) per tenant per month.

**Budget alternative: Linux Cloud C5 — $56.24/mo, 4 vCPU, 8 GB.** Only workable if: builds happen in CI, Hermes/presentation/voice services stay off, a 4 GB swap file is added, and you accept that it is tight. Upgrade path: scale the plan in place.

**Not recommended:** C4 (4 GB) cannot hold the stack.

## 4. Target architecture

- One VPS, Ubuntu LTS, Docker, Coolify (self-hosted) managing a single Docker Compose project from the GitHub repo (`docker-compose.yaml` plus `docker-compose.production.yml`).
- Traefik (Coolify's proxy) terminates HTTPS with Let's Encrypt certificates.
- Only the web app is public, plus the narrow paths that must be: provider webhooks (Zernio, Paystack, AgentMail), invoice/quote pay pages, published portal pages, unsubscribe. Every backend service stays on the internal Docker network with no published ports.
- Domains (all on omnidome.co.za): `app.` (web), `pay.` or the same host for customer links, `coolify.` (admin dashboard, restricted). The existing `www.omnidome.co.za` stays on Railway until cutover.
- Postgres in a container with a named volume on the VPS.
- Login (Supabase auth): keep the hosted Supabase project at first. HostAfrica also sells Supabase hosting if you want it in-country later.
- Email: AgentMail is external, so no mail server is needed on the VPS.

## 5. Security baseline

- SSH key login only, root login off, SSH limited to your IP if it is static; fail2ban.
- Firewall (UFW): allow 80/443 and SSH only; deny everything else, including Postgres and all service ports.
- Coolify dashboard on its own subdomain with two-factor, never on a bare IP.
- Secrets live only in Coolify's environment store (never in git): `INTERNAL_AUTH_SECRET`, `INVITE_CODE_SECRET`, `SECRETS_ENCRYPTION_KEY`, `INTERNAL_SERVICE_KEY`, Zernio/Paystack/AgentMail keys and webhook secrets, `HERMES_API_KEY`. Generate fresh values for production; do not reuse local ones.
- Keep `AUTH_MODE=signed`, role enforcement flags on, and set `BILLING_OUTBOX_WORKER_ENABLED=true`.
- Automatic security updates; Docker log rotation.

## 6. Backups and recovery (non-negotiable for billing data)

- Nightly `pg_dump` of the whole database, kept 14 daily + 8 weekly, copied off the server (HostAfrica backup add-on or an S3-compatible bucket such as Backblaze B2).
- Back up the Docker volumes for uploads and the secrets file separately. Back up `SECRETS_ENCRYPTION_KEY` outside the server: losing it makes stored provider keys unreadable.
- Run a restore drill before the first real tenant goes live and then quarterly.
- POPIA: data stays in a South African data centre; record the hosting provider as an operator in your records.

## 7. Migration steps

1. Order the VDS (South Africa), choose Ubuntu LTS, add your SSH key.
2. Harden the server (section 5) and install Docker.
3. Install Coolify; put its dashboard on `coolify.omnidome.co.za` with two-factor.
4. DNS at HostAfrica: add A records for `app.`/`pay.` and `coolify.` pointing at the VPS. Leave `www` alone for now.
5. Create the Compose project in Coolify from the repo; add all secrets; deploy. Services create their tables on first start.
6. Data: local data is test data, so start fresh. Create the platform admin and tenants again through the admin console.
7. Smoke test: log in, run the invoice flow (draft, issue, email, pay link), portal publish, marketing connect. Our end-to-end test script from 7 October can be reused.
8. Webhooks: point Zernio (`/svc/marketing/social/webhooks/zernio/inbound`), Paystack and AgentMail at the new domain and set their secrets there.
9. Monitoring: Uptime Kuma (or similar) for the public pages and a health check of every service, with email/WhatsApp alerts.
10. Cutover: move `www` to the VPS when ready, then shut down Railway and the ngrok tunnel and its Windows startup task.
11. Backups verified (section 6) before inviting the first paying tenant.

## 8. Costs (monthly, indicative)

| Item | Cost |
|---|---|
| VDS Linux S | $67.50 |
| Offsite backup storage (~50 GB) | about $1-3 |
| Domain (already owned) | - |
| Hosted Supabase (free tier at first) | $0 |
| **Total** | **about $70 (about R1,250)** |

Railway comparison needs your actual Railway bill; share it and I will compare.

## 9. Risks and open questions

- The 5-tenant memory figure is an estimate. A load test on the VPS in week one will confirm it.
- Single server means no high availability: a host failure is an outage until restored from backup. Acceptable for 5 tenants; revisit at 20+.
- Decide whether the local-only stand-ins (WhatsApp templates/flows/groups) should be hidden in production until built.
- Decide who can reach the Coolify dashboard and who holds the server and DNS credentials.
