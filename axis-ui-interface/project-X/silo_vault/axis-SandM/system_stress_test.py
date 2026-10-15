from lib.logger_tool import loggertool
from lib.event_bus_tool import eventbus
from lib.security_validator import securityvalidator
from lib.config_loader import configloader

def run_stress_test():
    print("--- Starting Real System Test ---")
    
    # 1. Test Logger
    logger = loggertool()
    logger.info("System boot verified. Starting stress test.")

    # 2. Test Security Validator
    security = securityvalidator()
    if security.validate_access("governor"):
        logger.info("Security check passed for 'governor'.")
    
    # 3. Test Event Bus
    bus = eventbus()
    def sample_callback(data):
        print(f"Event Bus received: {data}")
    
    bus.subscribe("test_event", sample_callback)
    bus.publish("test_event", "Hello, Axis System!")

    # 4. Test Config Loader
    config = configloader()
    result = config.load_config()
    print(f"Configuration Status: {result['status']}")

    print("--- Stress Test Complete ---")

if __name__ == "__main__":
    run_stress_test()

