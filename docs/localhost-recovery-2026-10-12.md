# Localhost recovery and ngrok connectivity

Local OmniDome is restored at **http://localhost:3000**, verified from Windows with HTTP 200. Ubuntu WSL was restarted with the owner's explicit approval. Existing containers were restored gradually, using their saved configuration and images, without deleting data or resetting the database. The automatic startup watchdog is active again.

Billing, agent orchestration, tenant memory and PostgreSQL are running and healthy. Owner billing/usage/invoice endpoints passed read-only checks. The Llama-wrapper/RAG hybrid recall recovered after embedding warm-up and returned three knowledge matches. The separate knowledge-indexing worker retains an existing failing HTTP health probe and one missing capability-builder import; this does not mean that all memory retrieval is down.

## What the ngrok message means

`reconnecting (failed to dial ... connect.ngrok-agent.com:443)` means the ngrok agent could not establish its outbound connection to ngrok's cloud. It is not a localhost application error. Ngrok uses an outbound TLS connection over port 443. [ngrok connectivity architecture](https://ngrok.com/use-cases/share-localhost)

The console still showing a Forwarding address does not prove the cloud tunnel is online. Likewise, `http://127.0.0.1:4040` is the local inspection interface, not the public tunnel.

The pasted error is cut off after `dial`, so it does not establish whether the original failure was DNS resolution, TCP timeout or another network condition. The displayed 2763 ms latency was unusually high, but latency alone cannot identify the cause.

## Results on this computer

- Localhost: HTTP 200.
- Windows DNS lookup for `connect.ngrok-agent.com`: successful.
- Windows TCP connection to that host on port 443: successful.
- Ngrok is running as a Windows process; its inspection API responds on port 4040 and lists the supplied URL forwarding to `http://localhost:3000`.
- The installed agent's **`ngrok diagnose --region in`** passed Internet DNS/TCP/TLS and ngrok India DNS/TCP/TLS/tunnel-protocol checks. It reported a successful diagnostic connection and approximately **655 ms** latency.
- A public request to `https://stellar-drowsily-impose.ngrok-free.dev` still returned HTTP 404 with a short plain-text response. That request did not appear in the local ngrok HTTP inspection list. Thus there is no evidence that this 404 came from OmniDome.

The current network can reach ngrok. The earlier connection failure appears transient. The existing public tunnel is still not reaching this application; restarting the existing agent session is the next practical step. No token failure, exhausted free-plan allowance, firewall block or regional outage was established by these checks.

## Reconnect the existing public tunnel

In the terminal already running ngrok, press **Ctrl+C**, then run:

```powershell
ngrok http 3000 --url=https://stellar-drowsily-impose.ngrok-free.dev
```

This retains the existing public URL. The command's URL flag follows ngrok's documented agent endpoint syntax. [ngrok agent endpoints](https://ngrok.com/docs/ai-gateway/guides/creating-endpoints)

Wait for **Session Status: online**, then reload the public URL. Keep that terminal running. If it returns to reconnecting, copy the complete error line, including the portion after `dial`; the missing suffix is needed to diagnose the original failure accurately. The installed diagnostic command can also be rerun without changing the tunnel:

```powershell
ngrok diagnose --region in
```

The existing ngrok process was inspected, not killed or replaced during diagnosis. No authtoken, account setting, firewall rule or region configuration was changed.

## Earlier trial/demo work

The new trial and demo code passed its recorded source and database tests, but the broad shared-guard deployment was interrupted during image staging. This recovery restored the existing live deployment; it did not claim that the new trial/demo release was activated. The source and its deployment notes remain in `docs/platform-trials-and-demos-2026-10-12.md`.
