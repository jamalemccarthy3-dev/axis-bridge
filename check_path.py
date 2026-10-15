import os

# Get the current directory the script is running in
current_dir = os.getcwd()
print(f"I am currently looking in: {current_dir}")
print("-" * 30)

# List everything in this folder
print("Contents of this folder:")
for item in os.listdir(current_dir):
    print(f" - {item}")

# Check if the interface folder is here
if os.path.exists("axis-ui-interface"):
    print("-" * 30)
    print("SUCCESS: 'axis-ui-interface' was found in this folder!")
else:
    print("-" * 30)
    print("CRITICAL ERROR: 'axis-ui-interface' is NOT in this folder.")