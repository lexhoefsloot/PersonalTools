#!/usr/bin/env python3
"""
Helper script to fetch Apple calendars.
This will trigger the macOS permission dialog for Calendar access.
"""

import subprocess
import json
import platform
import os
import sys
from datetime import datetime

def fetch_apple_calendars():
    """
    Fetch Apple calendars using AppleScript and save to a JSON file
    """
    print("Checking platform...")
    if platform.system() != 'Darwin':
        print("This script only works on macOS.")
        return False
    
    print("Attempting to access Apple Calendar...")
    
    # AppleScript to get calendars
    script = '''
    try
        tell application "Calendar"
            set calList to {}
            set allCals to every calendar
            repeat with c in allCals
                set calId to id of c
                set calName to name of c
                set end of calList to {id:calId, name:calName}
            end repeat
            return calList
        end tell
    on error errMsg
        return "Error: " & errMsg
    end try
    '''
    
    try:
        # Execute AppleScript and get the output
        print("Running AppleScript... (this may trigger a permission dialog)")
        result = subprocess.run(['osascript', '-e', script], 
                               capture_output=True, text=True, check=True)
        
        if result.stdout.startswith("Error:"):
            print(f"Error: {result.stdout}")
            if "not allowed to send Apple events" in result.stdout or "AppleEvent handler failed" in result.stdout:
                print("\nPermission Error: You need to grant permission to access Calendar.")
                print("Please check 'System Preferences > Security & Privacy > Privacy > Automation'")
                print("Make sure Terminal (or whatever app you're running this from) has access to Calendar.")
            return False
        
        # Parse the output
        calendar_list = []
        
        # Split by closing/opening braces to get individual calendar entries
        raw_entries = result.stdout.replace("}{", "}|{").split("|")
        
        for entry in raw_entries:
            entry = entry.strip()
            if not entry:
                continue
                
            # Extract id and name from the entry
            cal_id = None
            cal_name = None
            
            if "id:" in entry:
                id_part = entry.split("id:")[1].split(",")[0].strip()
                cal_id = id_part
                
            if "name:" in entry:
                name_part = entry.split("name:")[1].split("}")[0].strip()
                cal_name = name_part
                
            if cal_id and cal_name:
                calendar = {
                    'id': f"apple:{cal_id}",  # Prefix with 'apple:' to identify provider
                    'name': cal_name,
                    'description': f"Apple Calendar: {cal_name}",
                    'provider': 'apple'
                }
                calendar_list.append(calendar)
        
        # Add primary label to first calendar if any calendars were found
        if calendar_list:
            calendar_list[0]['primary'] = True
            
        # Save to a JSON file in the app/data directory
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'data')
        
        # Create the data directory if it doesn't exist
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        # Save calendars with timestamp
        timestamp = datetime.now().isoformat()
        data = {
            'calendars': calendar_list,
            'timestamp': timestamp,
            'count': len(calendar_list)
        }
        
        file_path = os.path.join(data_dir, 'apple_calendars.json')
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"Successfully fetched {len(calendar_list)} calendars and saved to {file_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error executing AppleScript: {e}")
        print(f"Error details: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = fetch_apple_calendars()
    sys.exit(0 if success else 1) 