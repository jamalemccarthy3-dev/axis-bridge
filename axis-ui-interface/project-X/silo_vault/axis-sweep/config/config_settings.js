// config_settings.js
export const AXISSettings = {
    auto_mount: true,
    throttle_threshold: 80,
    batch_interval_ms: 5000,
    verbose_logging: false,
   
    // Updated for your dynamic control:
    // Set to "AUTOPILOT" to sweep automatically
    // Set to "MANUAL" to require your manual acknowledgment
    operation_mode: "MANUAL",
   
    notify_on_scan_complete: true
};