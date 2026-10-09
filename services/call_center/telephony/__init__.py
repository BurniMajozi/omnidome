"""Real telephony for the Call Center: Asterisk (PJSIP + ARI) behind a tenant-supplied SIP trunk.

Modules (all pure/testable except routes/service/runtime):
  numbers     E.164 normalisation + dial policy (allow-list, premium-rate blocklist)
  confgen     strict validation + rendering of PJSIP / dialplan config (injection-proof)
  ari         thin async ARI REST + websocket client
  bridge      Stasis event handler: inbound routing, click-to-call, hold/transfer/DTMF, recording
  store       DB access used by the bridge/service (settings, audit, sessions, WebRTC endpoints)
  service     provisioning (reconcile config + reload), admission control, WebRTC credentials
  routes      FastAPI router mounted by main.py
"""
