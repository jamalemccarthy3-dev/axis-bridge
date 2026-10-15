# silo_ecom/config/silo_params.py
from config.silo_params import SiloParams
# Econ engine now operating at 0.8 priority
impact = SiloParams().get_weights()["econ"]
