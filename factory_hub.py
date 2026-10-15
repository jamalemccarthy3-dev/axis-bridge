"""factory_hub.py - ties the type registry to the generators: build an instance, run a company, keep each type's work apart.

  platform_factory      -> factory_platform (a real multi-page site in the instance folder)
  spatial_environment   -> factory_env      (a playable 3D page with its own physics; headless physics check)
  micro_company         -> micro_company    (bots on a scheduler; deploy/stop are explicit)
  publishing_pipeline   -> micro_company    (a maker bot renders a real mp4 and a stager bot queues it for review; the owner approves and dispatches)
A custom type that names an engine builds with that engine; a custom type with engine "none" has no generator and says so (its instances are records the owner keeps).
Live objects (running companies) are held here, keyed by instance id, so two instances of one type, or of different types, never share a runner, a folder or a ledger.
"""
import threading
import time

import factory_env
import factory_platform
import factory_types
import micro_company

FactoryError = factory_types.FactoryError


def pipeline_company(config):
    """The publishing pipeline's configuration as a micro-company: maker -> stager."""
    lines = [s.strip() for s in str(config["brief"]).replace("\r", "").split("\n") if s.strip()]
    if len(lines) == 1:
        import re
        lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+", lines[0]) if s.strip()]
    bots = [{"name": "Maker", "task": "video_make", "params": {"title": config["title"], "lines": lines, "seconds_per_card": 3}, "every_s": config.get("every_s"), "then": "Stager"},
            {"name": "Stager", "task": "publish_stage", "params": {"title": config["title"], "description": config["brief"][:4000], "tags": config.get("tags") or [], "topic": config["topic"]}}]
    return {"company": config["title"], "purpose": "Publishing pipeline: %s" % config["topic"], "bots": bots}


class Hub:
    def __init__(self, root, services=None, resolver=None, now=time.time):
        self.factory = factory_types.Factory(root, now)
        self.services, self.resolver, self.now = services or {}, resolver, now
        self.companies = {}
        self._lock = threading.RLock()

    # ---- helpers ----
    def _engine(self, rec):
        t = self.factory.type(rec["type"])
        return t.get("engine") if t.get("engine") in factory_types.ENGINES else None

    def create(self, type_key, name, config, demo=False):
        rec = self.factory.create(type_key, name, config)
        if demo:
            rec = self.factory.update(type_key, rec["id"], demo=True)
        return rec

    def build(self, type_key, iid):
        rec = self.factory.get(type_key, iid)
        eng, work, cfg = self._engine(rec), self.factory.workdir(type_key, iid), rec["config"]
        if eng is None:
            raise FactoryError("this custom type has no generator: its instances are records, there is nothing to build")
        t0 = time.perf_counter()
        try:
            if eng == "platform_factory":
                info = factory_platform.build(work, cfg, self.resolver, iid)          # build() proves its own output and raises if it fails
                info = {k: v for k, v in info.items() if k != "files"}
                chk = {"ok": True, "problems": []}
            elif eng == "spatial_environment":
                info = factory_env.build(work, cfg, self.resolver)
                chk = factory_env.check(work, cfg, self.resolver)
            else:
                spec = cfg if eng == "micro_company" else pipeline_company(cfg)
                co = micro_company.MicroCompany(work, spec, self.services)
                with self._lock:
                    old = self.companies.pop(iid, None)
                    if old:
                        old.stop()
                    self.companies[iid] = co
                info, chk = {"bots": len(co.spec["bots"])}, {"ok": True, "problems": []}
        except (factory_platform.PlatformError, factory_env.EnvError, micro_company.CompanyError) as e:
            self.factory.update(type_key, iid, state="build_failed", build={"ok": False, "error": str(e)})
            raise FactoryError(str(e))
        build = {"ok": chk["ok"], "problems": chk["problems"], "info": info, "ms": round((time.perf_counter() - t0) * 1000, 1), "at": round(self.now(), 3)}
        self.factory.update(type_key, iid, state="built" if chk["ok"] else "build_failed", build=build)
        return build

    def _company(self, type_key, iid):
        rec = self.factory.get(type_key, iid)
        co = self.companies.get(iid)
        if co is None:
            raise FactoryError("build the instance first")
        return rec, co

    def deploy(self, type_key, iid):
        rec, co = self._company(type_key, iid)
        started = co.start()
        self.factory.update(type_key, iid, state="running")
        return {"started": started}

    def stop(self, type_key, iid):
        rec, co = self._company(type_key, iid)
        done = co.stop()
        self.factory.update(type_key, iid, state="built")
        return {"stopped": done}

    def run_once(self, type_key, iid, bot):
        rec, co = self._company(type_key, iid)
        return co.run_bot(bot)

    def company_status(self, iid):
        co = self.companies.get(iid)
        return co.status() if co else None

    def delete(self, type_key, iid):
        co = self.companies.pop(iid, None)
        if co:
            co.stop()
        self.factory.delete(type_key, iid)

    def shutdown(self):
        for co in list(self.companies.values()):
            co.stop(2)

    def preview_root(self, type_key, iid):
        """The folder a browser may be served from for this instance (platform: site/, environment: env/), or None."""
        rec = self.factory.get(type_key, iid)
        eng = self._engine(rec)
        sub = {"platform_factory": "site", "spatial_environment": "env"}.get(eng)
        p = self.factory.workdir(type_key, iid) / sub if sub else None
        return p if p is not None and p.is_dir() else None
