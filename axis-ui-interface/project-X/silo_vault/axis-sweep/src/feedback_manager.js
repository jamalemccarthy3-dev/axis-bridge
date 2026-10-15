// src/feedback_manager.js - the human decision. Nothing is swept until a person answers "Sweep"; "Whitelist" keeps the process.
export class FeedbackManager {
    constructor() {
        this.waiting = new Map();      // pid -> item
        this.decisions = [];
    }

    async promptUserForApproval(flaggedItem, ui) {
        this.waiting.set(flaggedItem.pid, flaggedItem);
        if (ui) ui.showStatus(`Unauthorised process ${flaggedItem.name} (pid ${flaggedItem.pid}): Sweep or Whitelist?`);
        return "WAITING_FOR_USER_INPUT";
    }

    decide(pid, choice) {
        if (!this.waiting.has(pid)) throw new Error(`no decision is waiting for pid ${pid}`);
        if (choice !== "Sweep" && choice !== "Whitelist") throw new Error('the choice must be "Sweep" or "Whitelist"');
        const item = this.waiting.get(pid);
        this.waiting.delete(pid);
        const record = { pid, name: item.name, choice };
        this.decisions.push(record);
        return record;
    }

    pending() {
        return [...this.waiting.values()];
    }
}
