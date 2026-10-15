import sys
import os

# 1. Path to your search engine
silo_path = r"C:\Users\Jamal\Desktop\axis-bridge\axis-ui-interface\project-X\silo_vault"
sys.path.append(os.path.join(silo_path, "axis-search_engine"))

# 2. Import the module
import search_routing

# 3. Instantiate the class defined in your code
router = search_routing.SearchRouting()

# 4. Use the correct method: route_query
# Updated to run a real web test and print clear diagnostics
test_query = "https://www.google.com"

print("--- RUNNING ROUTING DIAGNOSTIC ---")
print(f"Testing Query: {test_query}")

try:
    # UPDATED: Explicitly setting query_type to 'archive' to match your config
    result = router.route_query(query=test_query, query_type="archive")
    print("\n--- RESPONSE RESULT ---")
    print(result)
except Exception as e:
    print("\n--- TEST FAILED ---")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Details: {e}")