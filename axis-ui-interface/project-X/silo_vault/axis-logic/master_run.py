import sys
import os

# the repo root is four folders above this file
REGISTRY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "registry.json"))

# Ensure the root folder is in the search path for consistent imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from operations import build_governor
from operations import bridge_connector
from operations import session_manager
from operations import integrity_checker
from operations import dispatcher
from operations import task_scheduler
from operations import stream_processor
from operations import status_reporter
from operations import feedback_loop
from operations import emergency_halt

def run_full_suite():
    print("--- Initiating Full System Orchestration ---")
    
    # 1. Initialization and Governance
    gov = build_governor.BuildGovernor("operations/config/build_governor_config.py")
    bridge = bridge_connector.BridgeConnector("operations/config/bridge_connector_config.py")
    bridge.establish_link("vault_processor")
    
    # 2. Management and Integrity
    session = session_manager.SessionManager("operations/config/session_manager_config.py")
    sid = session.create_session("admin_user_01")
    session.validate_session(sid)
    
    checker = integrity_checker.IntegrityChecker("operations/config/integrity_checker_config.py")
    checker.verify_file(REGISTRY_PATH)
    
    # 3. Operations and Dispatch
    disp = dispatcher.Dispatcher("operations/config/dispatcher_config.py")
    disp.route_request("system_sync", {"cmd": "run_protocol"})
    
    # 4. Task Scheduling and Processing
    scheduler = task_scheduler.TaskScheduler("operations/config/task_scheduler_config.py")
    scheduler.schedule_task("system_sync", 1, {"action": "initialize"})
    
    processor = stream_processor.StreamProcessor("operations/config/stream_processor_config.py")
    processor.process_data("channel_01", "raw_sensor_data")
    
    # 5. Reporting and Feedback
    # Initializing StatusReporter
    reporter = status_reporter.StatusReporter("operations/config/status_reporter_config.py")
    report = reporter.generate_report("Full_System_Suite", "OPERATIONAL")
    print(f"Status Report: {report}")
    
    # Initializing FeedbackLoop with full path requirements from your files
    feedback = feedback_loop.FeedbackLoop(
        "operations/config/feedback_loop_config.py", 
        REGISTRY_PATH
    )
    
    # Executing log_feedback to utilize the full loop capabilities
    result = feedback.log_feedback("dispatcher", "success", {"latency": 500})
    print(f"Feedback result: {result}")
    
    # 6. Safety Protocol
    halt = emergency_halt.EmergencyHalt("operations/config/emergency_halt_config.py")
    
    print("--- All Systems Operational ---")

if __name__ == "__main__":
    run_full_suite()