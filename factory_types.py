"""factory_types.py - the dashboard type registry and the isolated workspaces behind it.

A dashboard TYPE says what can be built (its configuration fields and its generator). An INSTANCE is one thing built from a type, in its own folder, from its own validated configuration.
Types never share state:
  * the built-in types (micro company, platform factory, spatial environment, publishing pipeline) are read-only; every read returns a copy, so nothing can edit them by accident,
  * each instance lives in factory/<type>/<id>/ and only ever reads and writes there (paths are resolved and checked against that folder),
  * a CUSTOM type is a name, a set of bespoke fields and (optionally) the generator it builds with. It adds its own fields; it cannot change a built-in type, cannot reuse a built-in key and
    cannot see another custom type's instances.
No data lives in this module: a type is a contract, an instance holds only what its owner entered.
"""
import json
import math
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

ENGINES = ("platform_factory", "spatial_environment", "micro_company", "publishing_pipeline")
MAX_CUSTOM_TYPES = 40
MAX_FIELDS = 24
KINDS = ("text", "textarea", "number", "choice", "list", "color", "json", "toggle")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class FactoryError(Exception):
    pass


def F(name, label, kind="text", required=False, help="", **extra):
    d = {"name": name, "label": label, "kind": kind, "required": required, "help": help}
    d.update(extra)
    return d


# ---- the built-in types: contracts only, no values ----
BUILTIN = {
    "micro_company": {
        "title": "Micro-company", "engine": "micro_company",
        "summary": "A small autonomous operation: bots that run named tasks on a schedule and route each result to the next bot. Tasks are real (health checks, creation jobs, publish staging, owner-approved webhooks, reports).",
        "fields": [F("company", "Company name", required=True, max=80), F("purpose", "What it does", "textarea", max=600),
                   F("bots", "Bots", "json", required=True, help='a list of {"name","task","params","every_s","then"}; tasks: health_check, creation_job, publish_stage, channel_check, webhook, report'),
                   F("webhook_allow", "Allowed webhook hosts", "list", help="https hosts the webhook task may call; empty means no outbound webhook at all")]},
    "platform_factory": {
        "title": "Platform factory", "engine": "platform_factory",
        "summary": "A branded website or storefront built from your brand, your copy and the live assets in the Creations hub. Orders are stored locally; no payment is taken.",
        "fields": [F("brand", "Brand name", required=True, max=60), F("tagline", "Tagline", max=140), F("accent", "Accent colour", "color"), F("kind", "Kind", "choice", required=True, choices=["site", "storefront"]),
                   F("about", "About text", "textarea", max=2000),
                   F("products", "Products", "json", help='storefront only: a list of {"name","price","description","asset"} where asset is a Creations hub id')]},
    "spatial_environment": {
        "title": "Spatial environment", "engine": "spatial_environment",
        "summary": "An interactive 3D space that runs in the browser: staged objects, lights, simple physics (gravity, collisions) and real-time first-person navigation (Babylon.js, served locally).",
        "fields": [F("title", "Title", required=True, max=80), F("ground", "Ground size (metres)", "number", min=4, max=500), F("gravity", "Gravity (m/s2)", "number", min=0, max=30),
                   F("objects", "Objects", "json", required=True, help='a list of {"shape": box|sphere|cylinder, "position":[x,y,z], "size":[..], "color":"#hex", "dynamic": bool, "mass": n}'),
                   F("lights", "Lights", "json", help='a list of {"type": hemispheric|directional|point, "intensity": n, "color":"#hex", "position":[x,y,z]}'),
                   F("player", "Player", "json", help='{"start":[x,y,z], "speed": n, "height": n}')]},
    "publishing_pipeline": {
        "title": "Publishing pipeline", "engine": "publishing_pipeline",
        "summary": "Topic in, video out, queue staged: creation job, finished video into the Creations hub, then staged for YouTube. Approval is yours; the channel is created by you in YouTube Studio (the API cannot).",
        "fields": [F("topic", "Topic", required=True, max=120), F("brief", "Video brief", "textarea", required=True, max=1200), F("title", "Video title", required=True, max=100), F("tags", "Tags", "list"),
                   F("every_s", "Check every (seconds)", "number", min=300, max=604800)]},
}


