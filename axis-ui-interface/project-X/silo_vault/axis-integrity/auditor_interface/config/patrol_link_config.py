# PATROL_LINK_CONFIG: The Rules of Engagement
# Purpose: Define patrol frequency and target silos.

PATROL_INTERVAL = 5          # seconds between patrols when run in a loop
TARGET_SILOS = None          # None = every axis-* engine found in the silo; or a list of folder names
STRICT_HEALTH_CHECK = True   # True: an engine must also show a recent pulse to count as alive; False: being present is enough
PULSE_FILE = "system_pulse.log"
PULSE_MAX_AGE_SECONDS = 24 * 3600
