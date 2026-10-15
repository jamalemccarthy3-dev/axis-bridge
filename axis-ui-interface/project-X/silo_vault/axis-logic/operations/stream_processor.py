import json

class StreamProcessor:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.active_streams = []

    def process_data(self, stream_id, data_packet):
        if stream_id not in self.config.get('active_channels', []):
            return {"status": "error", "message": "Unauthorized stream ID"}
        
        # Stream processing logic
        processed_data = f"Processed {data_packet}"
        self.active_streams.append(stream_id)
        return {"status": "success", "data": processed_data}