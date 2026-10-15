"""youtube_adapter.py - the YouTube Data API v3, used only on the owner's own authorised channel.

What this can and cannot do, stated plainly:
  * It CANNOT create a YouTube channel. The API has no call for it: a channel is created once, by the account owner, in YouTube Studio. channel() therefore VERIFIES that the authorised
    account has a channel and says exactly what to do when it does not.
  * It CANNOT authorise itself. The owner creates an OAuth client in Google Cloud and completes Google's consent screen once; the resulting access token is supplied in the environment
    (NEXXUS_YT_ACCESS_TOKEN). NEXXUS never asks for, stores or types a password, and the token is read at call time and never written to a log, a ledger or an error message.
  * It uploads with privacyStatus "private" unless the caller asks for more (publish_queue.py only asks after the owner approves and, for "public", confirms separately).
  * Google applies its own limits and policies (a quota cost per upload, and, as I understand it, uploads from API projects that have not passed Google's audit are locked to private).
    Check the current rules in Google's documentation: this module does not work around them.
Loopback URLs (http://127.0.0.1) are accepted only so the tests can use a local stand-in server; every real call goes to https.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://www.googleapis.com"
TIMEOUT_S = 120
MAX_UPLOAD_BYTES = 25 * 1024 * 1024             # the Creations hub's own file limit; larger renders are refused before anything is sent
PRIVACY = ("private", "unlisted", "public")


class YouTubeError(Exception):
    pass


def base():
    b = (os.environ.get("NEXXUS_YT_API_BASE") or API_BASE).rstrip("/")
    host = urllib.parse.urlparse(b)
    if host.scheme != "https" and not (host.scheme == "http" and host.hostname in ("127.0.0.1", "localhost", "::1")):
        raise YouTubeError("the YouTube API address must be https (loopback http is allowed for tests only)")
    return b


def _token():
    t = (os.environ.get("NEXXUS_YT_ACCESS_TOKEN") or "").strip()
    if not t:
        raise YouTubeError("no access token: complete Google's OAuth consent once as the channel owner and put the resulting access token in NEXXUS_YT_ACCESS_TOKEN. NEXXUS cannot authorise itself.")
    return t


def _call(method, url, headers=None, body=None):
    h = {"Authorization": "Bearer " + _token(), "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()[:2000].decode("utf-8", "replace")
        try:
            msg = json.loads(raw).get("error", {}).get("message") or raw
        except ValueError:
            msg = raw
        raise YouTubeError("YouTube answered HTTP %d: %s" % (e.code, str(msg).replace(_token(), "[token]")[:300]))
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise YouTubeError("could not reach YouTube (%s)" % type(getattr(e, "reason", e)).__name__)


def channel():
    """The authorised account's own channel -> {id, title, ...}. Raises with the owner's next step when the account has none."""
    _s, _h, raw = _call("GET", base() + "/youtube/v3/channels?part=snippet,statistics,brandingSettings&mine=true")
    items = (json.loads(raw.decode("utf-8")) or {}).get("items") or []
    if not items:
        raise YouTubeError("this Google account has no YouTube channel. The API cannot create one: open YouTube Studio signed in as the owner, create the channel once, then try again.")
    c = items[0]
    return {"id": c.get("id"), "title": (c.get("snippet") or {}).get("title"), "videos": (c.get("statistics") or {}).get("videoCount"), "branding": c.get("brandingSettings") or {}}


def configure_channel(channel_id, description=None, keywords=None, country=None):
    """Update the channel's description, keywords and country (read, merge, write: the API replaces the whole brandingSettings.channel block)."""
    cur = channel()
    if cur["id"] != channel_id:
        raise YouTubeError("that is not the authorised account's channel")
    chan = dict((cur["branding"] or {}).get("channel") or {})
    if description is not None:
        chan["description"] = str(description)[:1000]
    if keywords is not None:
        chan["keywords"] = " ".join('"%s"' % k if " " in k else k for k in [str(x).strip() for x in keywords if str(x).strip()])[:500]
    if country is not None:
        chan["country"] = str(country)[:2].upper()
    body = json.dumps({"id": channel_id, "brandingSettings": {"channel": chan}}).encode("utf-8")
    _call("PUT", base() + "/youtube/v3/channels?part=brandingSettings", {"Content-Type": "application/json"}, body)
    return {"id": channel_id, "updated": sorted(k for k, v in (("description", description), ("keywords", keywords), ("country", country)) if v is not None)}


def upload(path, title, description="", tags=(), privacy="private"):
    """Resumable upload of one video file. -> {video_id, url, privacy}. The file is read here and sent as is."""
    if privacy not in PRIVACY:
        raise YouTubeError("privacy must be one of %s" % ", ".join(PRIVACY))
    size = os.path.getsize(path)
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise YouTubeError("the video must be between 1 byte and %d MB" % (MAX_UPLOAD_BYTES // 1024 ** 2))
    ext = os.path.splitext(path)[1].lower()
    ctype = {".mp4": "video/mp4", ".webm": "video/webm"}.get(ext)
    if not ctype:
        raise YouTubeError("only .mp4 and .webm files are uploaded")
    meta = {"snippet": {"title": str(title)[:100], "description": str(description)[:5000], "tags": [str(t)[:30] for t in tags][:30]}, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    _s, hdr, _b = _call("POST", base() + "/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                        {"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": ctype, "X-Upload-Content-Length": str(size)}, json.dumps(meta).encode("utf-8"))
    loc = next((v for k, v in hdr.items() if k.lower() == "location"), None)
    if not loc:
        raise YouTubeError("YouTube did not return an upload address")
    if urllib.parse.urlparse(loc).netloc != urllib.parse.urlparse(base()).netloc:
        raise YouTubeError("YouTube returned an upload address on another host: refused")
    with open(path, "rb") as f:
        data = f.read()
    _s, _h, raw = _call("PUT", loc, {"Content-Type": ctype, "Content-Length": str(len(data))}, data)
    vid = (json.loads(raw.decode("utf-8")) or {}).get("id")
    if not vid:
        raise YouTubeError("YouTube accepted the upload but returned no video id")
    return {"video_id": vid, "url": "https://www.youtube.com/watch?v=" + vid, "privacy": privacy}
