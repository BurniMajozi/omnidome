"""RFC 5176 Dynamic Authorization: Disconnect-Request over UDP (default port 3799).

Pure struct/hashlib; no third-party RADIUS library. Outcome is only ever "ACK", "NAK" or "TIMEOUT"
(plus "ERROR" for a bad/unauthentic reply): a Disconnect is never reported as sent-OK without a
verified Disconnect-ACK from the NAS.

Request Authenticator = MD5(Code | Id | Length | 16 zero octets | Attributes | Secret)   (RFC 5176 2.3)
Response Authenticator = MD5(Code | Id | Length | Request Authenticator | Attributes | Secret)
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import socket
import struct
from dataclasses import dataclass
from typing import Optional

DISCONNECT_REQUEST = 40
DISCONNECT_ACK = 41
DISCONNECT_NAK = 42

ATTR_USER_NAME = 1
ATTR_NAS_IP_ADDRESS = 4
ATTR_ERROR_CAUSE = 101
ATTR_ACCT_SESSION_ID = 44


def _attr(attr_type: int, value: bytes) -> bytes:
    if len(value) > 253:
        raise ValueError("attribute too long")
    return struct.pack("!BB", attr_type, len(value) + 2) + value


def build_disconnect_request(secret: bytes, identifier: int, *, username: str,
                             nas_ip: Optional[str] = None, session_id: Optional[str] = None) -> bytes:
    attrs = _attr(ATTR_USER_NAME, username.encode("utf-8"))
    if nas_ip:
        attrs += _attr(ATTR_NAS_IP_ADDRESS, ipaddress.IPv4Address(nas_ip).packed)
    if session_id:
        attrs += _attr(ATTR_ACCT_SESSION_ID, session_id.encode("utf-8"))
    length = 20 + len(attrs)
    header = struct.pack("!BBH", DISCONNECT_REQUEST, identifier & 0xFF, length)
    auth = hashlib.md5(header + b"\x00" * 16 + attrs + secret).digest()  # noqa: S324 (mandated by RFC)
    return header + auth + attrs


def request_authenticator(packet: bytes) -> bytes:
    return packet[4:20]


def verify_response(packet: bytes, request_auth: bytes, identifier: int, secret: bytes) -> Optional[int]:
    """Return the response code if the reply is authentic and matches the request, else None."""
    if len(packet) < 20:
        return None
    code, ident, length = struct.unpack("!BBH", packet[:4])
    if ident != (identifier & 0xFF) or length != len(packet) or code not in (DISCONNECT_ACK, DISCONNECT_NAK):
        return None
    expected = hashlib.md5(packet[:4] + request_auth + packet[20:length] + secret).digest()  # noqa: S324
    return code if hmac.compare_digest(expected, packet[4:20]) else None


def build_response(code: int, identifier: int, request_auth: bytes, secret: bytes, attrs: bytes = b"") -> bytes:
    """Used by tests (a fake NAS)."""
    length = 20 + len(attrs)
    header = struct.pack("!BBH", code, identifier & 0xFF, length)
    return header + hashlib.md5(header + request_auth + attrs + secret).digest() + attrs  # noqa: S324


@dataclass
class CoaResult:
    outcome: str  # ACK | NAK | TIMEOUT | ERROR
    error_cause: Optional[int] = None


def send_disconnect(host: str, port: int, secret: bytes, *, username: str, session_id: Optional[str] = None,
                    timeout: float = 3.0, retries: int = 2) -> CoaResult:
    """Blocking. `host` must be an IP literal (the NAS client's registered address)."""
    ip = ipaddress.ip_address(host)
    ident = os.urandom(1)[0]
    nas_ip = str(ip) if ip.version == 4 else None
    packet = build_disconnect_request(secret, ident, username=username, nas_ip=nas_ip, session_id=session_id)
    req_auth = request_authenticator(packet)
    family = socket.AF_INET if ip.version == 4 else socket.AF_INET6
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        for _ in range(retries + 1):
            try:
                sock.sendto(packet, (str(ip), port))
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return CoaResult("ERROR")
            if addr[0] != str(ip):
                continue
            code = verify_response(data, req_auth, ident, secret)
            if code is None:
                return CoaResult("ERROR")
            cause = None
            pos = 20
            while pos + 2 <= len(data):
                t, ln = data[pos], data[pos + 1]
                if ln < 2:
                    break
                if t == ATTR_ERROR_CAUSE and ln == 6:
                    cause = struct.unpack("!I", data[pos + 2:pos + 6])[0]
                pos += ln
            return CoaResult("ACK" if code == DISCONNECT_ACK else "NAK", cause)
    return CoaResult("TIMEOUT")