def _atomic(path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def check_value(field, value, path=""):
    """-> (clean value, error or None). One field of a configuration against its contract."""
    k, label = field["kind"], field["label"]
    if value is None or value == "" or value == []:
        return None, ("%s is required" % label) if field.get("required") else None
    if k in ("text", "textarea"):
        if not isinstance(value, str) or _CTRL.search(value):
            return None, "%s must be plain text" % label
        if len(value) > field.get("max", 4000):
            return None, "%s is longer than %d characters" % (label, field.get("max", 4000))
        return value.strip(), None
    if k == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None, "%s must be a number" % label
        if "min" in field and value < field["min"] or "max" in field and value > field["max"]:
            return None, "%s must be between %s and %s" % (label, field.get("min", "-inf"), field.get("max", "inf"))
        return value, None
    if k == "choice":
        return (value, None) if value in field.get("choices", []) else (None, "%s must be one of %s" % (label, ", ".join(field.get("choices", []))))
    if k == "color":
        return (value, None) if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else (None, "%s must be a colour like #1e90ff" % label)
    if k == "toggle":
        return (value, None) if isinstance(value, bool) else (None, "%s must be true or false" % label)
    if k == "list":
        if not isinstance(value, list) or len(value) > 200 or not all(isinstance(x, str) and 0 < len(x) <= 200 and not _CTRL.search(x) for x in value):
            return None, "%s must be a list of up to 200 short texts" % label
        return value, None
    if k == "json":
        try:
            if len(json.dumps(value)) > 400_000:
                return None, "%s is larger than 400 KB" % label
        except (TypeError, ValueError):
            return None, "%s must be valid JSON" % label
        return value, None
    return None, "unknown field kind %r" % k


class Factory:
    def __init__(self, root, now=time.time):
        self.root, self.now = Path(root), now
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._custom_file = self.root / "custom_types.json"
        self._custom = {}
        if self._custom_file.is_file():
            try:
                self._custom = json.loads(self._custom_file.read_text(encoding="utf-8")).get("types", {})
            except (OSError, ValueError):
                self._custom_file.replace(self._custom_file.with_suffix(".corrupt-%d" % int(now())))        # never overwrite what could not be read

    # ---- types ----
    def types(self):
        """Every type, built-in first, as copies: nothing a caller does to the result can change a type."""
        out = {k: json.loads(json.dumps(dict(v, builtin=True, key=k))) for k, v in BUILTIN.items()}
        for k, v in self._custom.items():
            out[k] = json.loads(json.dumps(dict(v, builtin=False, key=k)))
        return out

    def type(self, key):
        t = self.types().get(key)
        if t is None:
            raise FactoryError("no such dashboard type %r" % key)
        return t

    def define_custom(self, key, title, summary, fields, engine="none"):
        """A brand-new type: its own name, its own fields, and (optionally) the generator it builds with. It extends; it never edits a built-in."""
        key = "custom_" + re.sub(r"^custom_", "", re.sub(r"[^a-z0-9_]+", "_", str(key or "").strip().lower()).strip("_"))
        if not _SLUG.match(key) or len(key) > 40:
            raise FactoryError("the type key must be 2 to 32 lowercase letters, digits or underscores")
        if key in BUILTIN:
            raise FactoryError("that key belongs to a built-in type")
        title, summary = str(title or "").strip(), str(summary or "").strip()
        if not title or len(title) > 60 or _CTRL.search(title):
            raise FactoryError("a custom type needs a title of up to 60 characters")
        if len(summary) > 400 or _CTRL.search(summary):
            raise FactoryError("the summary is up to 400 characters of plain text")
        if engine != "none" and engine not in ENGINES:
            raise FactoryError("engine must be none or one of %s" % ", ".join(ENGINES))
        if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
            raise FactoryError("define 1 to %d fields" % MAX_FIELDS)
        clean, seen = [], set()
        for i, f in enumerate(fields):
            if not isinstance(f, dict) or not _SLUG.match(str(f.get("name", ""))) or f.get("kind") not in KINDS:
                raise FactoryError("field %d needs a name (letters, digits, underscore) and a kind (%s)" % (i + 1, ", ".join(KINDS)))
            if f["name"] in seen:
                raise FactoryError("field %r appears twice" % f["name"])
            seen.add(f["name"])
            lab = str(f.get("label") or f["name"]).strip()[:60]
            nf = F(f["name"], lab, f["kind"], bool(f.get("required")), str(f.get("help") or "")[:200])
            if f["kind"] == "choice":
                ch = f.get("choices")
                if not isinstance(ch, list) or not 2 <= len(ch) <= 30 or not all(isinstance(c, str) and 0 < len(c) <= 40 for c in ch):
                    raise FactoryError("field %r needs 2 to 30 short choices" % f["name"])
                nf["choices"] = ch
            for lim in ("min", "max"):
                if isinstance(f.get(lim), (int, float)) and not isinstance(f.get(lim), bool):
                    nf[lim] = f[lim]
            clean.append(nf)
        if engine != "none":                                                  # the custom type must still satisfy its generator: same names, same kinds
            need = {f["name"]: f for f in BUILTIN[engine]["fields"] if f["required"]}
            for n, bf in need.items():
                cf = next((c for c in clean if c["name"] == n), None)
                if cf is None or cf["kind"] != bf["kind"]:
                    raise FactoryError("built with %s, this type must include the field %r (%s)" % (engine, n, bf["kind"]))
        with self._lock:
            if key not in self._custom and len(self._custom) >= MAX_CUSTOM_TYPES:
                raise FactoryError("at most %d custom types" % MAX_CUSTOM_TYPES)
            self._custom[key] = {"title": title, "summary": summary, "engine": engine, "fields": clean, "created": round(self.now(), 3)}
            _atomic(self._custom_file, {"types": self._custom})
        return self.type(key)

    def delete_custom(self, key):
        with self._lock:
            if key not in self._custom:
                raise FactoryError("no such custom type")
            if self.list(key):
                raise FactoryError("that type still has instances: delete them first")
            del self._custom[key]
            _atomic(self._custom_file, {"types": self._custom})

    # ---- instances ----
    def _dir(self, type_key, iid):
        if not re.fullmatch(r"[a-z0-9_]{2,40}", type_key) or not re.fullmatch(r"fi-[0-9a-f]{12}", iid):
            raise FactoryError("not a valid type or instance id")
        d = (self.root / type_key / iid).resolve()
        if self.root.resolve() not in d.parents:
            raise FactoryError("outside the factory folder")
        return d

    def validate(self, type_key, config):
        t = self.type(type_key)
        if not isinstance(config, dict):
            raise FactoryError("the configuration must be an object")
        known = {f["name"] for f in t["fields"]}
        extra = sorted(set(config) - known)
        if extra:
            raise FactoryError("not fields of %s: %s" % (t["title"], ", ".join(extra[:6])))              # a type cannot be fed another type's fields
        clean, errs = {}, []
        for f in t["fields"]:
            v, e = check_value(f, config.get(f["name"]))
            if e:
                errs.append(e)
            elif v is not None:
                clean[f["name"]] = v
        if errs:
            raise FactoryError("; ".join(errs[:8]))
        return clean

    def create(self, type_key, name, config):
        name = str(name or "").strip()
        if not name or len(name) > 80 or _CTRL.search(name):
            raise FactoryError("give the instance a name of up to 80 characters")
        clean = self.validate(type_key, config)
        iid = "fi-" + uuid.uuid4().hex[:12]
        d = self._dir(type_key, iid)
        with self._lock:
            d.mkdir(parents=True, exist_ok=False)
            rec = {"id": iid, "type": type_key, "name": name, "config": clean, "created": round(self.now(), 3), "state": "configured"}
            _atomic(d / "instance.json", rec)
        return rec

    def get(self, type_key, iid):
        p = self._dir(type_key, iid) / "instance.json"
        if not p.is_file():
            raise FactoryError("no such instance")
        return json.loads(p.read_text(encoding="utf-8"))

    def update(self, type_key, iid, **changes):
        with self._lock:
            rec = self.get(type_key, iid)
            rec.update(changes)
            _atomic(self._dir(type_key, iid) / "instance.json", rec)
            return rec

    def list(self, type_key=None):
        out = []
        for tk in ([type_key] if type_key else sorted(self.types())):
            base = self.root / tk
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                p = d / "instance.json"
                if p.is_file():
                    try:
                        out.append(json.loads(p.read_text(encoding="utf-8")))
                    except ValueError:
                        continue
        return sorted(out, key=lambda r: r["created"])

    def delete(self, type_key, iid):
        d = self._dir(type_key, iid)
        if not (d / "instance.json").is_file():
            raise FactoryError("no such instance")
        try:
            shutil.rmtree(d)
        except OSError as e:                                  # on Windows a file still being served or opened cannot be removed
            raise FactoryError("could not remove the instance folder (something is still using it): %s" % e)

    def workdir(self, type_key, iid):
        """The instance's own folder: the only place its generator may read or write."""
        d = self._dir(type_key, iid)
        if not (d / "instance.json").is_file():
            raise FactoryError("no such instance")
        return d
