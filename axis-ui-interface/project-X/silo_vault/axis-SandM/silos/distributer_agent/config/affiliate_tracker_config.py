class AffiliateTrackerConfig:
    def __init__(self):
        # Operational parameters for the Affiliate Tracker
        self.COMMISSION_RATE = 0.05
        self.VERIFICATION_MODE = "strict"
        
        # Partner management settings
        self.MAX_PAYOUT_LIMIT = 5000.00
        self.ENABLE_FRAUD_DETECTION = True
