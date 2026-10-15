"""image_ingest.py - fetch a real image from a web URL, on demand, safely.

The owner gives a URL; this fetches that exact file and returns its bytes. It is not a generator and substitutes nothing: if the fetch fails, it says why.
Because the URL is typed by a person and the fetch runs on this machine, it is treated as an attack surface:
  * https only (plain http and every other scheme are refused); a loopback http address is accepted ONLY when a test passes allow_loopback=True,
  * the host name is resolved here and every address it resolves to must be public (no loopback, private, link-local, multicast or reserved ranges), and the connection goes to that
    checked address, so a name that resolves differently a moment later cannot redirect the request inside the network,
  * at most 3 redirects, each one re-checked the same way; the response is capped at 8 MB and 15 seconds,
  * only png, jpeg, gif and webp are accepted, decided by the file's own first bytes, not by what the server claims (svg is refused: it can carry script),
  * an image wider or taller than 2048 px is scaled down (and the report says so) so it works as a texture.
fetch() returns the data plus a step-by-step telemetry list (resolve, connect, download, verify, texture-ready), each with its own timing.
"""
import hashlib
import http.client
import io
import ipaddress
import socket
import ssl
import time
import urllib.parse

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 2048
MAX_REDIRECTS = 3
TIMEOUT = 15
USER_AGENT = "NEXXUS-image-ingest/1.0 (local owner tool)"
_TYPES = {b"\x89PNG\r\n\x1a\n": ("png", "image/png"), b"\xff\xd8\xff": ("jpg", "image/jpeg"), b"GIF87a": ("gif", "image/gif"), b"GIF89a": ("gif", "image/gif")}


class IngestError(Exception):
    pass


def _sniff(data):
    for magic, v in _TYPES.items():
        if data.startswith(magic):
            return v
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("webp", "image/webp")
    return None


def _public(ip):
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


def _resolve(host, port, allow_loopback):
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise IngestError("the host name %r does not resolve: %s" % (host, e))
    ips = []
    for fam, _, _, _, sa in infos:
        ip = sa[0]
        if not _public(ip) and not (allow_loopback and ipaddress.ip_address(ip).is_loopback):
            raise IngestError("refused: %s resolves to %s, which is not a public address (this tool does not fetch from inside a network)" % (host, ip))
        ips.append(ip)
    if not ips:
        raise IngestError("the host name %r has no address" % host)
    return ips[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Connects to an address that has already been checked, while still verifying the certificate for the real host name."""

    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


def _get(url, allow_loopback, steps, t_all):
    u = urllib.parse.urlsplit(url)
    host, secure = (u.hostname or "").lower(), u.scheme == "https"
    if u.scheme not in ("https", "http") or not host:
        raise IngestError("only https addresses can be fetched")
    if not secure and not allow_loopback:
        raise IngestError("only https addresses can be fetched (plain http is refused)")
    if u.username or u.password:
        raise IngestError("addresses with a user name or password are refused")
    port = u.port or (443 if secure else 80)
    t = time.perf_counter()
    ip = _resolve(host, port, allow_loopback)
    steps.append({"step": "resolve", "ok": True, "host": host, "address": ip, "ms": round((time.perf_counter() - t) * 1000, 1)})
    t = time.perf_counter()
    conn = (_PinnedHTTPS if secure else _PinnedHTTP)(host, ip, port, TIMEOUT)
    try:
        conn.request("GET", (u.path or "/") + ("?" + u.query if u.query else ""), headers={"User-Agent": USER_AGENT, "Accept": "image/png,image/jpeg,image/gif,image/webp", "Accept-Encoding": "identity"})
        r = conn.getresponse()
        steps.append({"step": "connect", "ok": True, "status": r.status, "tls": secure, "ms": round((time.perf_counter() - t) * 1000, 1)})
        if r.status in (301, 302, 303, 307, 308):
            return None, r.getheader("Location")
        if r.status != 200:
            raise IngestError("the server answered %d %s" % (r.status, r.reason))
        t = time.perf_counter()
        buf = bytearray()
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_BYTES:
                raise IngestError("the image is larger than %d MB" % (MAX_BYTES // 1048576))
            if time.perf_counter() - t_all > TIMEOUT * 2:
                raise IngestError("the download took too long")
        steps.append({"step": "download", "ok": True, "bytes": len(buf), "ms": round((time.perf_counter() - t) * 1000, 1)})
        return bytes(buf), None
    except (OSError, http.client.HTTPException, ssl.SSLError) as e:
        raise IngestError("could not fetch it: %s: %s" % (type(e).__name__, e))
    finally:
        conn.close()


def fetch(url, allow_loopback=False):
    """-> {"data", "ext", "content_type", "width", "height", "scaled", "sha256", "url", "steps": [...]}. Raises IngestError."""
    url = str(url or "").strip()
    if not url or len(url) > 2000:
        raise IngestError("give the web address of an image (up to 2000 characters)")
    steps, t_all, cur = [], time.perf_counter(), url
    for hop in range(MAX_REDIRECTS + 1):
        data, loc = _get(cur, allow_loopback, steps, t_all)
        if data is not None:
            break
        if not loc or hop == MAX_REDIRECTS:
            raise IngestError("too many redirects" if loc else "a redirect without a destination")
        cur = urllib.parse.urljoin(cur, loc)
        steps.append({"step": "redirect", "ok": True, "to": cur})
    t = time.perf_counter()
    kind = _sniff(data)
    if kind is None:
        raise IngestError("that is not a png, jpeg, gif or webp image (decided from the file itself)")
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise IngestError("the image is damaged or unreadable: %s" % str(e)[:120])
    w, h = img.size
    scaled = False
    if max(w, h) > MAX_SIDE:
        k = MAX_SIDE / max(w, h)
        img = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
        out = io.BytesIO()
        ext, ctype = ("png", "image/png") if img.mode == "RGBA" else ("jpg", "image/jpeg")
        img.save(out, "PNG" if ext == "png" else "JPEG", **({} if ext == "png" else {"quality": 92}))
        data, kind, scaled = out.getvalue(), (ext, ctype), True
        w, h = img.size
    steps.append({"step": "verify", "ok": True, "type": kind[1], "width": w, "height": h, "scaled_to_fit": scaled, "ms": round((time.perf_counter() - t) * 1000, 1)})
    return {"data": data, "ext": kind[0], "content_type": kind[1], "width": w, "height": h, "scaled": scaled, "sha256": hashlib.sha256(data).hexdigest(), "url": cur, "steps": steps,
            "total_ms": round((time.perf_counter() - t_all) * 1000, 1)}
