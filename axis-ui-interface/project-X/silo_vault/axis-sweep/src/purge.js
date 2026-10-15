// src/purge.js - the recursive purge. It finds unauthorised process families and ALERTS; it removes one only after a person confirms, never on its own,
// and never anything on the protected list. The actual termination is handed in (terminate), so the default is a dry run that changes nothing.
import { LineageMapper } from "./lineage.js";
import { KnownGoodBaseline } from "../config/config_registry.js";
import { AXISSettings } from "../config/config_settings.js";

export const RecursivePurge = {
    async scanAndAlert(processes, { allowed = KnownGoodBaseline.authorized_services, ui } = {}) {
        const flagged = LineageMapper.findUnauthorized(processes, allowed);
        if (ui && flagged.length) ui.showAlert(flagged);
        return flagged;      // the engine now waits for your decision
    },

    // confirmed must be exactly true. Children are terminated before their parent. -> { dryRun, planned, terminated, refused }
    async executeFinalSweep(item, { processes, terminate = null, confirmed = false, allowed = KnownGoodBaseline.authorized_services } = {}) {
        if (confirmed !== true) throw new Error(`a sweep needs an explicit confirmation (operation_mode is ${AXISSettings.operation_mode})`);
        const family = LineageMapper.getFullTree(item.pid, processes);
        const allowedSet = new Set(allowed);
        const refused = family.filter(p => allowedSet.has(p.name));
        if (refused.length) return { dryRun: true, planned: [], terminated: [], refused: refused.map(p => p.name), reason: "the family contains an authorised process" };
        const order = [...family].reverse();
        if (typeof terminate !== "function") return { dryRun: true, planned: order.map(p => p.pid), terminated: [], refused: [] };
        const terminated = [];
        for (const p of order) {
            await terminate(p);
            terminated.push(p.pid);
        }
        return { dryRun: false, planned: order.map(p => p.pid), terminated, refused: [] };
    }
};
