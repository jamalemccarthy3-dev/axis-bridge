// src/dashbord.js - the dashboard's side of a sweep: shows status and alerts, and keeps them so a person (or a test) can read them back.
export class UIManager {
    constructor(log = console.log) {
        this.log = log;
        this.alerts = [];
        this.statuses = [];
    }

    showStatus(message) {
        this.statuses.push(message);
        this.log("UI-dashboard: " + message);
    }

    showAlert(flaggedItems) {
        this.alerts.push(...flaggedItems);
        this.log(`UI-dashboard: ${flaggedItems.length} unauthorised process(es) need your decision`);
    }
}
