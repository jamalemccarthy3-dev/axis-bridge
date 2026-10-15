"""src/silo_manager - the shared engines every silo uses (entropy, signal, risk, threshold, strategy, feedback, data_source, engine_base), the
pipeline that chains them, and SiloManager, which runs the four silos. The silo engines are loaded lazily and by path, so importing this package
never fails because one silo is broken: the problem shows up for that silo only, when it is asked to run."""
import importlib.util
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SILOS = {"sports": ("sports", "sports", "SportsEngine"), "stocks": ("stocks", "stocks", "StocksEngine"),
          "ecom": ("ecom", "ecom", "EcomEngine"), "logs": ("logs", "logs", "LogsEngine")}


class SiloManager:
    def __init__(self):
        self._engines = {}

    def available(self):
        return sorted(_SILOS)

    def engine(self, name):
        if name not in _SILOS:
            raise KeyError("unknown silo %r (silos: %s)" % (name, ", ".join(self.available())))
        if name not in self._engines:
            folder, module, cls = _SILOS[name]
            spec = importlib.util.spec_from_file_location("silo_engine_" + name, os.path.join(_ROOT, folder, module + ".py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._engines[name] = getattr(mod, cls)()
        return self._engines[name]

    def run_silo(self, name, data):
        """Run one silo's engine on `data`. -> its decision record."""
        return self.engine(name).calculate(data)

    def health(self):
        """-> {silo: 'OK' or the error}: whether each silo's engine can be created."""
        out = {}
        for name in self.available():
            try:
                self.engine(name)
                out[name] = "OK"
            except Exception as e:
                out[name] = "%s: %s" % (type(e).__name__, e)
        return out


__all__ = ["SiloManager"]
