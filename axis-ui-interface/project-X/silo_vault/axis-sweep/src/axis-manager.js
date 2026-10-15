// src/axis-manager.js - the master controller. It wires the scheduler, the dispatcher and the sweep modules and reports what really happened.
import { TaskScheduler } from "./scheduler.js";
import { Dispatcher } from "./event_dispatcher.js";
import { PortManager } from "../lib/port_manager.js";
import { AXISSettings } from "../config/config_settings.js";

export class AxisManager {
    constructor({ scheduler = new TaskScheduler({ intervalMs: AXISSettings.batch_interval_ms }), dispatcher = Dispatcher, log = console.log } = {}) {
        this.scheduler = scheduler;
        this.dispatcher = dispatcher;
        this.log = log;
        this.log("AxisManager: Gate initialized.");
    }

    // -> { host, scheduled, delivered, errors }: the real state after the start-up sequence
    async initiateAll() {
        this.log("AxisManager: Initiating sweep sequence...");
        const link = await PortManager.establishLink();
        const released = this.runScheduler();
        const emitted = this.runDispatcher();
        const report = { host: link.host.platform, mode: AXISSettings.operation_mode, scheduled: released.length, delivered: emitted.delivered, errors: emitted.errors.length };
        this.log("AxisManager: " + JSON.stringify(report));
        return report;
    }

    runScheduler() {
        return this.scheduler.flush();
    }

    runDispatcher() {
        return this.dispatcher.emit("sweep:start", { at: new Date().toISOString() });
    }
}
