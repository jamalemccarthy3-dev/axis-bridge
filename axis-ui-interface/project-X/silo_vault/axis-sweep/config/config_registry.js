// config/config_registry.js - the known-good baseline: what is allowed to run and what must never be touched.
import { CryptoVault } from "../lib/crypto_vault.js";

export const KnownGoodBaseline = {
    version: "1.0.0",
    authorized_services: [
        "system_kernel",
        "ui_shell",
        "axis_manager"
    ],
    protected_paths: [
        "/system/bin/",
        "/axis/core/"
    ],
    // The handshake marker is derived from the baseline with a secret (AXIS_SWEEP_SECRET); no token is stored in this file.
    trustedMarker() {
        return CryptoVault.getTrustedMarker({ version: this.version, services: this.authorized_services });
    }
};
