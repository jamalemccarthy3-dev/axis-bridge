"""factory_env.py - the environment compiler: a spatial_environment configuration becomes a playable 3D page.

Output (in the instance's own folder): env/index.html (the scene is embedded as JSON), env/env.js (staging, lights, first-person navigation), env/physics.js (a copy of factory_env_physics.js).
Babylon.js is loaded from the server's own /vendor/babylon.js, never from the internet. The compiler:
  * validates every object, light and the player (shapes, finite numbers, sizes, colours, counts) and refuses a bad scene instead of fixing it silently,
  * checks the compiled files (the page parses, env.js and physics.js pass `node --check`, the embedded scene reads back identical),
  * simulate() runs the same physics file under Node, headless, and reports bodies, contacts, faults, objects out of bounds and the step rate: that is the stress telemetry.
Navigation: W A S D / arrow keys to move, mouse to look (click to capture), Space to jump, Shift to run; the player is a sphere in the same physics world as the objects.
"""
import hashlib
import html
import html.parser
import io
import json
import math
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PHYSICS_SRC = HERE / "factory_env_physics.js"
MAX_OBJECTS = 5000
SHAPES = ("box", "sphere", "cylinder", "panel")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")
LIGHTS = ("hemispheric", "directional", "point")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class EnvError(Exception):
    pass


