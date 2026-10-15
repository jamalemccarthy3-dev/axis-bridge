# File: attention_context_engine_config.py
class AttentionContextEngineConfig:
    def __init__(self):
        self.num_heads = 8
        self.head_dim = 64
        self.scale = True
        self.use_dropout = True
        self.dropout_rate = 0.1