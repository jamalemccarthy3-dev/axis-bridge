// src/main.js
import { AxisManager } from "./axis-manager.js";

const system = new AxisManager();
console.log("--- AXIS Sweep System Initialized ---");
const report = await system.initiateAll();
console.log("System status:", report.errors === 0 ? "ready for command" : "started with listener errors");