def _num(v, what, lo=None, hi=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise EnvError("%s must be a finite number" % what)
    if lo is not None and v < lo or hi is not None and v > hi:
        raise EnvError("%s must be between %s and %s" % (what, lo, hi))
    return float(v)


def _vec(v, n, what, lo=-1000, hi=1000):
    if not isinstance(v, (list, tuple)) or len(v) != n:
        raise EnvError("%s must be a list of %d numbers" % (what, n))
    return [_num(x, what, lo, hi) for x in v]


def _color(v, what):
    if v in (None, ""):
        return "#8899aa"
    if not isinstance(v, str) or not _HEX.match(v):
        raise EnvError("%s must be a #rrggbb colour" % what)
    return v.lower()


def _texture(resolver, cid, cache, files):
    """A Creations-hub image -> (path inside the build, width, height). The bytes are queued in `files` to be copied beside the page."""
    if cid in cache:
        return cache[cid]
    got = resolver(cid) if resolver else None
    pick = next((f for f in (got or []) if f[0].lower().endswith(IMG_EXT)), None)
    if pick is None:
        raise EnvError("the texture %r is not an image in the Creations hub" % cid)
    from PIL import Image
    try:
        w, h = Image.open(io.BytesIO(pick[1])).size
    except Exception:
        raise EnvError("the texture %r is not a readable image" % cid)
    rel = "tex/%s%s" % (hashlib.sha256(pick[1]).hexdigest()[:12], pick[0][pick[0].rfind("."):].lower())
    files[rel] = pick[1]
    cache[cid] = (rel, w, h)
    return cache[cid]


def compile_scene(config, resolver=None):
    return _compile(config, resolver)[0]


def _compile(config, resolver=None):
    """-> (the normalised scene the page embeds, {path: bytes} of the textures to copy). Raises EnvError on anything that is not a valid scene."""
    files, cache = {}, {}
    ground = _num(config.get("ground", 40), "ground", 4, 500)
    gravity = _num(config.get("gravity", 9.81), "gravity", 0, 30)
    raw = config.get("objects")
    if not isinstance(raw, list) or not raw:
        raise EnvError("a scene needs at least one object")
    if len(raw) > MAX_OBJECTS:
        raise EnvError("a scene holds at most %d objects" % MAX_OBJECTS)
    objects = []
    for i, o in enumerate(raw):
        w = "object %d" % (i + 1)
        if not isinstance(o, dict):
            raise EnvError("%s must be an object" % w)
        shape = o.get("shape")
        if shape not in SHAPES:
            raise EnvError("%s: shape must be one of %s" % (w, ", ".join(SHAPES)))
        size, tex = o.get("size"), None
        if o.get("texture"):
            tex = _texture(resolver, str(o["texture"]), cache, files)
        if shape == "panel":
            lst = size if isinstance(size, (list, tuple)) else [size]
            size = _vec(lst, len(lst), w + " size (width[, height])", 0.05, 500) if len(lst) in (1, 2) else None
            if size is None:
                raise EnvError("%s size must be [width] or [width, height]" % w)
            if len(size) == 1:
                if tex is None:
                    raise EnvError("%s: give the panel a height, or a texture to take its proportions from" % w)
                size = [size[0], size[0] * tex[2] / tex[1]]
            size = [size[0], size[1], 0.1]
        elif shape == "box":
            size = _vec(size, 3, w + " size", 0.05, 500)
        elif shape == "sphere":
            size = _vec(size if isinstance(size, (list, tuple)) else [size], 1, w + " size (diameter)", 0.05, 500)
        else:
            size = _vec(size, 2, w + " size (diameter, height)", 0.05, 500)
        pos = _vec(o.get("position", [0, 0, 0]), 3, w + " position", -1000, 1000)
        if abs(pos[0]) > ground / 2 or abs(pos[2]) > ground / 2:
            raise EnvError("%s is outside the ground (x and z must be within %s of the centre)" % (w, ground / 2))
        dynamic = o.get("dynamic", False)
        if not isinstance(dynamic, bool):
            raise EnvError("%s: dynamic must be true or false" % w)
        mass = _num(o.get("mass", 1), w + " mass", 0.001, 100000) if dynamic else 0
        half = [size[0] / 2, size[1] / 2, size[2] / 2] if shape in ("box", "panel") else [size[0] / 2, size[1] / 2 if shape == "cylinder" else size[0] / 2, size[0] / 2]
        if pos[1] - half[1] < -1e-9:
            raise EnvError("%s is below the ground: raise its y to at least %s" % (w, round(half[1], 3)))
        objects.append({"shape": shape, "size": size, "half": half, "position": pos, "color": _color(o.get("color"), w + " colour"), "dynamic": dynamic, "mass": mass, "texture": tex[0] if tex else None})
        if shape == "panel" and dynamic:
            raise EnvError("%s: a panel is fixed in place (it cannot be dynamic)" % w)
    lights = []
    for i, l in enumerate(config.get("lights") or [{"type": "hemispheric", "intensity": 0.8}, {"type": "directional", "intensity": 0.7, "position": [-10, 20, -10]}]):
        w = "light %d" % (i + 1)
        if not isinstance(l, dict) or l.get("type") not in LIGHTS:
            raise EnvError("%s: type must be one of %s" % (w, ", ".join(LIGHTS)))
        lights.append({"type": l["type"], "intensity": _num(l.get("intensity", 0.8), w + " intensity", 0, 10), "color": _color(l.get("color") or "#ffffff", w + " colour"),
                       "position": _vec(l.get("position", [0, 10, 0]), 3, w + " position", -1000, 1000)})
    p = config.get("player") or {}
    if not isinstance(p, dict):
        raise EnvError("player must be an object")
    player = {"start": _vec(p.get("start", [0, 1.7, -ground / 4]), 3, "player start", -1000, 1000), "speed": _num(p.get("speed", 5), "player speed", 0.5, 30), "height": _num(p.get("height", 1.7), "player height", 0.8, 3)}
    return {"title": str(config.get("title") or "Environment").strip()[:80], "ground": ground, "gravity": gravity, "objects": objects, "lights": lights, "player": player}, files


_ENV_JS = r"""(function () {
  var S = JSON.parse(document.getElementById('scene-data').textContent);
  var canvas = document.getElementById('view'), hud = document.getElementById('hud');
  var engine = new BABYLON.Engine(canvas, true, { preserveDrawingBuffer: false });
  var scene = new BABYLON.Scene(engine);
  scene.clearColor = new BABYLON.Color4(0.04, 0.06, 0.12, 1);
  function col(h) { return BABYLON.Color3.FromHexString(h); }
  var world = new NexxusPhysics.World({ gravity: S.gravity, ground: S.ground });
  var ground = BABYLON.MeshBuilder.CreateGround('ground', { width: S.ground, height: S.ground }, scene);
  var gm = new BABYLON.StandardMaterial('gm', scene); gm.diffuseColor = new BABYLON.Color3(0.16, 0.2, 0.26); gm.specularColor = new BABYLON.Color3(0, 0, 0); ground.material = gm;
  var pairs = [], TEX = { expected: 0, loaded: 0, failed: 0, size: [] };
  S.objects.forEach(function (o, i) {
    var m;
    if (o.shape === 'box') m = BABYLON.MeshBuilder.CreateBox('o' + i, { width: o.size[0], height: o.size[1], depth: o.size[2] }, scene);
    else if (o.shape === 'sphere') m = BABYLON.MeshBuilder.CreateSphere('o' + i, { diameter: o.size[0] }, scene);
    else if (o.shape === 'panel') m = BABYLON.MeshBuilder.CreatePlane('o' + i, { width: o.size[0], height: o.size[1], sideOrientation: BABYLON.Mesh.DOUBLESIDE }, scene);
    else m = BABYLON.MeshBuilder.CreateCylinder('o' + i, { diameter: o.size[0], height: o.size[1] }, scene);
    var mat = new BABYLON.StandardMaterial('m' + i, scene); mat.diffuseColor = col(o.color); m.material = mat;
    if (o.texture) {
      TEX.expected++;
      var tx = new BABYLON.Texture(o.texture, scene, false, true, BABYLON.Texture.TRILINEAR_SAMPLINGMODE, function () { TEX.loaded++; TEX.size.push([tx.getSize().width, tx.getSize().height]); }, function () { TEX.failed++; });
      if (o.shape === 'panel') { mat.disableLighting = true; mat.emissiveTexture = tx; mat.diffuseColor = new BABYLON.Color3(0, 0, 0); mat.backFaceCulling = false; } else { mat.diffuseTexture = tx; mat.diffuseColor = new BABYLON.Color3(1, 1, 1); }
    }
    var b = world.addBody(o.shape === 'sphere' ? { shape: 'sphere', pos: o.position, r: o.size[0] / 2, mass: o.mass, dynamic: o.dynamic } : { shape: 'box', pos: o.position, half: o.half, mass: o.mass, dynamic: o.dynamic });
    m.position.set(b.x, b.y, b.z); pairs.push([b, m]);
  });
  S.lights.forEach(function (l, i) {
    var L;
    if (l.type === 'hemispheric') L = new BABYLON.HemisphericLight('l' + i, new BABYLON.Vector3(0, 1, 0), scene);
    else if (l.type === 'directional') L = new BABYLON.DirectionalLight('l' + i, new BABYLON.Vector3(-l.position[0], -l.position[1], -l.position[2]).normalize(), scene);
    else L = new BABYLON.PointLight('l' + i, new BABYLON.Vector3(l.position[0], l.position[1], l.position[2]), scene);
    L.intensity = l.intensity; L.diffuse = col(l.color);
  });
  var P = S.player, pr = 0.4, touch = { fx: 0, fz: 0, jump: false, on: (('ontouchstart' in window) || navigator.maxTouchPoints > 0) };
  var player = world.addBody({ shape: 'sphere', pos: [P.start[0], Math.max(P.start[1], pr), P.start[2]], r: pr, mass: 70, dynamic: true });
  var cam = new BABYLON.FreeCamera('cam', new BABYLON.Vector3(player.x, player.y + P.height - pr, player.z), scene);
  cam.minZ = 0.05; cam.fov = 1.1; var yaw = 0, pitch = 0, keys = {};
  window.addEventListener('keydown', function (e) { keys[e.code] = true; }); window.addEventListener('keyup', function (e) { keys[e.code] = false; });
  canvas.addEventListener('click', function (e) { if (!touch.on && canvas.requestPointerLock) canvas.requestPointerLock(); });
  if (touch.on) {                                                    /* phones and tablets: left thumb walks, right thumb looks, the round button jumps */
    var ring = document.createElement('div'), knob = document.createElement('div'), jb = document.createElement('div'); ring.className = 'tstick'; knob.className = 'tknob'; ring.appendChild(knob); ring.hidden = true; jb.className = 'tjump'; jb.textContent = 'JUMP';
    document.body.appendChild(ring); document.body.appendChild(jb);
    var st = null, lk = null, R = 56;
    canvas.addEventListener('pointerdown', function (e) {
      if (e.pointerType === 'mouse') return; try { canvas.setPointerCapture(e.pointerId); } catch (x) { }
      if (e.clientX < innerWidth / 2 && !st) { st = { id: e.pointerId, x: e.clientX, y: e.clientY }; ring.hidden = false; ring.style.left = (e.clientX - R) + 'px'; ring.style.top = (e.clientY - R) + 'px'; knob.style.transform = 'translate(0,0)'; }
      else if (e.clientX >= innerWidth / 2 && !lk) lk = { id: e.pointerId, x: e.clientX, y: e.clientY };
    });
    canvas.addEventListener('pointermove', function (e) {
      if (st && e.pointerId === st.id) { var dx = e.clientX - st.x, dy = e.clientY - st.y, d = Math.sqrt(dx * dx + dy * dy) || 1, k = Math.min(1, d / R); touch.fx = dx / d * k; touch.fz = -dy / d * k; knob.style.transform = 'translate(' + (dx / d * Math.min(d, R)) + 'px,' + (dy / d * Math.min(d, R)) + 'px)'; }
      else if (lk && e.pointerId === lk.id) { yaw += (e.clientX - lk.x) * 0.006; pitch = Math.max(-1.4, Math.min(1.4, pitch + (e.clientY - lk.y) * 0.006)); lk.x = e.clientX; lk.y = e.clientY; }
    });
    var up = function (e) { if (st && e.pointerId === st.id) { st = null; touch.fx = touch.fz = 0; ring.hidden = true; } if (lk && e.pointerId === lk.id) lk = null; };
    canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
    jb.addEventListener('pointerdown', function (e) { e.preventDefault(); touch.jump = true; }); jb.addEventListener('pointerup', function () { touch.jump = false; }); jb.addEventListener('pointercancel', function () { touch.jump = false; });
  }
  document.addEventListener('mousemove', function (e) { if (document.pointerLockElement === canvas) { yaw += e.movementX * 0.0022; pitch = Math.max(-1.4, Math.min(1.4, pitch + e.movementY * 0.0022)); } });
  var last = performance.now(), frames = 0, fpsT = last, fps = 0;
  window.nexxusEnv = { textures: TEX, world: world, player: player, camera: cam, pairs: pairs, scene: scene, keys: keys };
  engine.runRenderLoop(function () {
    var now = performance.now(), dt = Math.min((now - last) / 1000, 0.05); last = now;
    var f = (keys.KeyW || keys.ArrowUp ? 1 : 0) - (keys.KeyS || keys.ArrowDown ? 1 : 0), r = (keys.KeyD || keys.ArrowRight ? 1 : 0) - (keys.KeyA || keys.ArrowLeft ? 1 : 0);
    f = Math.max(-1, Math.min(1, f + touch.fz)); r = Math.max(-1, Math.min(1, r + touch.fx));
    var sp = P.speed * (keys.ShiftLeft || keys.ShiftRight ? 1.8 : 1), ln = Math.max(1, Math.sqrt(f * f + r * r));
    var fx = Math.sin(yaw), fz = Math.cos(yaw);
    player.vx = (fx * f + fz * r) / ln * sp; player.vz = (fz * f - fx * r) / ln * sp;
    if ((keys.Space || touch.jump) && player.y - player.r <= 0.02) player.vy = 5.2;
    world.step(dt);
    for (var i = 0; i < pairs.length; i++) { var b = pairs[i][0]; if (b.dynamic) pairs[i][1].position.set(b.x, b.y, b.z); }
    cam.position.set(player.x, player.y + P.height - pr, player.z); cam.rotation.set(pitch, yaw, 0);
    scene.render(); frames++;
    if (now - fpsT > 500) { fps = Math.round(frames * 1000 / (now - fpsT)); frames = 0; fpsT = now; var s = world.stats(); hud.textContent = S.title + '  |  ' + fps + ' fps  |  ' + (TEX.expected ? 'textures ' + TEX.loaded + '/' + TEX.expected + (TEX.failed ? ' (' + TEX.failed + ' FAILED)' : '') + '  |  ' : '') + s.bodies + ' bodies, ' + s.contacts + ' contacts  |  ' + (touch.on ? 'left thumb walks, right thumb looks' : 'WASD move, mouse look (click), Space jump, Shift run'); }
  });
  window.addEventListener('resize', function () { engine.resize(); });
})();
"""


def build(workdir, config, resolver=None):
    scene, files = _compile(config, resolver)
    out = Path(workdir) / "env"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(PHYSICS_SRC, out / "physics.js")
    (out / "env.js").write_text(_ENV_JS, encoding="utf-8")
    for rel, data in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    data = json.dumps(scene, separators=(",", ":")).replace("<", "\\u003c")
    (out / "index.html").write_text(
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover"><title>%s</title>'
        '<style>html,body{margin:0;height:100%%;background:#0a0f1e;overflow:hidden}#view{width:100%%;height:100%%;display:block;outline:none;touch-action:none}'
        '.tstick{position:fixed;width:112px;height:112px;border-radius:50%%;border:2px solid rgba(255,255,255,.35);background:rgba(255,255,255,.08);pointer-events:none}.tknob{position:absolute;left:36px;top:36px;width:40px;height:40px;border-radius:50%%;background:rgba(255,255,255,.55)}'
        '.tjump{position:fixed;right:22px;bottom:26px;width:72px;height:72px;border-radius:50%%;background:rgba(56,189,248,.35);border:2px solid rgba(255,255,255,.5);color:#fff;font:700 12px system-ui,sans-serif;display:flex;align-items:center;justify-content:center;touch-action:none;user-select:none}'
        '@media (max-width:820px){#hud{font-size:11px;max-width:92vw}}'
        '#hud{position:fixed;left:10px;top:8px;color:#cfd8ee;font:12px system-ui,sans-serif;background:rgba(0,0,0,.45);padding:4px 8px;border-radius:6px;pointer-events:none}</style></head>\n'
        '<body><canvas id="view" tabindex="0"></canvas><div id="hud"></div>\n<script id="scene-data" type="application/json">%s</script>\n'
        '<script src="/vendor/babylon.js"></script><script src="physics.js"></script><script src="env.js"></script></body></html>\n' % (html.escape(scene["title"]), data), encoding="utf-8")
    return {"files": ["env/index.html", "env/env.js", "env/physics.js"], "textures": sorted(files), "objects": len(scene["objects"]), "dynamic": sum(1 for o in scene["objects"] if o["dynamic"]), "entry": "env/index.html"}


class _Scan(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self._in, self.scripts = "", False, []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in = True
        if tag == "script":
            self.scripts.append(dict(attrs).get("src"))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in = False

    def handle_data(self, d):
        if self._in:
            self.title += d


def _node_check(path):
    r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=30)
    return None if r.returncode == 0 else (r.stderr.strip().splitlines() or ["syntax error"])[-1][:300]


def check(workdir, config, resolver=None):
    """Read the compiled files back and prove them. -> {"ok": bool, "problems": [...]}"""
    problems, out = [], Path(workdir) / "env"
    try:
        scene, files = _compile(config, resolver)
    except EnvError as e:
        return {"ok": False, "problems": [str(e)]}
    for n in ("index.html", "env.js", "physics.js"):
        if not (out / n).is_file() or (out / n).stat().st_size < 200:
            problems.append("%s is missing or empty" % n)
    if problems:
        return {"ok": False, "problems": problems}
    for rel, data in files.items():
        if not (out / rel).is_file() or hashlib.sha256((out / rel).read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
            problems.append("the texture file %s is missing or does not match its source" % rel)
    page = (out / "index.html").read_text(encoding="utf-8")
    sc = _Scan()
    sc.feed(page)
    if scene["title"] not in html.unescape(sc.title):
        problems.append("the page title does not carry the scene title")
    if sc.scripts[-3:] != ["/vendor/babylon.js", "physics.js", "env.js"]:
        problems.append("the page does not load babylon, physics and env in order")
    if re.search(r"""(src|href)\s*=\s*["']\s*(https?:)?//""", page):
        problems.append("the page references an external URL")
    m = re.search(r'<script id="scene-data" type="application/json">(.*?)</script>', page, re.S)
    try:
        if not m or json.loads(m.group(1)) != scene:
            problems.append("the embedded scene does not read back identical to the compiled scene")
    except ValueError:
        problems.append("the embedded scene is not valid JSON")
    for n in ("env.js", "physics.js"):
        try:
            err = _node_check(out / n)
        except (OSError, subprocess.SubprocessError):
            err = "node is not available to check %s" % n
        if err:
            problems.append("%s: %s" % (n, err))
    return {"ok": not problems, "problems": problems}


_SIM = r"""
const {World}=require(process.argv[1]); const cfg=JSON.parse(require('fs').readFileSync(0,'utf8'));
const w=new World({gravity:cfg.gravity,ground:cfg.ground});
for(const o of cfg.objects) w.addBody(o.shape==='sphere'?{shape:'sphere',pos:o.position,r:o.size[0]/2,mass:o.mass,dynamic:o.dynamic}:{shape:'box',pos:o.position,half:o.half,mass:o.mass,dynamic:o.dynamic});
const t=process.hrtime.bigint(); let peakContacts=0, worst=0;
for(let i=0;i<cfg.steps;i++){ w.step(1/60); if(w.contacts>peakContacts)peakContacts=w.contacts; const m=process.memoryUsage().heapUsed; if(m>worst)worst=m; }
const ms=Number(process.hrtime.bigint()-t)/1e6; const s=w.stats();
let ke=0,low=1e9; for(const b of w.bodies){ if(b.dynamic){ke+=b.vx*b.vx+b.vy*b.vy+b.vz*b.vz; low=Math.min(low,b.y-b.hy);} }
console.log(JSON.stringify({steps:cfg.steps,ms:ms,step_ms:ms/cfg.steps,bodies:s.bodies,dynamic:s.dynamic,faults:s.faults,peak_contacts:peakContacts,out_of_bounds:w.outOfBounds(),max_speed:s.maxSpeed,min_height:low===1e9?null:low,heap_mb:worst/1048576}));
"""


def simulate(config, steps=600, timeout=120, resolver=None):
    """Run the compiled scene's physics headless under Node. -> telemetry dict (raises EnvError if the scene is invalid or node fails)."""
    scene = compile_scene(config, resolver)
    scene["steps"] = int(max(1, min(steps, 20000)))
    try:
        r = subprocess.run(["node", "-e", _SIM, str(PHYSICS_SRC)], input=json.dumps(scene), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise EnvError("the headless simulation could not run: %s" % e)
    if r.returncode != 0:
        raise EnvError("the headless simulation failed: %s" % (r.stderr.strip().splitlines() or ["unknown"])[-1][:300])
    return json.loads(r.stdout.strip().splitlines()[-1])
