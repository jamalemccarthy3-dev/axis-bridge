
# silo_stocks/config/silo_params.py
from config.silo_params import SiloParams
# Stocks engine now locked at 1.2 priority
impact = SiloParams().get_weights()["stocks"]
