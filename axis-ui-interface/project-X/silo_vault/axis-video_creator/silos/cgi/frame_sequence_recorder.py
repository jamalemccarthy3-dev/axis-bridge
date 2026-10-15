# operations/cgi_silo/com_lib/frame_sequence_recorder.py
from lib.frame_sequence_recorder_tool import frame_sequence_recorder_tool
from config.frame_sequence_recorder_config import frame_sequence_recorder_config

class frame_sequence_recorder:
    def __init__(self):
        self.tool = frame_sequence_recorder_tool(frame_sequence_recorder_config)

    def start_recording(self, session_id):
        """Initializes the frame sequence buffer."""
        return self.tool.begin_capture(session_id)

    def save_frame(self, frame_data):
        """Processes and saves the current frame data."""
        return self.tool.write_frame(frame_data)

if __name__ == "__main__":
    # Test block to verify initialization
    try:
        recorder = frame_sequence_recorder()
        print("Frame sequence recorder initialized successfully.")
    except Exception as e:
        print(f"Test failed with error: {e}")