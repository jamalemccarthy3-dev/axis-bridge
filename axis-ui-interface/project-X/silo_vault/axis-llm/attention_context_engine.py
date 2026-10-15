# File: attention_context_engine.py
import numpy as np
import logging

from config.attention_context_engine_config import AttentionContextEngineConfig

class AttentionContextEngine:
    def __init__(self, config=None):
        self.config = config or AttentionContextEngineConfig()
        self.logger = logging.getLogger("Nexxus.Attention.Engine")

    def compute(self, query, key, value):
        try:
            d_k = query.shape[-1]
            scores = np.matmul(query, key.transpose(-2, -1)) / np.sqrt(d_k)
            weights = self.softmax(scores)
            self.logger.info("Attention context successfully processed in Nexxus.")
            return np.matmul(weights, value)
        except Exception as e:
            self.logger.error(f"Attention computation failure: {e}")
            return None

    def softmax(self, x):
        e_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e_x / np.sum(e_x, axis=-1, keepdims=True)