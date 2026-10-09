# Call Center telephony (Asterisk + tenant SIP trunk)

Real telephone calls for the Call Center: an Asterisk container (`services/asterisk`) behind a SIP trunk the
tenant buys from a provider, agents on browser softphones (WebRTC), and an ARI bridge inside the
`call_center` service (`services/call_center/telephony/`). Speech (STT/TTS) stays on Deepgram.

Nothing here has been exercised against a real trunk. See "Not verified" at the end.

## Architecture

```
 customer ── PSTN ── SIP trunk provider ──SIP/RTP──┐
                                                    │  (public VPS only: UDP/TCP 5060 or TLS 5061, RTP 10000-10100/udp)
 agent browser ──wss://pbx.example.com/ws──► reverse proxy (TLS) ──ws──► asterisk:8088/ws
        ▲  JsSIP (WebRTC: DTLS-SRTP + ICE)                                  │
        │                                                                   │ ARI REST + events (internal network only)
 web UI ── /svc/call-center/telephony/* ──► call_center service ◄───────────┘ asterisk:8088/ari
                                         │   └─ admin sidecar  asterisk:8099 (reload / registrations only)
                                         └─ shared volume asterisk_generated (call_center writes, asterisk reads)
```

* **One Asterisk, many tenants.** Per tenant the call_center service renders `pjsip_<tenanthex>.conf` and
  `ext_<tenanthex>.conf` into the shared volume: a trunk endpoint `trk_<hex>` (registration or IP-auth), the
  tenant's DIDs, and short-lived agent endpoints `w<20hex>`.
* **Isolation.** The trunk endpoint's context `in_<hex>` only contains that tenant's DIDs and hands them to
  `Stasis(omnidome,inbound,<hex>,<did>)`. Unknown DIDs hit `Hangup`. The bridge re-checks that the DID, the
  tenant in the args and the context the call arrived on all agree before touching the call. Agent endpoints
  live in `ag_<hex>` which can only hang up: **agents cannot dial anything directly**; every outbound call goes
  through `POST /telephony/calls`, where policy is enforced. Outbound dials always use the tenant's own
  trunk endpoint, computed server-side from the authenticated tenant.
* **Reload design.** ARI cannot reload config and AMI must never be exposed, so `services/asterisk/admin.py`
  is a tiny stdlib HTTP sidecar (`POST /reload`, `GET /registrations`, `GET /health`), bearer-token protected
  (`ASTERISK_ADMIN_TOKEN`, constant-time compare), fixed argv lists, no shell, container network only.
  call_center reconciles (renders, atomically writes changed files, calls `/reload` only when something
  changed) on: SIP credential save/delete, telephony settings save, WebRTC credential issue, "Test
  registration", and every 60 s (which also prunes expired softphone endpoints).
* **Config injection.** Tenant values only reach config files through allow-list validators
  (`telephony/confgen.py`): hostnames/IPv4 only, usernames `[A-Za-z0-9._+@=-]`, passwords reject `; \ ${` and
  control/non-ASCII characters (rejected, not escaped), DIDs strict E.164, object names derived from UUID hex.
  The save endpoint (`PUT /provider-credentials/sip`) refuses bad values with 422 and never echoes them;
  provisioning validates again, so a poisoned stored row cannot reach the PBX.
* **WebRTC credentials.** `POST /telephony/agents/me/webrtc-credentials` mints a random endpoint and password
  valid for `TELEPHONY_WEBRTC_TTL_SECONDS` (default 900). Only `md5(user:realm:pass)` is stored and written to
  disk (PJSIP `auth_type=md5`); the plaintext exists once, in the response. Max 3 live endpoints per agent. The
  softphone renews before expiry.
