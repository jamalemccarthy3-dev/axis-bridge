// src/lineage.js - process lineage: who started whom, so a sweep removes the whole family and not one head of the hydra.
// Works on a plain process list: [{ pid, ppid, name, cpu }]. It reads nothing from the machine itself.
export class LineageMapper {
    static buildTree(processes) {
        const children = new Map();
        for (const p of processes) {
            if (!children.has(p.ppid)) children.set(p.ppid, []);
            children.get(p.ppid).push(p.pid);
        }
        return children;
    }

    // the process and every descendant, parents before children
    static getFullTree(targetPid, processes) {
        const byPid = new Map(processes.map(p => [p.pid, p]));
        if (!byPid.has(targetPid)) return [];
        const children = LineageMapper.buildTree(processes);
        const out = [];
        const seen = new Set();                                  // a loop in the data must not hang the sweep
        const walk = (pid) => {
            if (seen.has(pid)) return;
            seen.add(pid);
            out.push(byPid.get(pid));
            for (const c of children.get(pid) || []) walk(c);
        };
        walk(targetPid);
        return out;
    }

    // processes whose name is not on the allow-list (the roots of unauthorised families only: a flagged child of a flagged parent is part of its family)
    static findUnauthorized(processes, allowedNames) {
        const allowed = new Set(allowedNames);
        const flagged = processes.filter(p => !allowed.has(p.name));
        const flaggedPids = new Set(flagged.map(p => p.pid));
        return flagged.filter(p => !flaggedPids.has(p.ppid));
    }
}
