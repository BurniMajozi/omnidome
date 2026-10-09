"""ARI Stasis event handler: inbound routing, click-to-call, hold / transfer / DTMF, recording.

Everything here talks to two narrow interfaces so it can be tested with fakes and no network:
  * `ari`   - AriClient-like (originate/answer/hangup/hold/... see ari.py)
  * `store` - async persistence (see store.py: route_for_did, ring_agents, create_session, ...)

Tenant isolation: a call is bound to exactly one tenant when it is created (from the DID route for
inbound, from the authenticated caller for outbound). Channels are mapped to calls by id, every public
accessor takes the tenant id, and a channel we did not originate is never trusted to carry its own tenant.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from services.call_center.telephony import confgen
from services.call_center.telephony.ari import AriError

logger = logging.getLogger("call_center.telephony.bridge")

MAX_RING_AGENTS = 5
RING_INTERVAL = 3.0
AGENT_LEG_TIMEOUT = 20
OUTBOUND_SETUP_TIMEOUT = 75
XFER_TIMEOUT = 45
NOTICE_WAIT = 15.0
RECORDING_NOTICE_MEDIA_ENV = "ASTERISK_RECORDING_NOTICE_SOUND"
DEFAULT_NOTICE_MEDIA = "sound:this-call-may-be-monitored-or-recorded"
_DTMF = re.compile(r"^[0-9A-Da-d*#]{1,32}$")


@dataclass
class TenantRoute:
    tenant_id: uuid.UUID
    queue_id: Optional[uuid.UUID] = None
    max_concurrent_calls: int = 5
    max_call_seconds: int = 3600
    max_wait_seconds: int = 120
    recording: bool = False  # recording_enabled AND announcement confirmed


@dataclass
class RingAgent:
    agent_id: uuid.UUID
    endpoint_id: str


@dataclass
class CallState:
    id: str                       # uuid hex
    tenant_id: uuid.UUID
    direction: str                # INBOUND | OUTBOUND
    route: TenantRoute
    number: str = ""              # the remote party (E.164 / caller id as presented)
    state: str = "new"            # new|ringing|agent_ringing|dialing|announcing|connected|transferring|ended
    cust_channel: Optional[str] = None
    agent_channel: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    bridge_id: Optional[str] = None
    started: float = field(default_factory=time.monotonic)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    answered_mono: Optional[float] = None
    answered_at: Optional[datetime] = None
    held: bool = False
    record: bool = False
    recording_name: Optional[str] = None
    trunk_endpoint: Optional[str] = None
    caller_id: Optional[str] = None
    ring_channels: Dict[str, RingAgent] = field(default_factory=dict)
    xfer_channel: Optional[str] = None
    xfer_agent_id: Optional[uuid.UUID] = None
    ignore_end: Set[str] = field(default_factory=set)
    tasks: List[asyncio.Task] = field(default_factory=list)
    end_reason: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        return {
            "id": self.id, "session_id": str(self.session_id) if self.session_id else None,
            "direction": self.direction, "state": self.state, "number": self.number,
            "agent_id": str(self.agent_id) if self.agent_id else None, "held": self.held,
            "recording": bool(self.record and self.state in ("connected", "transferring")),
            "started_at": self.started_at.isoformat(),
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
            "max_seconds": self.route.max_call_seconds,
        }


class TelephonyBridge:
    def __init__(self, ari, store, *, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                 notice_media: str = DEFAULT_NOTICE_MEDIA):
        self.ari = ari
        self.store = store
        self._sleep = sleep
        self.notice_media = notice_media
        self._calls: Dict[str, CallState] = {}
        self._chan: Dict[str, str] = {}               # channel id -> call id
        self._playbacks: Dict[str, asyncio.Event] = {}
        self._tasks: Set[asyncio.Task] = set()
        self.admission_lock = asyncio.Lock()
        self.connected = False
        self.last_error: Optional[str] = None

    # ── introspection (tenant-checked) ───────────────────────────────
    def active_count(self, tenant_id) -> int:
        return sum(1 for c in self._calls.values() if str(c.tenant_id) == str(tenant_id))

    def active_for_agent(self, tenant_id, agent_id) -> Optional[CallState]:
        for c in self._calls.values():
            if str(c.tenant_id) == str(tenant_id) and c.agent_id and str(c.agent_id) == str(agent_id):
                return c
        return None

    def list_active(self, tenant_id, agent_id=None) -> List[Dict[str, Any]]:
        return [c.public() for c in self._calls.values()
                if str(c.tenant_id) == str(tenant_id) and (agent_id is None or str(c.agent_id) == str(agent_id))]

    def get_call(self, tenant_id, call_id: str) -> Optional[CallState]:
        c = self._calls.get(call_id)
        return c if c is not None and str(c.tenant_id) == str(tenant_id) else None

    def set_link_state(self, connected: bool, error: Optional[str] = None) -> None:
        self.connected = connected
        self.last_error = error

    # ── task plumbing ────────────────────────────────────────────────
    def _spawn(self, coro, call: Optional[CallState] = None) -> asyncio.Task:
        async def runner():
            try:
                await coro
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("telephony task failed")
        task = asyncio.get_running_loop().create_task(runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        if call is not None:
            call.tasks.append(task)
        return task

    async def settle(self, timeout: float = 2.0) -> None:
        """Wait for in-flight handler tasks (used by tests and graceful shutdown)."""
        pending = [t for t in self._tasks if not t.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    async def _quiet(self, coro) -> None:
        try:
            await coro
        except AriError as exc:
            logger.info("ARI call ignored: %s", exc)

    # ── event entry point ────────────────────────────────────────────
    async def handle_event(self, ev: Dict[str, Any]) -> None:
        etype = ev.get("type")
        if etype == "StasisStart":
            ch = ev.get("channel") or {}
            args = [str(a) for a in (ev.get("args") or [])]
            self._spawn(self._on_stasis_start(ch, args))
        elif etype in ("ChannelDestroyed", "StasisEnd"):
            cid = (ev.get("channel") or {}).get("id")
            if cid:
                self._spawn(self._on_channel_gone(cid))
        elif etype == "PlaybackFinished":
            pid = (ev.get("playback") or {}).get("id")
            evt = self._playbacks.get(pid)
            if evt is not None:
                evt.set()
        elif etype in ("RecordingFinished", "RecordingFailed"):
            rec = ev.get("recording") or {}
            self._spawn(self._on_recording(rec.get("name", ""), etype == "RecordingFinished"))

    async def _on_stasis_start(self, ch: Dict[str, Any], args: List[str]) -> None:
        cid = ch.get("id", "")
        kind = args[0] if args else ""
        if kind == "inbound":
            await self._on_inbound(ch, args)
            return
        call = self._calls.get(args[1]) if len(args) > 1 else None
        # only channels WE originated may enter with these roles
        if call is None or self._chan.get(cid) != call.id:
            logger.warning("unexpected Stasis entry (kind=%s) hung up", kind[:20])
            await self._quiet(self.ari.hangup(cid))
            return
        if kind == "agent_leg":
            await self._on_agent_answered_inbound(call, cid)
        elif kind == "out_agent":
            await self._on_out_agent(call, cid)
        elif kind == "out_cust":
            await self._on_out_customer(call, cid)
        elif kind == "xfer_target":
            await self._on_xfer_answered(call, cid)
        else:
            await self._quiet(self.ari.hangup(cid))

    # ── inbound ──────────────────────────────────────────────────────
    async def _on_inbound(self, ch: Dict[str, Any], args: List[str]) -> None:
        cid = ch.get("id", "")
        if len(args) < 3:
            await self._quiet(self.ari.hangup(cid))
            return
        th, did = args[1], args[2]
        ctx = (ch.get("dialplan") or {}).get("context") or ""
        route = await self.store.route_for_did(did)
        if route is None or confgen.tenant_hex(route.tenant_id) != th or (ctx and ctx != f"in_{th}"):
            logger.info("inbound call to unknown DID ignored")
            await self._quiet(self.ari.hangup(cid, "congestion"))
            return
        async with self.admission_lock:
            if self.active_count(route.tenant_id) >= route.max_concurrent_calls:
                busy = True
            else:
                busy = False
                call = CallState(id=uuid.uuid4().hex, tenant_id=route.tenant_id, direction="INBOUND", route=route,
                                 number=str((ch.get("caller") or {}).get("number") or "unknown")[:40],
                                 state="ringing", cust_channel=cid)
                self._calls[call.id] = call
                self._chan[cid] = call.id
        if busy:
            await self.store.audit(route.tenant_id, "inbound", "refused:max_concurrent_calls", to_number=did)
            await self._quiet(self.ari.hangup(cid, "busy"))
            return
        await self._quiet(self.ari.answer(cid))
        if route.recording:
            call.record = await self._play_notice(call, cid)
        await self._quiet(self.ari.moh_start(cid))
        self._spawn(self._ring_loop(call), call)

    async def _play_notice(self, call: CallState, channel_id: str) -> bool:
        """Play the recording announcement; True only if it was accepted AND finished (recording needs it)."""
        pid = f"cc-{call.id}-notice"
        evt = asyncio.Event()
        self._playbacks[pid] = evt
        try:
            await self.ari.play(channel_id, self.notice_media, pid)
            await asyncio.wait_for(evt.wait(), NOTICE_WAIT)
            return True
        except (AriError, asyncio.TimeoutError):
            logger.warning("recording announcement not played; call will NOT be recorded")
            return False
        finally:
            self._playbacks.pop(pid, None)

    async def _ring_loop(self, call: CallState) -> None:
        deadline = time.monotonic() + max(5, call.route.max_wait_seconds)
        idx = 0
        while call.state == "ringing" and time.monotonic() < deadline:
            try:
                candidates = await self.store.ring_agents(call.tenant_id, call.route.queue_id)
            except Exception:  # noqa: BLE001
                logger.exception("ring_agents failed")
                candidates = []
            busy_agents = {a.agent_id for a in call.ring_channels.values()}
            for cand in candidates:
                if call.state != "ringing" or len(call.ring_channels) >= MAX_RING_AGENTS:
                    break
                if cand.agent_id in busy_agents or self.active_for_agent(call.tenant_id, cand.agent_id):
                    continue
                try:
                    if await self.ari.endpoint_state(cand.endpoint_id) != "online":
                        continue
                except AriError:
                    continue
                idx += 1
                chan = f"cc-{call.id}-a{idx}"
                call.ring_channels[chan] = cand
                self._chan[chan] = call.id
                try:
                    await self.ari.originate(endpoint=f"PJSIP/{cand.endpoint_id}", app_args=["agent_leg", call.id],
                                             channel_id=chan, caller_id=call.number, timeout=AGENT_LEG_TIMEOUT)
                except AriError:
                    call.ring_channels.pop(chan, None)
                    self._chan.pop(chan, None)
            await self._sleep(RING_INTERVAL)
        if call.state == "ringing":
            await self._end_call(call, "ABANDONED", "no_agent_answered")

    async def _on_agent_answered_inbound(self, call: CallState, chan: str) -> None:
        agent = call.ring_channels.get(chan)
        if call.state != "ringing" or call.agent_channel or agent is None:
            await self._quiet(self.ari.hangup(chan))
            return
        call.agent_channel = chan
        call.agent_id = agent.agent_id
        for other in [c for c in call.ring_channels if c != chan]:
            call.ignore_end.add(other)
            await self._quiet(self.ari.hangup(other))
        call.ring_channels = {chan: agent}
        call.session_id = await self.store.create_session(
            call.tenant_id, agent.agent_id, "INBOUND", call.route.queue_id, call.cust_channel,
            "given" if call.record else "unknown")
        await self._quiet(self.ari.moh_stop(call.cust_channel))
        await self._connect(call)

    # ── outbound (click-to-call) ─────────────────────────────────────
    async def start_outbound(self, *, route: TenantRoute, agent_id, agent_endpoint: str, number: str,
                             trunk_endpoint: str, caller_id: Optional[str]) -> CallState:
        """Caller (service layer) has already authorised the call and applied dial policy/limits."""
        async with self.admission_lock:
            if self.active_count(route.tenant_id) >= route.max_concurrent_calls:
                raise PermissionError("max_concurrent_calls")
            if self.active_for_agent(route.tenant_id, agent_id):
                raise PermissionError("agent_busy")
            call = CallState(id=uuid.uuid4().hex, tenant_id=route.tenant_id, direction="OUTBOUND", route=route,
                             number=number, state="agent_ringing", agent_id=agent_id,
                             trunk_endpoint=trunk_endpoint, caller_id=caller_id)
            self._calls[call.id] = call
        chan = f"cc-{call.id}-ag"
        call.agent_channel = chan
        self._chan[chan] = call.id
        try:
            call.session_id = await self.store.create_session(
                route.tenant_id, agent_id, "OUTBOUND", None, None, "unknown")
            await self.ari.originate(endpoint=f"PJSIP/{agent_endpoint}", app_args=["out_agent", call.id],
                                     channel_id=chan, caller_id=number, timeout=AGENT_LEG_TIMEOUT)
        except Exception:
            await self._end_call(call, "NO_ANSWER", "originate_failed")
            raise
        self._spawn(self._setup_watchdog(call), call)
        return call

    async def _setup_watchdog(self, call: CallState) -> None:
        await asyncio.sleep(OUTBOUND_SETUP_TIMEOUT)
        if call.state in ("agent_ringing", "dialing", "announcing"):
            await self._end_call(call, "NO_ANSWER", "setup_timeout")

    async def _on_out_agent(self, call: CallState, chan: str) -> None:
        if call.state != "agent_ringing":
            await self._quiet(self.ari.hangup(chan))
            return
        call.state = "dialing"
        cust = f"cc-{call.id}-cust"
        call.cust_channel = cust
        self._chan[cust] = call.id
        try:
            await self.ari.originate(endpoint=f"PJSIP/{call.number}@{call.trunk_endpoint}",
                                     app_args=["out_cust", call.id], channel_id=cust,
                                     caller_id=call.caller_id, timeout=45)
        except AriError:
            await self._end_call(call, "NO_ANSWER", "trunk_originate_failed")

    async def _on_out_customer(self, call: CallState, chan: str) -> None:
        if call.state != "dialing":
            await self._quiet(self.ari.hangup(chan))
            return
        if call.route.recording:
            call.state = "announcing"
            call.record = await self._play_notice(call, chan)
            if call.state != "announcing":
                return
        await self._connect(call)

    # ── common connect ───────────────────────────────────────────────
    async def _connect(self, call: CallState) -> None:
        bridge_id = f"cc-{call.id}-br"
        try:
            await self.ari.create_bridge(bridge_id)
            call.bridge_id = bridge_id
            await self.ari.add_to_bridge(bridge_id, call.cust_channel)
            await self.ari.add_to_bridge(bridge_id, call.agent_channel)
        except AriError:
            await self._end_call(call, "NO_ANSWER", "bridge_failed")
            return
        call.state = "connected"
        call.answered_mono = time.monotonic()
        call.answered_at = datetime.now(timezone.utc)
        if call.direction == "OUTBOUND" and call.session_id and call.record:
            await self.store.set_consent(call.tenant_id, call.session_id, "given")
        await self.store.set_agent_status(call.tenant_id, call.agent_id, "ON_CALL")
        if call.record:
            call.recording_name = f"{confgen.tenant_hex(call.tenant_id)}_{call.session_id.hex}"
            try:
                await self.ari.record_bridge(bridge_id, call.recording_name)
            except AriError:
                call.recording_name = None
                logger.warning("recording could not be started")
        self._spawn(self._duration_watchdog(call), call)

    async def _duration_watchdog(self, call: CallState) -> None:
        await asyncio.sleep(call.route.max_call_seconds)
        if call.state in ("connected", "transferring"):
            await self._end_call(call, "COMPLETED", "max_duration")

    # ── teardown ─────────────────────────────────────────────────────
    async def _on_channel_gone(self, cid: str) -> None:
        call_id = self._chan.get(cid)
        call = self._calls.get(call_id) if call_id else None
        if call is None or call.state == "ended":
            return
        if cid in call.ignore_end:
            call.ignore_end.discard(cid)
            self._chan.pop(cid, None)
            return
        if cid == call.xfer_channel and call.state == "transferring":
            call.xfer_channel = None
            call.xfer_agent_id = None
            call.state = "connected"  # transfer target never answered; keep the original call
            return
        if cid in call.ring_channels and call.state == "ringing":
            call.ring_channels.pop(cid, None)  # that agent did not answer; ring loop may retry
            self._chan.pop(cid, None)
            return
        if cid in (call.cust_channel, call.agent_channel):
            outcome = "COMPLETED" if call.state in ("connected", "transferring") else (
                "ABANDONED" if call.direction == "INBOUND" else "NO_ANSWER")
            await self._end_call(call, outcome, "hangup")

    async def _end_call(self, call: CallState, outcome: str, reason: str) -> None:
        if call.state == "ended":
            return
        was_connected = call.state in ("connected", "transferring")
        call.state = "ended"
        call.end_reason = reason
        me = asyncio.current_task()
        for t in call.tasks:
            if t is not me and not t.done():
                t.cancel()
        chans = {c for c in (call.cust_channel, call.agent_channel, call.xfer_channel, *call.ring_channels) if c}
        for c in chans:
            await self._quiet(self.ari.hangup(c))
        if call.bridge_id:
            await self._quiet(self.ari.destroy_bridge(call.bridge_id))
        duration = int(time.monotonic() - call.answered_mono) if call.answered_mono else 0
        if call.session_id:
            await self.store.finish_session(call.tenant_id, call.session_id, outcome, duration)
        elif call.direction == "INBOUND":
            await self.store.audit(call.tenant_id, "inbound", f"missed:{reason}", to_number=call.number)
        for aid in {a for a in (call.agent_id, call.xfer_agent_id) if a}:
            await self.store.set_agent_status(call.tenant_id, aid, "IDLE", only_if="ON_CALL")
        for c in list(self._chan):
            if self._chan[c] == call.id:
                del self._chan[c]
        self._calls.pop(call.id, None)

    async def _on_recording(self, name: str, ok: bool) -> None:
        # name is "<tenant_hex>_<session_hex>"; resolve the owning call row through the store (tenant-checked)
        m = re.fullmatch(r"([0-9a-f]{32})_([0-9a-f]{32})", name or "")
        if not m:
            return
        await self.store.recording_done(uuid.UUID(m.group(1)), uuid.UUID(m.group(2)), name if ok else None)

    # ── agent-driven actions ─────────────────────────────────────────
    def _require(self, tenant_id, call_id: str, *, states=("connected",)) -> CallState:
        call = self.get_call(tenant_id, call_id)
        if call is None:
            raise LookupError("call not found")
        if call.state not in states:
            raise PermissionError(f"call is {call.state}")
        return call

    async def hangup(self, tenant_id, call_id: str) -> None:
        call = self.get_call(tenant_id, call_id)
        if call is None:
            raise LookupError("call not found")
        await self._end_call(call, "COMPLETED" if call.state in ("connected", "transferring") else (
            "ABANDONED" if call.direction == "INBOUND" else "NO_ANSWER"), "agent_hangup")

    async def hold(self, tenant_id, call_id: str, on: bool) -> CallState:
        call = self._require(tenant_id, call_id)
        if on and not call.held:
            await self.ari.hold(call.cust_channel)
            await self._quiet(self.ari.moh_start(call.cust_channel))
        elif not on and call.held:
            await self._quiet(self.ari.moh_stop(call.cust_channel))
            await self.ari.unhold(call.cust_channel)
        call.held = on
        return call

    async def dtmf(self, tenant_id, call_id: str, digits: str) -> None:
        if not _DTMF.match(digits or ""):
            raise ValueError("dtmf must be 1-32 characters from 0-9 A-D * #")
        call = self._require(tenant_id, call_id)
        await self.ari.send_dtmf(call.cust_channel, digits)

    async def transfer(self, tenant_id, call_id: str, *, endpoint: str, caller_id: Optional[str],
                       new_agent_id=None) -> CallState:
        """Blind-ish transfer: dial the target, and when it answers swap it in for the transferring agent
        (the bridge - and any recording - stays up). `endpoint` was authorised by the service layer."""
        call = self._require(tenant_id, call_id)
        chan = f"cc-{call.id}-x{uuid.uuid4().hex[:6]}"
        call.state = "transferring"
        call.xfer_channel = chan
        call.xfer_agent_id = new_agent_id
        self._chan[chan] = call.id
        try:
            await self.ari.originate(endpoint=endpoint, app_args=["xfer_target", call.id], channel_id=chan,
                                     caller_id=caller_id, timeout=XFER_TIMEOUT)
        except AriError:
            call.state, call.xfer_channel, call.xfer_agent_id = "connected", None, None
            self._chan.pop(chan, None)
            raise
        self._spawn(self._xfer_watchdog(call, chan), call)
        return call

    async def _xfer_watchdog(self, call: CallState, chan: str) -> None:
        await asyncio.sleep(XFER_TIMEOUT + 5)
        if call.state == "transferring" and call.xfer_channel == chan:
            call.state, call.xfer_channel, call.xfer_agent_id = "connected", None, None
            await self._quiet(self.ari.hangup(chan))

    async def _on_xfer_answered(self, call: CallState, chan: str) -> None:
        if call.state != "transferring" or call.xfer_channel != chan or not call.bridge_id:
            await self._quiet(self.ari.hangup(chan))
            return
        old = call.agent_channel
        old_agent = call.agent_id
        call.ignore_end.add(old)
        await self.ari.add_to_bridge(call.bridge_id, chan)
        await self._quiet(self.ari.remove_from_bridge(call.bridge_id, old))
        await self._quiet(self.ari.hangup(old))
        call.agent_channel = chan
        call.xfer_channel = None
        call.state = "connected"
        if call.xfer_agent_id:
            call.agent_id = call.xfer_agent_id
            await self.store.set_session_agent(call.tenant_id, call.session_id, call.agent_id)
            await self.store.set_agent_status(call.tenant_id, call.agent_id, "ON_CALL")
            if old_agent:
                await self.store.set_agent_status(call.tenant_id, old_agent, "IDLE", only_if="ON_CALL")
            call.xfer_agent_id = None
        else:
            # target is an external number: the transferring agent is free again
            if old_agent:
                await self.store.set_agent_status(call.tenant_id, old_agent, "IDLE", only_if="ON_CALL")
            call.agent_id = None

    # ── startup recovery ─────────────────────────────────────────────
    async def recover(self) -> None:
        """Memory is lost on restart: hang up channels we originated, close sessions left open."""
        try:
            for ch in await self.ari.list_channels():
                if str(ch.get("id", "")).startswith("cc-"):
                    await self._quiet(self.ari.hangup(ch["id"]))
        except AriError:
            pass
        await self.store.close_orphans()