* **ARI bridge** (`telephony/bridge.py`, one Stasis app `omnidome`): inbound call on a known DID → answer →
  (optional recording notice) → MOH → ring every IDLE agent that has an online softphone and matches the queue
  skills (up to 5, retried every 3 s until the queue `max_wait`) → first to answer wins, others are hung up →
  mixing bridge → `CallSession` row (existing tables; `provider='asterisk'`, `external_call_id` = customer
  channel). Click-to-call: agent leg rings first (auto-answered by the softphone), then the customer leg is
  originated through the trunk, then both are bridged. Transfer swaps the new party into the existing bridge.
  Calls that nobody answers are audited (`inbound missed:*`) because `call_sessions.agent_id` is required.
* **Recording (POPIA).** Only when `recording_enabled` AND `recording_announcement_confirmed` are both true, AND
  the announcement playback actually finished. The session is stamped `recording_consent='given'`. The
  recording is `<tenanthex>_<sessionhex>.wav` in the `asterisk_recordings` volume; the DB stores only the
  object key `asterisk/<name>.wav` (never audio). Fetching audio/transcribing is admin tier
  (`/recordings/...` is in `access._ADMIN_PATH`) and tenant-checked by file name. Retention uses the existing
  `retention_until`/purge. Optional `TELEPHONY_AUTO_TRANSCRIBE=true` sends finished recordings to Deepgram.
* **Toll-fraud controls (all server-side).** Authenticated agent/admin only; agents can only call as themselves;
  E.164 normalisation (SA default: `+27…`, `0xx…`, `0027…`, `27…`), short codes/extensions/`*#`/letters
  refused; per-tenant allow-listed prefixes (default `["+27"]`; international only when an admin adds a country
  code); built-in premium-rate/satellite/shared-cost blocklist that wins over the allow-list (+ per-tenant
  extra blocks); max concurrent calls, max call duration (watchdog hangs up), calls per agent per hour, all
  bounded by hard caps (`TELEPHONY_HARD_MAX_*`); an audit row for every attempt (`GET /telephony/audit`). Inbound:
  unknown DIDs are hung up; a DID claimed by two tenants is ignored.

## Endpoints (JSON; base `/svc/call-center`)

Errors for telephony routes: `{"detail": {"code": "<stable_code>", "message": "<human text>"}}`.
Tier column: agent = any call-center role, admin = owner/admin/manager-level (existing `access.py` tiers).

