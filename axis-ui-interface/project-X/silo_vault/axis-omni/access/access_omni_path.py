"""access_omni_path.py - which files axis-omni may touch.

    access = OmniPathAccess()                      # default: read the bank/ folder, read and write the out/ folder
    access.resolve("bank/voices.json")             -> the real absolute path, if it is inside an allowed folder
    access.resolve("out/reply.wav", write=True)    -> only allowed where writing is allowed
    access.resolve("../../secrets.txt")            -> PermissionError

Every path is made absolute and its symbolic links are resolved BEFORE the check, so `..` tricks and links that point outside cannot escape. A relative path is taken
relative to the omni folder."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OMNI = os.path.dirname(HERE)


class OmniPathAccess:
    def __init__(self, roots=None):
        """roots: {name: (folder, writable)}. Default {"bank": (omni/bank, False), "out": (omni/out, True)}."""
        roots = roots or {"bank": (os.path.join(OMNI, "bank"), False), "out": (os.path.join(OMNI, "out"), True)}
        self.roots = {n: (os.path.realpath(p), bool(w)) for n, (p, w) in roots.items()}

    def resolve(self, path, write=False):
        """-> the real path. PermissionError when it is outside every allowed folder, or when write=True and the folder it is in is read-only. ValueError for an empty or NUL-containing path."""
        if not path or "\x00" in str(path):
            raise ValueError("a path is a non-empty text without NUL characters")
        p = path if os.path.isabs(path) else os.path.join(OMNI, path)
        real = os.path.realpath(p)
        for name, (root, writable) in self.roots.items():
            if real == root or real.startswith(root + os.sep):
                if write and not writable:
                    raise PermissionError("%s is inside %r, which is read-only" % (path, name))
                return real
        raise PermissionError("%s is outside the folders axis-omni may use (%s)" % (path, ", ".join(sorted(self.roots))))

    def allowed(self, path, write=False):
        """True/False instead of raising."""
        try:
            self.resolve(path, write)
            return True
        except (PermissionError, ValueError):
            return False

    def open(self, path, mode="r", **kw):
        """open() for allowed paths only: a mode that writes ('w', 'a', 'x', '+') needs a writable folder. The folder of a new file is created."""
        write = any(c in mode for c in "wax+")
        real = self.resolve(path, write)
        if write:
            os.makedirs(os.path.dirname(real), exist_ok=True)
        return open(real, mode, **kw)
