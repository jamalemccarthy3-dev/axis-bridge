# silo_sports/config/silo_params.py
from config.silo_params import SiloParams
# Sports engine now operates at 1.5x priority
impact = SiloParams().get_weights()["sports"]

