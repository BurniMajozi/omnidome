"""Render /etc/asterisk from templates + environment. FAILS CLOSED: any missing/weak/invalid value aborts
the container before Asterisk starts. Values are validated against strict patterns so an env typo can
never inject config.

Required: ASTERISK_ARI_PASSWORD (>=24 chars), ASTERISK_ADMIN_TOKEN (>=32 chars)
Optional: ASTERISK_ARI_USER (omnidome), ASTERISK_ARI_APP (omnidome), ASTERISK_RTP_START/END (10000/10100),
          ASTERISK_EXTERNAL_IP (public IPv4 of the VPS), ASTERISK_LOCAL_NET (comma CIDRs),
          ASTERISK_STUN_SERVER (host:port), ASTERISK_TLS_CERT / ASTERISK_TLS_KEY (enables SIP TLS on 5061)
"""
import ipaddress
import os
import re
import string
import sys
from pathlib import Path

TEMPLATES = Path("/opt/omnidome/templates")
OUT = Path(os.getenv("ASTERISK_CONF_DIR", "/etc/asterisk"))
TOKEN = re.compile(r"[A-Za-z0-9._~-]+")
NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}")
HOSTPORT = re.compile(r"[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?")


def die(msg):
    sys.stderr.write(f"asterisk entrypoint: {msg}\n")
    sys.exit(78)


def need_secret(name, min_len):
    v = os.environ.get(name, "")
    if not v:
        die(f"{name} is not set; refusing to start (generate one: openssl rand -hex 24)")
    if len(v) < min_len or not TOKEN.fullmatch(v):
        die(f"{name} must be at least {min_len} chars of [A-Za-z0-9._~-]")
    return v


def get_name(name, default):
    v = os.environ.get(name, default)
    if not NAME.fullmatch(v):
        die(f"{name} has unsupported characters")
    return v


def get_port(name, default):
    try:
        p = int(os.environ.get(name, default))
    except ValueError:
        die(f"{name} must be a number")
    if not 1024 <= p <= 65535:
        die(f"{name} out of range")
    return p


def main():
    ari_pw = need_secret("ASTERISK_ARI_PASSWORD", 24)
    need_secret("ASTERISK_ADMIN_TOKEN", 32)
    rtp_start = get_port("ASTERISK_RTP_START", 10000)
    rtp_end = get_port("ASTERISK_RTP_END", 10100)
    if rtp_end <= rtp_start or rtp_end - rtp_start > 2000:
        die("invalid RTP port range")
    nat = []
    ext = os.environ.get("ASTERISK_EXTERNAL_IP", "").strip()
    if ext:
        try:
            ip = ipaddress.IPv4Address(ext)
        except ValueError:
            die("ASTERISK_EXTERNAL_IP must be an IPv4 address")
        nat.append(f"external_media_address={ip}")
        nat.append(f"external_signaling_address={ip}")
        for cidr in filter(None, (c.strip() for c in os.environ.get("ASTERISK_LOCAL_NET", "172.16.0.0/12,10.0.0.0/8,192.168.0.0/16").split(","))):
            try:
                nat.append(f"local_net={ipaddress.IPv4Network(cidr, strict=False)}")
            except ValueError:
                die("ASTERISK_LOCAL_NET must be comma-separated IPv4 CIDRs")
    stun = os.environ.get("ASTERISK_STUN_SERVER", "").strip()
    if stun and not HOSTPORT.fullmatch(stun):
        die("ASTERISK_STUN_SERVER must be host[:port]")
    tls_block = ""
    cert, key = os.environ.get("ASTERISK_TLS_CERT", ""), os.environ.get("ASTERISK_TLS_KEY", "")
    if cert or key:
        if not (cert.startswith("/") and key.startswith("/") and TOKEN.fullmatch(cert.replace("/", "")) and TOKEN.fullmatch(key.replace("/", ""))):
            die("ASTERISK_TLS_CERT / ASTERISK_TLS_KEY must be absolute file paths")
        if not (Path(cert).is_file() and Path(key).is_file()):
            die("TLS certificate or key file not found")
        tls_block = ("[transport-tls]\ntype=transport\nprotocol=tls\nbind=0.0.0.0:5061\n"
                     f"cert_file={cert}\npriv_key_file={key}\nmethod=tlsv1_2\n" + "\n".join(nat) + "\n")
    values = {
        "ARI_USER": get_name("ASTERISK_ARI_USER", "omnidome"),
        "ARI_APP": get_name("ASTERISK_ARI_APP", "omnidome"),
        "ARI_PASSWORD": ari_pw,
        "RTP_START": rtp_start, "RTP_END": rtp_end,
        "STUN_LINE": f"stunaddr={stun}" if stun else "; stunaddr not set (set ASTERISK_STUN_SERVER on a VPS)",
        "NAT_LINES": "\n".join(nat) if nat else "; no external address (local/NAT lab: trunk media will not work)",
        "TLS_TRANSPORT": tls_block,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    for tpl in sorted(TEMPLATES.glob("*.conf")):
        text = string.Template(tpl.read_text()).substitute(values)
        dest = OUT / tpl.name
        dest.write_text(text)
        os.chmod(dest, 0o640)
    (OUT / "generated").mkdir(exist_ok=True)
    os.system(f"chown -R asterisk:asterisk {OUT} 2>/dev/null")


if __name__ == "__main__":
    main()
