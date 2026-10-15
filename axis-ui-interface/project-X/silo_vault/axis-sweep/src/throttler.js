// src/throttler.js - the battery governor. It PLANS: which busy background processes should be moved to a low-power state. It changes nothing itself.
export const BatteryGovernor = {
    // processes: [{ pid, name, cpu }], threshold: percent. Protected names are never in the plan.
    plan(processes, threshold = 80, protectedNames = []) {
        const protectedSet = new Set(protectedNames);
        return processes
            .filter(p => p.cpu > threshold && !protectedSet.has(p.name))
            .sort((a, b) => b.cpu - a.cpu)
            .map(p => ({ pid: p.pid, name: p.name, cpu: p.cpu, action: "move to low-power state" }));
    },

    // a plain-language summary of a plan; nothing was changed
    stabilize(processes = [], threshold = 80, protectedNames = []) {
        const plan = BatteryGovernor.plan(processes, threshold, protectedNames);
        return { plan, summary: `${plan.length} process(es) recommended for throttling above ${threshold}% CPU (nothing was changed)` };
    }
};
