import test from "node:test";
import assert from "node:assert/strict";
import { LineageMapper } from "../src/lineage.js";
import { RecursivePurge } from "../src/purge.js";
import { BatteryGovernor } from "../src/throttler.js";
import { TaskScheduler } from "../src/scheduler.js";
import { Dispatcher } from "../src/event_dispatcher.js";
import { FeedbackManager } from "../src/feedback_manager.js";
import { UIManager } from "../src/dashbord.js";
import { CryptoVault } from "../lib/crypto_vault.js";
import { PortManager } from "../lib/port_manager.js";
import { KnownGoodBaseline } from "../config/config_registry.js";
import { AxisManager } from "../src/axis-manager.js";

const PROCS = [
    { pid: 1, ppid: 0, name: "system_kernel", cpu: 1 },
    { pid: 2, ppid: 1, name: "ui_shell", cpu: 2 },
    { pid: 10, ppid: 2, name: "miner", cpu: 95 },
    { pid: 11, ppid: 10, name: "miner_child", cpu: 40 },
    { pid: 12, ppid: 11, name: "miner_grandchild", cpu: 10 },
    { pid: 20, ppid: 1, name: "axis_manager", cpu: 5 }
];

test("the lineage of a process includes every descendant, parents first", () => {
    assert.deepEqual(LineageMapper.getFullTree(10, PROCS).map(p => p.pid), [10, 11, 12]);
    assert.deepEqual(LineageMapper.getFullTree(999, PROCS), []);
});

test("a loop in the process data does not hang the walk", () => {
    const loop = [{ pid: 1, ppid: 2, name: "a" }, { pid: 2, ppid: 1, name: "b" }];
    assert.equal(LineageMapper.getFullTree(1, loop).length, 2);
});

test("only the root of an unauthorised family is flagged", () => {
    const flagged = LineageMapper.findUnauthorized(PROCS, KnownGoodBaseline.authorized_services);
    assert.deepEqual(flagged.map(p => p.name), ["miner"]);
});

test("scanAndAlert alerts the dashboard and waits for a person", async () => {
    const ui = new UIManager(() => {});
    const flagged = await RecursivePurge.scanAndAlert(PROCS, { ui });
    assert.equal(flagged.length, 1);
    assert.equal(ui.alerts.length, 1);
});

test("a sweep without an explicit confirmation is refused", async () => {
    await assert.rejects(() => RecursivePurge.executeFinalSweep(PROCS[2], { processes: PROCS }), /confirmation/);
    await assert.rejects(() => RecursivePurge.executeFinalSweep(PROCS[2], { processes: PROCS, confirmed: "yes" }), /confirmation/);
});

test("a confirmed sweep without a terminate function is a dry run that changes nothing", async () => {
    const r = await RecursivePurge.executeFinalSweep(PROCS[2], { processes: PROCS, confirmed: true });
    assert.equal(r.dryRun, true);
    assert.deepEqual(r.planned, [12, 11, 10]);          // children before parents
    assert.deepEqual(r.terminated, []);
});

test("a confirmed sweep terminates children before the parent", async () => {
    const order = [];
    const r = await RecursivePurge.executeFinalSweep(PROCS[2], { processes: PROCS, confirmed: true, terminate: async (p) => { order.push(p.pid); } });
    assert.deepEqual(order, [12, 11, 10]);
    assert.equal(r.dryRun, false);
});

test("a family containing an authorised process is never swept", async () => {
    const r = await RecursivePurge.executeFinalSweep(PROCS[1], { processes: PROCS, confirmed: true, terminate: async () => { throw new Error("must not run"); } });
    assert.deepEqual(r.terminated, []);
    assert.ok(r.refused.includes("ui_shell"));
});

test("the throttler plans but never acts, and skips protected names", () => {
    const plan = BatteryGovernor.plan(PROCS, 30, ["axis_manager"]);
    assert.deepEqual(plan.map(p => p.pid), [10, 11]);
    assert.match(BatteryGovernor.stabilize(PROCS, 30).summary, /nothing was changed/);
});

test("the scheduler batches wake-ups and releases them together", () => {
    let t = 0;
    const s = new TaskScheduler({ intervalMs: 1000, maxBatch: 3, now: () => t });
    s.interceptWakeRequests("a");
    s.interceptWakeRequests("b");
    assert.deepEqual(s.flush(), []);                       // not due yet
    t = 1500;
    assert.deepEqual(s.flush(), ["a", "b"]);               // interval passed: one batch
    ["x", "y", "z"].forEach(x => s.interceptWakeRequests(x));
    assert.equal(s.due(), true);                           // a full batch is due at once
    assert.deepEqual(s.flush(), ["x", "y", "z"]);
});

test("one failing listener does not stop the others", () => {
    const seen = [];
    Dispatcher.listeners = {};
    Dispatcher.subscribe("e", () => { throw new Error("boom"); });
    Dispatcher.subscribe("e", (d) => seen.push(d));
    const r = Dispatcher.emit("e", 7);
    assert.deepEqual(seen, [7]);
    assert.equal(r.errors.length, 1);
    assert.equal(r.delivered, 1);
});

test("a decision waits for a person and accepts only Sweep or Whitelist", async () => {
    const f = new FeedbackManager();
    assert.equal(await f.promptUserForApproval(PROCS[2]), "WAITING_FOR_USER_INPUT");
    assert.equal(f.pending().length, 1);
    assert.throws(() => f.decide(10, "Maybe"), /Sweep/);
    assert.equal(f.decide(10, "Whitelist").choice, "Whitelist");
    assert.throws(() => f.decide(10, "Sweep"), /no decision/);
});

test("signatures verify, and a changed payload or a wrong key does not", () => {
    const sig = CryptoVault.sign({ a: 1, b: 2 }, "k");
    assert.equal(CryptoVault.verify({ b: 2, a: 1 }, sig, "k"), true);        // key order does not matter
    assert.equal(CryptoVault.verify({ a: 1, b: 3 }, sig, "k"), false);
    assert.equal(CryptoVault.verify({ a: 1, b: 2 }, sig, "other"), false);
    assert.equal(CryptoVault.verify({ a: 1, b: 2 }, "zz", "k"), false);
});

test("without a secret there is no marker (nothing is hard-coded)", () => {
    const saved = process.env.AXIS_SWEEP_SECRET;
    delete process.env.AXIS_SWEEP_SECRET;
    assert.throws(() => KnownGoodBaseline.trustedMarker(), /AXIS_SWEEP_SECRET/);
    process.env.AXIS_SWEEP_SECRET = "s";
    assert.equal(KnownGoodBaseline.trustedMarker().length, 64);
    if (saved === undefined) delete process.env.AXIS_SWEEP_SECRET; else process.env.AXIS_SWEEP_SECRET = saved;
});

test("the start-up sequence reports what really happened", async () => {
    const logs = [];
    Dispatcher.listeners = {};
    const m = new AxisManager({ log: (x) => logs.push(x) });
    const report = await m.initiateAll();
    assert.equal(report.host, PortManager.detectHost().platform);
    assert.equal(report.errors, 0);
    assert.equal(report.mode, "MANUAL");
});