| Method + path | Tier | Notes |
|---|---|---|
| `GET /telephony/status` | agent | Safe subset (no host). Drives the softphone's honest states. |
| `GET /telephony/trunk/status` | admin | Same plus `host`, `port`, `transport`. |
| `POST /telephony/trunk/test` | admin | Re-applies config and polls **registration only** (≤12 s). Places no call. |
| `GET/PUT /telephony/settings` | admin | Dial policy, DIDs, limits, recording consent. |
| `GET /telephony/audit?limit=100` | admin | Originate / transfer / inbound-missed log. |
| `POST /telephony/agents/me/webrtc-credentials` | agent | Short-lived SIP creds + WSS URL + ICE servers. |
| `POST /telephony/calls` | agent | Click-to-call. Body `{"to": "082 123 4567", "agent_id"?: uuid (admin only)}` → 201 `ActiveCall`. |
| `GET /telephony/calls/active` | agent (own) / admin (tenant) | `ActiveCall[]` |
| `POST /telephony/calls/{id}/hangup` | agent (own) / admin | |
| `POST /telephony/calls/{id}/hold` | same | Body `{"on": true}` |
| `POST /telephony/calls/{id}/transfer` | same | Body `{"to_agent_id": uuid}` **or** `{"to_number": "..."}` (same dial policy as click-to-call). |
| `POST /telephony/calls/{id}/dtmf` | same | Body `{"digits": "12#"}` (0-9 A-D * #, ≤32), sent to the customer leg. |
| `GET /recordings/{session_id}/audio` | admin | `audio/wav`. |
| `POST /recordings/{session_id}/transcribe` | admin | Deepgram; stores `transcript` on the session (only with consent). |
| `PUT /provider-credentials/sip` | admin | Existing endpoint. Fields: `host`, `port`, `username`, `password`, `transport` (udp\|tcp\|tls), `auth_mode` (registration\|ip), `caller_id`, `caller_name`. |

`TelephonyStatus` (`/telephony/status`):
```json
{"available": true, "bridge_connected": true, "enabled": true, "configured": true, "registered": false,
 "state": "rejected", "detail": "Trunk not registered: rejected. Check host, username and password with your provider.",
 "mode": "registration", "last_error": "rejected", "recording_effective": false, "allowed_prefixes": ["+27"]}
```
`state` ∈ `not_configured | config_error | pbx_unavailable | disabled | not_loaded | registered | reachable |
unreachable | rejected | unregistered | stopped`. UI copy: `not_configured` → "No SIP trunk configured";
anything not registered → "Trunk not registered: <reason>".

`ActiveCall`:
```json
{"id": "<32hex>", "session_id": "<uuid>|null", "direction": "INBOUND|OUTBOUND",
 "state": "ringing|agent_ringing|dialing|announcing|connected|transferring|ended",
 "number": "+27821234567", "agent_id": "<uuid>|null", "held": false, "recording": false,
 "started_at": "…", "answered_at": "…|null", "max_seconds": 3600}
```

`POST /telephony/agents/me/webrtc-credentials` →
```json
{"sip_uri": "sip:w1a2b…@pbx.example.com", "username": "w1a2b…", "password": "<once>", "realm": "omnidome",
 "ws_url": "wss://pbx.example.com/ws", "ice_servers": [{"urls": ["stun:…"]}], "display_name": "Sipho",
 "agent_id": "<uuid>", "expires_at": "…", "expires_in": 900}
```

Refusal codes for `POST /telephony/calls`: `no_agent_profile` (403, the user is not linked to a call-center
agent; set `Agent.user_id`), `telephony_disabled`, `invalid_number` (422), `destination_not_allowed` (403),
`blocked_prefix` (403), `no_trunk`, `trunk_not_registered`, `softphone_not_registered` (409),
`agent_hourly_limit`, `max_concurrent_calls` (429), `agent_busy` (409), `pbx_unavailable` (503).

## Environment variables

call_center (set in `.env`; compose passes them through):

| Var | Purpose |
|---|---|
| `ASTERISK_ARI_URL` | default `http://asterisk:8088` |
| `ASTERISK_ARI_USER` / `ASTERISK_ARI_APP` | default `omnidome` / `omnidome` |
| `ASTERISK_ARI_PASSWORD` | **required**; telephony stays off (no default password) if unset. ≥24 chars `[A-Za-z0-9._~-]` (`openssl rand -hex 24`). |
| `ASTERISK_ADMIN_URL` / `ASTERISK_ADMIN_TOKEN` | reload sidecar, default `http://asterisk:8099`; token ≥32 chars (`openssl rand -hex 24`) |
| `TELEPHONY_WSS_URL` | public `wss://pbx.example.com/ws` given to browsers (must be `wss://`) |
| `TELEPHONY_SIP_DOMAIN` | optional; defaults to the WSS host |
| `TELEPHONY_STUN_URLS` | default Google STUN; comma list |
| `TELEPHONY_TURN_URL` / `_USERNAME` / `_CREDENTIAL` | recommended in production (agents behind strict NAT) |
| `TELEPHONY_WEBRTC_TTL_SECONDS` | 60-3600, default 900 |
| `TELEPHONY_HARD_MAX_CONCURRENT` / `_SECONDS` / `_PER_HOUR` | platform-wide caps (50 / 14400 / 200) |
| `TELEPHONY_GENERATED_DIR` / `TELEPHONY_RECORDINGS_DIR` | `/asterisk-generated` / `/asterisk-recordings` |
| `ASTERISK_RECORDING_NOTICE_SOUND` | default `sound:this-call-may-be-monitored-or-recorded` (confirm the file exists in your sounds package, or point to your own recording) |
| `TELEPHONY_AUTO_TRANSCRIBE` | `true` to transcribe finished recordings via Deepgram |
| `SECRETS_ENCRYPTION_KEY` | already required for provider credentials |

asterisk container: `ASTERISK_ARI_USER`, `ASTERISK_ARI_PASSWORD`, `ASTERISK_ARI_APP`, `ASTERISK_ADMIN_TOKEN`
(all four fail-closed: the container refuses to start without a strong password/token), `ASTERISK_RTP_START/END`
(10000/10100), `ASTERISK_EXTERNAL_IP` (public IPv4; needed on a VPS for media), `ASTERISK_LOCAL_NET`,
`ASTERISK_STUN_SERVER`, `ASTERISK_TLS_CERT`/`ASTERISK_TLS_KEY` (optional SIP-TLS to the provider).

## Running it

Local (WSL/NAT lab, opt-in, publishes nothing to the host):
```
docker compose --profile telephony up -d --build asterisk call_center
```
Registration against a provider and signalling can work locally; **trunk media will not** behind NAT.

Public VPS (HostAfrica + Coolify plan): add a compose override that publishes only what is needed, and nothing else.
```yaml
services:
  asterisk:
    ports:
      - "5060:5060/udp"            # or "5061:5061/tcp" for SIP-TLS only
      - "10000-10100:10000-10100/udp"
```
Never publish 8088, 8099, or any AMI port. Firewall: allow UDP 5060 (or TCP 5061) **only from the provider's
signalling IPs**, UDP 10000-10100 from anywhere (RTP; the provider's media IPs if they publish them).
Set `ASTERISK_EXTERNAL_IP` to the VPS public IPv4.

WSS for browsers: terminate TLS at the reverse proxy and forward **only** `/ws`:
```
pbx.example.com {
    @ws path /ws
    reverse_proxy @ws asterisk:8088
    respond 404          # blocks /ari and everything else
}
```
(Coolify/Traefik: route only the `/ws` path to the asterisk service on port 8088.) The agents' browsers then
use `TELEPHONY_WSS_URL=wss://pbx.example.com/ws`. UDP 3478 (TURN) is needed if you run coturn.

## Not verified without a real trunk

Everything is covered by unit tests with a fake ARI (no network, no Asterisk): number policy, config rendering
and injection resistance, tenant isolation, ARI event handling, limits, audit, credentials-never-logged. Not
exercised end to end: the Docker image build (apt package version `1:20.*` for Debian bookworm), Asterisk
loading the generated PJSIP/dialplan (e.g. exact module names in the reload list, `pjsip list registrations`
output format parsing, `webrtc=yes` behaviour on your exact 20.x), WebRTC media (DTLS-SRTP/ICE through the
proxy), real registration, inbound/outbound audio, the recording announcement sound file, and recordings.
Expect a first-boot tuning pass against a real trunk.

## Owner checklist

- [ ] A SIP trunk from a South African provider (registration or IP-auth); note host, port, transport,
      username/password (or give them your VPS IP for IP-auth), allowed codecs (alaw/ulaw are enabled).
- [ ] DID number(s) on that trunk (E.164), and the outbound caller-ID you are entitled to present.
- [ ] A public VPS with a static IPv4; DNS `pbx.example.com` → VPS.
- [ ] TLS certificate for `pbx.example.com` (Coolify/Let's Encrypt) for WSS; optional cert for SIP-TLS.
- [ ] Firewall/ports: UDP 5060 or TCP 5061 (provider IPs only), UDP 10000-10100, TCP 443 (WSS), UDP/TCP 3478 if TURN.
- [ ] A TURN server (coturn) and its credentials, for agents on restrictive networks.
- [ ] Secrets: `ASTERISK_ARI_PASSWORD`, `ASTERISK_ADMIN_TOKEN`, `ASTERISK_EXTERNAL_IP`, `TELEPHONY_WSS_URL`.
- [ ] Each agent's `Agent.user_id` linked to their platform user (softphone/click-to-call need it).
- [ ] POPIA: decide whether to record; record the announcement audio and set
      `ASTERISK_RECORDING_NOTICE_SOUND`; then tick both recording switches in Telephony settings.
- [ ] Provider terms: confirm the account's international/premium dialling restrictions match ours.
