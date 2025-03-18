#!/usr/bin/env python3
"""
Simple script to force the Calendar permission dialog to appear.
"""
import subprocess
import time

print("This script will attempt to access the Calendar app to trigger the permission dialog.")
print("When the permission dialog appears, select 'OK' to grant access.")
print("Launching in 3 seconds...")
time.sleep(3)

# The simplest possible script to trigger the permission dialog
script = '''
tell application "Calendar"
    get name of calendars
end tell
'''

try:
    subprocess.run(['osascript', '-e', script], check=True)
    print("Success! Permission granted. You can now use the calendar features in the app.")
except Exception as e:
    print(f"Error: {e}")
    print("Please try again and make sure to grant permission when the dialog appears.") 