"""privacy.py - the wall between PRIVATE conversations and the PUBLIC wall.

Two classes of data, and the rule between them is code, not a promise:

  PRIVATE  direct messages, group chats, live room sessions (and the signalling that sets them up).
           Never collected, never scraped, never shown on a public feed, never synced to GitHub, never counted for ranks, never part of telemetry.
  PUBLIC   public posts and public comments: things a person chose to share on the public wall. Only these may feed the public wall, the GitHub sync and the ranking ledger.

Every public path (public wall, GitHub sync, ranking) takes its input through `require_public()` / `public_only()`. A private item raises PrivacyViolation; it is never silently dropped into a feed.
The private stores live in their own folder (PRIVATE_DIR) that no public module is allowed to read; test_privacy.py fails if a public module mentions a private kind or that folder, or if the telemetry
schema ever gains a content field.

Honest status: Platform has no direct messages or group chats yet and live rooms are built as peer-to-peer (nothing recorded or stored). This module is the rule those features must follow when they exist.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PRIVATE_DIR = os.path.join(HERE, "nexxus_data", "private")          # future home of DM / group chat stores; no public module may read it

PRIVATE_KINDS = frozenset({"direct_message", "group_chat", "room_session", "room_signal"})
PUBLIC_KINDS = frozenset({"public_post", "public_comment"})

PRIVATE_STATEMENT = ("Your private conversations stay private. Direct messages, group chats and live rooms are never collected, never scraped, never shown on the public wall, "
                     "never synced to GitHub, and never counted toward ranks. Only what you choose to make public can appear on the public wall.")


class PrivacyViolation(Exception):
    """A private item tried to enter a public path."""


def is_private(item):
    return isinstance(item, dict) and (item.get("kind") in PRIVATE_KINDS or item.get("visibility") == "private" and item.get("kind") not in PUBLIC_KINDS)


def is_public(item):
    return isinstance(item, dict) and item.get("kind") in PUBLIC_KINDS and item.get("visibility") == "public"


def require_public(item, purpose="a public path"):
    """Return the item if it is public, else raise. Use at the entrance of anything that publishes, syncs or ranks."""
    if is_private(item):
        raise PrivacyViolation("a private item was offered to %s" % purpose)
    if not is_public(item):
        raise PrivacyViolation("an item that is not marked public was offered to %s" % purpose)
    return item


def public_only(items, purpose="a public path"):
    """Keep only public items; private ones raise (so a bug cannot quietly publish a conversation), unmarked ones are skipped."""
    out = []
    for it in items:
        if is_private(it):
            raise PrivacyViolation("a private item was offered to %s" % purpose)
        if is_public(it):
            out.append(it)
    return out


def as_public_post(post):
    """A floor post that its owner marked public, in the shape the public paths take. Never carries ratings or private fields."""
    return {"kind": "public_post", "visibility": "public", "id": post["id"], "t": post.get("t", 0), "text": post.get("text", ""), "url": post.get("url", ""),
            "media": post.get("media", ""), "gh": post.get("gh") or None}


def as_public_comment(post_id, c):
    return {"kind": "public_comment", "visibility": "public", "id": c["id"], "post_id": post_id, "t": c.get("t", 0), "text": c.get("text", ""),
            "author": c.get("author") or "you", "source": c.get("source") or "local", "url": c.get("url", ""), "pushed": bool(c.get("pushed"))}
