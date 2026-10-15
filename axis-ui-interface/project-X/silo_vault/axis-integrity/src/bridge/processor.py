# PROCESSOR: The Throughput Brain.
# Purpose: Orchestrates the transfer by validating the config and using the tool.
import processor_tool as tool


def process_stream(data):
    """Refuses nothing silently: no data is an ERROR; anything else is judged by the tool (type, size) and staged in the bridge buffer. -> the tool's result."""
    if data is None or (hasattr(data, "__len__") and len(data) == 0):
        return {"status": "ERROR", "reason": "NO_DATA"}
    return tool.execute_stream(data)
