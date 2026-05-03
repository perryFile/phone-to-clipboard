"""LAN IP discovery — picks the first non-loopback IPv4 address."""
import socket
from typing import Optional


def get_lan_ip() -> Optional[str]:
    """Return the LAN IPv4 address this machine uses to reach the local network.

    Works by opening a UDP socket toward a public address (no packets actually
    sent) to let the OS pick the correct outgoing interface, then reads the
    local address.  Falls back to iterating ``getaddrinfo`` if that fails.
    """
    # Primary method: UDP routing trick
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0)
            sock.connect(("10.254.254.254", 1))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    # Fallback: hostname resolution
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return None


def get_mdns_hostname() -> Optional[str]:
    """Return a best-effort mDNS hostname like '<host>.local'.

    This gives users a stable URL that often survives DHCP IP changes
    when both devices stay on local networks that support mDNS.
    """
    try:
        host = socket.gethostname().strip().strip(".")
    except Exception:
        return None

    if not host:
        return None

    lowered = host.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return None

    if lowered.endswith(".local"):
        return host

    return f"{host}.local"


def is_public_ip(ip: str) -> bool:
    """Return True if *ip* is a public (routable) address, False for RFC-1918."""
    try:
        packed = socket.inet_aton(ip)
        a = packed[0]
        b = packed[1]
        # 10.x.x.x
        if a == 10:
            return False
        # 172.16.x.x – 172.31.x.x
        if a == 172 and 16 <= b <= 31:
            return False
        # 192.168.x.x
        if a == 192 and b == 168:
            return False
        # 127.x.x.x
        if a == 127:
            return False
        # 169.254.x.x (link-local)
        if a == 169 and b == 254:
            return False
    except Exception:
        return True
    return True
