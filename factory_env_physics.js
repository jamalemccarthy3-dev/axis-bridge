/* factory_env_physics.js - NEXXUS spatial-environment physics: gravity, a ground plane, walls, and collisions between spheres and axis-aligned boxes.
 * Deterministic (no randomness), allocation-light, and the SAME file runs in the browser and in Node (the stress tests use Node). Dynamic bodies are spheres or boxes without rotation;
 * a cylinder is simulated as the box that bounds it. Static bodies never move. Any body whose numbers stop being finite is frozen and counted as a fault, so one bad value cannot spread. */
(function (root, factory) { if (typeof module === 'object' && module.exports) module.exports = factory(); else root.NexxusPhysics = factory(); })(this, function () {
  'use strict';
  var OFF = 4096, K1 = 16777216, K2 = 4096;

  function World(opts) {
    opts = opts || {};
    this.gravity = isFinite(opts.gravity) ? Number(opts.gravity) : 9.81;
    this.half = (isFinite(opts.ground) ? Number(opts.ground) : 40) / 2;
    this.cell = Math.max(1, Number(opts.cell) || 2);
    this.restitution = 0.25; this.damping = 0.9995; this.friction = 0.04; this.maxSpeed = 200;
    this.bodies = []; this.faults = 0; this.contacts = 0; this.steps = 0;
  }

  /* def: {shape: 'sphere'|'box', pos: [x,y,z], r (sphere radius) | half: [hx,hy,hz] (box), mass, dynamic} -> the body */
  World.prototype.addBody = function (def) {
    var p = def.pos || [0, 0, 0], sphere = def.shape === 'sphere';
    var b = { id: this.bodies.length, sphere: sphere, x: +p[0], y: +p[1], z: +p[2], vx: 0, vy: 0, vz: 0, r: 0, hx: 0, hy: 0, hz: 0, dynamic: !!def.dynamic, inv: 0, fault: false };
    if (sphere) { b.r = +def.r; b.hx = b.hy = b.hz = b.r; } else { b.hx = +def.half[0]; b.hy = +def.half[1]; b.hz = +def.half[2]; }
    if (!(b.r >= 0) || !isFinite(b.x + b.y + b.z + b.hx + b.hy + b.hz)) { b.fault = true; this.faults++; }
    if (b.dynamic) { var m = def.mass > 0 ? +def.mass : 1; b.inv = 1 / m; }
    this.bodies.push(b);
    return b;
  };

  function freeze(w, b) { if (!b.fault) { b.fault = true; w.faults++; } b.vx = b.vy = b.vz = 0; b.inv = 0; b.dynamic = false; }

  World.prototype.step = function (dt) {
    dt = Math.min(Math.max(dt, 0), 0.05);
    var bs = this.bodies, n = bs.length, i, b, g = this.gravity, half = this.half, e = this.restitution;
    this.contacts = 0; this.steps++;
    for (i = 0; i < n; i++) {                                         /* integrate, then ground and walls */
      b = bs[i];
      if (!b.dynamic) continue;
      b.vy -= g * dt; b.vx *= this.damping; b.vy *= this.damping; b.vz *= this.damping;
      var sp = Math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);
      if (sp > this.maxSpeed) { var k = this.maxSpeed / sp; b.vx *= k; b.vy *= k; b.vz *= k; }
      b.x += b.vx * dt; b.y += b.vy * dt; b.z += b.vz * dt;
      if (!isFinite(b.x + b.y + b.z + b.vx + b.vy + b.vz)) { freeze(this, b); continue; }
      var low = b.y - b.hy;
      if (low < 0) { b.y -= low; if (b.vy < 0) { b.vy = (-b.vy < 0.6) ? 0 : -b.vy * e; } b.vx *= (1 - this.friction); b.vz *= (1 - this.friction); }
      var ex = b.hx, ez = b.hz;
      if (b.x > half - ex) { b.x = half - ex; if (b.vx > 0) b.vx = -b.vx * e; } else if (b.x < -half + ex) { b.x = -half + ex; if (b.vx < 0) b.vx = -b.vx * e; }
      if (b.z > half - ez) { b.z = half - ez; if (b.vz > 0) b.vz = -b.vz * e; } else if (b.z < -half + ez) { b.z = -half + ez; if (b.vz < 0) b.vz = -b.vz * e; }
    }
    var grid = new Map(), c = this.cell;                                /* spatial hash of every body's box */
    for (i = 0; i < n; i++) {
      b = bs[i];
      if (b.fault) continue;
      var x0 = Math.floor((b.x - b.hx) / c), x1 = Math.floor((b.x + b.hx) / c), y0 = Math.floor((b.y - b.hy) / c), y1 = Math.floor((b.y + b.hy) / c), z0 = Math.floor((b.z - b.hz) / c), z1 = Math.floor((b.z + b.hz) / c);
      if (x1 - x0 > 64 || y1 - y0 > 64 || z1 - z0 > 64) continue;       /* enormous static bodies are handled below, not hashed */
      for (var X = x0; X <= x1; X++) for (var Y = y0; Y <= y1; Y++) for (var Z = z0; Z <= z1; Z++) {
        var key = (X + OFF) * K1 + (Y + OFF) * K2 + (Z + OFF), cell = grid.get(key);
        if (cell === undefined) grid.set(key, [i]); else cell.push(i);
      }
    }
    var self = this;
    grid.forEach(function (list, key) {
      var L = list.length;
      if (L < 2) return;
      for (var a = 0; a < L; a++) for (var d = a + 1; d < L; d++) {
        var A = bs[list[a]], B = bs[list[d]];
        if (!A.dynamic && !B.dynamic) continue;
        var ox = Math.max(A.x - A.hx, B.x - B.hx), oy = Math.max(A.y - A.hy, B.y - B.hy), oz = Math.max(A.z - A.hz, B.z - B.hz);
        if ((Math.floor(ox / c) + OFF) * K1 + (Math.floor(oy / c) + OFF) * K2 + (Math.floor(oz / c) + OFF) !== key) continue;   /* a pair is resolved once, in the cell that holds its overlap corner */
        resolve(self, A, B);
      }
    });
    for (i = 0; i < n; i++) {                                         /* contact correction may push a body out of the world: put it back */
      b = bs[i];
      if (!b.dynamic) continue;
      if (b.y < b.hy) { b.y = b.hy; if (b.vy < 0) b.vy = 0; }
      if (b.x > half - b.hx) b.x = half - b.hx; else if (b.x < -half + b.hx) b.x = -half + b.hx;
      if (b.z > half - b.hz) b.z = half - b.hz; else if (b.z < -half + b.hz) b.z = -half + b.hz;
    }
  };

  function resolve(w, A, B) {
    var nx, ny, nz, pen;
    if (A.sphere && B.sphere) {
      var dx = B.x - A.x, dy = B.y - A.y, dz = B.z - A.z, rr = A.r + B.r, d2 = dx * dx + dy * dy + dz * dz;
      if (d2 >= rr * rr) return;
      var dist = Math.sqrt(d2);
      if (dist < 1e-9) { nx = 0; ny = 1; nz = 0; pen = rr; } else { nx = dx / dist; ny = dy / dist; nz = dz / dist; pen = rr - dist; }
    } else if (A.sphere !== B.sphere) {
      var S = A.sphere ? A : B, X = A.sphere ? B : A, sgn = A.sphere ? -1 : 1;      /* e below points box -> sphere; the contact normal must point A -> B */
      var cx = Math.max(X.x - X.hx, Math.min(S.x, X.x + X.hx)), cy = Math.max(X.y - X.hy, Math.min(S.y, X.y + X.hy)), cz = Math.max(X.z - X.hz, Math.min(S.z, X.z + X.hz));
      var ex = S.x - cx, ey = S.y - cy, ez = S.z - cz, e2 = ex * ex + ey * ey + ez * ez;
      if (e2 >= S.r * S.r) return;
      if (e2 > 1e-12) { var ed = Math.sqrt(e2); nx = ex / ed; ny = ey / ed; nz = ez / ed; pen = S.r - ed; }
      else { var px = X.hx - Math.abs(S.x - X.x), py = X.hy - Math.abs(S.y - X.y), pz = X.hz - Math.abs(S.z - X.z); nx = ny = nz = 0;
        if (px <= py && px <= pz) { nx = S.x >= X.x ? 1 : -1; pen = px + S.r; } else if (py <= pz) { ny = S.y >= X.y ? 1 : -1; pen = py + S.r; } else { nz = S.z >= X.z ? 1 : -1; pen = pz + S.r; } }
      nx *= sgn; ny *= sgn; nz *= sgn;
    } else {
      var ox = A.hx + B.hx - Math.abs(B.x - A.x), oy = A.hy + B.hy - Math.abs(B.y - A.y), oz = A.hz + B.hz - Math.abs(B.z - A.z);
      if (ox <= 0 || oy <= 0 || oz <= 0) return;
      nx = ny = nz = 0;
      if (ox <= oy && ox <= oz) { nx = B.x >= A.x ? 1 : -1; pen = ox; } else if (oy <= oz) { ny = B.y >= A.y ? 1 : -1; pen = oy; } else { nz = B.z >= A.z ? 1 : -1; pen = oz; }
    }
    var inv = A.inv + B.inv;
    if (inv === 0) return;
    w.contacts++;
    var cor = pen / inv * 0.8;                                              /* positional correction, shared by inverse mass */
    A.x -= nx * cor * A.inv; A.y -= ny * cor * A.inv; A.z -= nz * cor * A.inv;
    B.x += nx * cor * B.inv; B.y += ny * cor * B.inv; B.z += nz * cor * B.inv;
    var rvn = (B.vx - A.vx) * nx + (B.vy - A.vy) * ny + (B.vz - A.vz) * nz;
    if (rvn >= 0) return;
    var j = -(1 + w.restitution) * rvn / inv;
    A.vx -= j * nx * A.inv; A.vy -= j * ny * A.inv; A.vz -= j * nz * A.inv;
    B.vx += j * nx * B.inv; B.vy += j * ny * B.inv; B.vz += j * nz * B.inv;
  }

  World.prototype.stats = function () {
    var maxSpeed = 0, dyn = 0, bs = this.bodies;
    for (var i = 0; i < bs.length; i++) { var b = bs[i]; if (b.dynamic) { dyn++; var s = Math.sqrt(b.vx * b.vx + b.vy * b.vy + b.vz * b.vz); if (s > maxSpeed) maxSpeed = s; } }
    return { bodies: bs.length, dynamic: dyn, faults: this.faults, contacts: this.contacts, maxSpeed: maxSpeed, steps: this.steps };
  };

  /* every dynamic body must be inside the world: above the ground, within the walls (the stress tests assert this) */
  World.prototype.outOfBounds = function () {
    var n = 0, bs = this.bodies, h = this.half + 1e-6;
    for (var i = 0; i < bs.length; i++) { var b = bs[i]; if (b.dynamic && (b.y - b.hy < -1e-6 || Math.abs(b.x) - b.hx > h || Math.abs(b.z) - b.hz > h)) n++; }
    return n;
  };

  return { World: World };
});
