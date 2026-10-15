"""github_sync.py - anchor public posts and their comments to this repository's GitHub Discussions, for a transparent, verifiable audit trail.

How it works
  * A post becomes a GitHub Discussion only when its owner has marked it PUBLIC and then confirms publishing it, one post at a time, after seeing exactly what will be posted. Nothing is ever sent automatically.
  * Comments from other people on that Discussion are pulled back and shown under the post on the public wall (their GitHub login and a link to the comment are kept: it is public information).
  * A comment you wrote on a mirrored post is posted to GitHub only when you press "Post to GitHub" on that comment and confirm.
  * Only PUBLIC items can enter this module (privacy.py raises otherwise). Direct messages, group chats and live rooms never can.

What it needs: NEXXUS_GITHUB_TOKEN in the environment (for example `gh auth token`), with permission to use Discussions on the repository; Discussions turned on for it. The token is read from the
environment on each call and is never saved, logged or returned. Photos are not uploaded (the API cannot take them); a mirrored photo post carries its text and says the photo stays with the author.

Honest limits: a Discussion on GitHub cannot be fully unpublished by this app (delete it on GitHub; GitHub may keep cached copies), so a mirrored post cannot be switched back to private here.
"""
import json
import os
import urllib.request

import privacy

API = "https://api.github.com/graphql"
DEFAULT_REPO = "jamalemccarthy3-dev/axis-bridge"
DEFAULT_CATEGORY = "Show and tell"
FOOTER = "\n\n---\n_Shared from NEXXUS Platform. Photos stay on the author's computer. Keep it PG-13: see the [Code of Conduct](https://github.com/%s/blob/main/CODE_OF_CONDUCT.md)._"


class GitHubError(Exception):
    pass


def repo():
    r = os.environ.get("NEXXUS_GITHUB_REPO", DEFAULT_REPO).strip()
    return r if r.count("/") == 1 and all(r.split("/")) else DEFAULT_REPO


def category():
    return os.environ.get("NEXXUS_DISCUSSION_CATEGORY", DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY


def configured():
    return bool(os.environ.get("NEXXUS_GITHUB_TOKEN", "").strip())


def _default_transport(query, variables):
    token = os.environ.get("NEXXUS_GITHUB_TOKEN", "").strip()
    if not token:
        raise GitHubError("Set NEXXUS_GITHUB_TOKEN first (for example from `gh auth token`).")
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables}).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "nexxus-platform"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read(2_000_000))
    except Exception as e:                                           # the message never includes the token
        raise GitHubError("Could not reach GitHub: " + type(e).__name__)


def _call(query, variables, transport):
    out = (transport or _default_transport)(query, variables)
    if not isinstance(out, dict) or out.get("errors"):
        msg = (out.get("errors") or [{}])[0].get("message", "unknown error") if isinstance(out, dict) else "bad reply"
        raise GitHubError("GitHub refused: " + str(msg)[:200])
    return out.get("data") or {}


def preview(post):
    """Exactly what would be posted, so the owner can read it before confirming. Raises PrivacyViolation if the post is not public."""
    if post.get("kind") in privacy.PUBLIC_KINDS:
        p = privacy.require_public(post, "the GitHub sync")
    elif post.get("public") is True:
        p = privacy.require_public(privacy.as_public_post(post), "the GitHub sync")
    else:
        raise privacy.PrivacyViolation("a post that is not marked public was offered to the GitHub sync")
    first = (p["text"].strip().splitlines() or [""])[0].strip()
    title = (first[:80] or "A photo from NEXXUS Platform").strip()
    body = (p["text"].strip() or "(a photo post: the photo stays with the author)") + (FOOTER % repo())
    return {"title": title, "body": body, "repo": repo(), "category": category()}


def publish_post(post, transport=None):
    """Create the Discussion. -> {"id","number","url"}."""
    pv = preview(post)
    owner, name = repo().split("/")
    info = _call("query($o:String!,$n:String!){repository(owner:$o,name:$n){id hasDiscussionsEnabled discussionCategories(first:25){nodes{id name}}}}", {"o": owner, "n": name}, transport)["repository"]
    if not info or not info.get("hasDiscussionsEnabled"):
        raise GitHubError("Discussions are not turned on for %s." % repo())
    cat = next((c for c in info["discussionCategories"]["nodes"] if c["name"].lower() == category().lower()), None)
    if not cat:
        raise GitHubError("The Discussions category '%s' does not exist on %s." % (category(), repo()))
    d = _call("mutation($i:CreateDiscussionInput!){createDiscussion(input:$i){discussion{id number url}}}",
              {"i": {"repositoryId": info["id"], "categoryId": cat["id"], "title": pv["title"], "body": pv["body"]}}, transport)["createDiscussion"]["discussion"]
    return {"id": d["id"], "number": d["number"], "url": d["url"]}


def viewer_login(transport=None):
    return _call("query{viewer{login}}", {}, transport)["viewer"]["login"]


def pull_comments(discussion_id, transport=None):
    """Public comments on a mirrored Discussion -> [{"id","author","text","url","t"}]."""
    node = _call("query($id:ID!){node(id:$id){... on Discussion{comments(first:100){nodes{id body url createdAt author{login}}}}}}", {"id": discussion_id}, transport).get("node") or {}
    out = []
    for c in ((node.get("comments") or {}).get("nodes") or []):
        out.append({"id": c["id"], "author": (c.get("author") or {}).get("login") or "ghost", "text": str(c.get("body", ""))[:2000], "url": c.get("url", ""), "created": c.get("createdAt", "")})
    return out


def push_comment(discussion_id, comment, transport=None):
    """Post one PUBLIC local comment to the Discussion. -> {"id","url"}."""
    c = privacy.require_public(comment, "the GitHub sync")
    r = _call("mutation($i:AddDiscussionCommentInput!){addDiscussionComment(input:$i){comment{id url}}}", {"i": {"discussionId": discussion_id, "body": c["text"]}}, transport)["addDiscussionComment"]["comment"]
    return {"id": r["id"], "url": r["url"]}
