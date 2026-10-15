# Final Copy: The Buffer Configuration
class BufferConfig:
    def get_buffer_settings(self):
        """Defines the memory constraints and throughput limits."""
        return {
            "max_capacity": 1024,
            "overflow_strategy": "DROP_OLDEST"
        }