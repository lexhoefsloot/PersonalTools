#!/usr/bin/env python3
"""
Calendar Permission Fix Utility

This script helps diagnose and fix permission issues with accessing 
the macOS Calendar app from the Calendar Screenshot Analyzer.
"""

import subprocess
import os
import sys
import platform
import time
import webbrowser
from datetime import datetime, timedelta

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*80)
    print(f" {text} ".center(80, "="))
    print("="*80 + "\n")

def print_step(step_num, text):
    """Print a step instruction"""
    print(f"\n[Step {step_num}] {text}")

def run_applescript(script):
    """Run an AppleScript and return the result"""
    try:
        process = subprocess.Popen(['osascript', '-e', script], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE,
                                   text=True)
        stdout, stderr = process.communicate()
        
        return {
            'success': process.returncode == 0,
            'stdout': stdout.strip(),
            'stderr': stderr.strip(),
            'returncode': process.returncode
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'returncode': -1
        }

def open_security_preferences():
    """Open the Security & Privacy preferences panel"""
    privacy_script = '''
    tell application "System Preferences"
        activate
        set current pane to pane "com.apple.preference.security"
        delay 1
        tell application "System Events"
            tell process "System Preferences"
                delay 1
                try
                    click tab group 1 of window 1
                    click radio button "Privacy" of tab group 1 of window 1
                    delay 0.5
                    select row "Automation" of outline 1 of scroll area 1 of tab group 1 of window 1
                on error
                    display dialog "Please navigate to Privacy > Automation in Security & Privacy preferences." buttons {"OK"} default button "OK"
                end try
            end tell
        end tell
    end tell
    '''
    try:
        subprocess.run(['osascript', '-e', privacy_script], capture_output=True, text=True)
    except:
        # If the AppleScript fails, just open System Preferences manually
        subprocess.run(['open', '/System/Applications/System Preferences.app'])

def check_calendar_access():
    """Check if this application has permission to access Calendar"""
    test_script = '''
    tell application "Calendar"
        try
            get name of calendars
            return "Access granted"
        on error errMsg
            return "Access denied: " & errMsg
        end try
    end tell
    '''
    
    result = run_applescript(test_script)
    return result

def test_calendar_event_access(calendar_id=None):
    """Test if we can access events in a specific calendar or any calendar"""
    
    # First make sure Calendar app is running
    activate_script = '''
    tell application "Calendar"
        activate
    end tell
    '''
    run_applescript(activate_script)
    time.sleep(1)
    
    # Now try to access calendars
    if calendar_id:
        # Test a specific calendar
        test_script = f'''
        tell application "Calendar"
            try
                set cal to first calendar whose id is "{calendar_id}"
                set eventCount to count of events of cal
                return "Successfully accessed " & eventCount & " events in calendar " & name of cal
            on error errMsg
                return "Error accessing calendar: " & errMsg
            end try
        end tell
        '''
    else:
        # Just try to list all calendars
        test_script = '''
        tell application "Calendar"
            try
                set calList to every calendar
                set calNames to ""
                repeat with c in calList
                    set calNames to calNames & name of c & ", "
                end repeat
                return "Found calendars: " & calNames
            on error errMsg
                return "Error listing calendars: " & errMsg
            end try
        end tell
        '''
    
    result = run_applescript(test_script)
    return result

def fix_calendar_files():
    """Fix common issues with Calendar files by resetting caches"""
    print("Attempting to fix Calendar caches...")
    
    # Define the path to the Calendar cache files
    cache_path = os.path.expanduser("~/Library/Calendars/Calendar Cache")
    
    if os.path.exists(cache_path):
        try:
            backup_path = f"{cache_path}_backup_{int(time.time())}"
            os.rename(cache_path, backup_path)
            print(f"✓ Moved Calendar cache to backup: {backup_path}")
            print("  Calendar will rebuild its cache the next time it launches.")
        except Exception as e:
            print(f"× Error moving Calendar cache: {e}")
    else:
        print("× Calendar cache directory not found at expected location.")

def main():
    """Main function to run the Calendar permission fix utility"""
    print_header("Calendar Permission Fix Utility")
    
    # Check if running on macOS
    if platform.system() != "Darwin":
        print("This utility only works on macOS.")
        sys.exit(1)
    
    print("This utility will help diagnose and fix permission issues with accessing")
    print("the macOS Calendar app from the Calendar Screenshot Analyzer.")
    print("\nMake sure that:")
    print("1. You have the Calendar app installed and set up with your accounts")
    print("2. You're running this from the same account that will run the app")
    
    input("\nPress Enter to begin...")
    
    # Step 1: Test basic Calendar access
    print_step(1, "Testing basic Calendar access...")
    cal_access = check_calendar_access()
    
    if cal_access['success'] and "Access granted" in cal_access['stdout']:
        print("✓ Basic Calendar access is working!")
    else:
        print("× Calendar access is denied. Error message:")
        if 'stdout' in cal_access and cal_access['stdout']:
            print(f"  {cal_access['stdout']}")
        if 'stderr' in cal_access and cal_access['stderr']:
            print(f"  {cal_access['stderr']}")
        
        print("\nYou need to grant permission for Terminal (or the app running this script)")
        print("to access the Calendar app.")
        
        print_step(2, "Opening Security & Privacy preferences...")
        print("Please follow these steps:")
        print("1. In the System Preferences window that opens, click on the 'Privacy' tab")
        print("2. Scroll down and select 'Automation' in the left sidebar")
        print("3. Find 'Terminal' or the app running this script in the right panel")
        print("4. Check the box next to 'Calendar' to allow access")
        print("5. You may need to close and reopen Terminal/the app")
        
        # Open Security & Privacy preferences
        open_security_preferences()
        
        input("\nAfter granting permission, press Enter to test again...")
        
        # Test again
        cal_access = check_calendar_access()
        if cal_access['success'] and "Access granted" in cal_access['stdout']:
            print("✓ Basic Calendar access is now working!")
        else:
            print("× Calendar access is still denied.")
            print("  Please try running this script again after granting permissions.")
            sys.exit(1)
    
    # Step 3: Test Event Access
    print_step(3, "Testing Calendar event access...")
    event_access = test_calendar_event_access()
    
    if event_access['success'] and not "Error" in event_access['stdout']:
        print("✓ Calendar event access working!")
        print(f"  {event_access['stdout']}")
    else:
        print("× Error accessing calendar events:")
        if 'stdout' in event_access and event_access['stdout']:
            print(f"  {event_access['stdout']}")
        if 'stderr' in event_access and event_access['stderr']:
            print(f"  {event_access['stderr']}")
        
        # Try to fix Calendar caches
        print_step(4, "Attempting to fix Calendar caches...")
        fix_calendar_files()
        
        print("\nNow we need to ensure the Terminal has full access to the Calendar app.")
        print("1. Please open Calendar app manually")
        print("2. Make sure it's fully loaded")
        
        input("Press Enter after opening Calendar app...")
        
        # Run Calendar app
        subprocess.run(['open', '-a', 'Calendar'])
        time.sleep(2)
        
        print("\nNow we'll try to access Calendar events again...")
        event_access = test_calendar_event_access()
        
        if event_access['success'] and not "Error" in event_access['stdout']:
            print("✓ Calendar event access now working!")
            print(f"  {event_access['stdout']}")
        else:
            print("× Still having issues with Calendar access.")
            print("  The application might need to be given explicit permission.")
            
            # Create and open a small helper app to request Calendar access
            print_step(5, "Creating a helper app to request Calendar access...")
            helper_script = '''
            import subprocess
            
            script = """
            tell application "Calendar"
                return name of every calendar
            end tell
            """
            
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
            print("Calendars found:", result.stdout)
            
            input("Press Enter to close this window...")
            '''
            
            helper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'calendar_helper.py')
            with open(helper_path, 'w') as f:
                f.write(helper_script)
            
            print("Running helper app to request Calendar permissions...")
            print("If you see a permission dialog, click 'OK' to allow access.")
            
            # Run the helper
            subprocess.run([sys.executable, helper_path])
            
            # Test again
            print("\nTesting Calendar access one more time...")
            event_access = test_calendar_event_access()
            
            if event_access['success'] and not "Error" in event_access['stdout']:
                print("✓ Calendar event access now working!")
                print(f"  {event_access['stdout']}")
            else:
                print("× Still experiencing issues. Please try the following:")
                print("  1. Restart your computer")
                print("  2. Open Calendar app and make sure it's working")
                print("  3. Run this fix utility again")
                print("  4. If still not working, check for any macOS updates")
    
    # Update the apple_calendars.json file to fix the calendar IDs
    print_step(6, "Updating calendar data file...")
    
    # Get real calendar IDs - using a simpler approach less likely to trigger AppleEvent handler error
    get_real_ids_script = '''
    tell application "Calendar"
        set calNames to ""
        set calList to every calendar
        repeat with c in calList
            set calName to name of c
            set calNames to calNames & calName & "|"
        end repeat
        return calNames
    end tell
    '''
    
    real_ids_result = run_applescript(get_real_ids_script)
    
    if real_ids_result['success'] and real_ids_result['stdout']:
        # Format of output is name1|name2|name3|...
        calendar_names = real_ids_result['stdout'].split('|')
        
        # Create a manually curated calendar list
        manual_calendars = []
        for i, cal_name in enumerate(calendar_names):
            if not cal_name.strip():
                continue
                
            # Create a safe ID based on the calendar name
            safe_id = cal_name.strip().replace(" ", "-").lower()
            
            calendar = {
                'id': f"apple:{safe_id}",
                'name': cal_name.strip(),
                'description': f"Apple Calendar: {cal_name.strip()}",
                'provider': 'apple'
            }
            
            if i == 0:  # Mark first as primary
                calendar['primary'] = True
                
            manual_calendars.append(calendar)
            print(f"✓ Found calendar: {cal_name.strip()} with ID {safe_id}")
        
        if manual_calendars:
            # Save to the app's data directory
            import json
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'data')
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
                
            cache_file = os.path.join(data_dir, 'apple_calendars.json')
            
            data = {
                'calendars': manual_calendars,
                'timestamp': datetime.now().isoformat(),
                'count': len(manual_calendars),
                'manual': True
            }
            
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            print(f"✓ Updated calendar data with {len(manual_calendars)} calendars")
        else:
            print("× No calendars found. Please make sure Calendar app is set up.")
    else:
        print("× Unable to get calendar names:")
        if 'stdout' in real_ids_result and real_ids_result['stdout']:
            print(f"  {real_ids_result['stdout']}")
        if 'stderr' in real_ids_result and real_ids_result['stderr']:
            print(f"  {real_ids_result['stderr']}")
            
        # As a last resort, create calendars from the list we got in step 3
        print("\nAttempting to create calendar list from previously retrieved names...")
        if event_access['success'] and "Found calendars:" in event_access['stdout']:
            cal_names_str = event_access['stdout'].replace("Found calendars:", "").strip()
            cal_names = [name.strip() for name in cal_names_str.split(",") if name.strip()]
            
            manual_calendars = []
            for i, cal_name in enumerate(cal_names):
                if not cal_name:
                    continue
                    
                # Create a safe ID based on the calendar name
                safe_id = cal_name.replace(" ", "-").lower()
                
                calendar = {
                    'id': f"apple:{safe_id}",
                    'name': cal_name,
                    'description': f"Apple Calendar: {cal_name}",
                    'provider': 'apple'
                }
                
                if i == 0:  # Mark first as primary
                    calendar['primary'] = True
                    
                manual_calendars.append(calendar)
                print(f"✓ Found calendar: {cal_name} with ID {safe_id}")
            
            if manual_calendars:
                # Save to the app's data directory
                import json
                data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'data')
                if not os.path.exists(data_dir):
                    os.makedirs(data_dir)
                    
                cache_file = os.path.join(data_dir, 'apple_calendars.json')
                
                data = {
                    'calendars': manual_calendars,
                    'timestamp': datetime.now().isoformat(),
                    'count': len(manual_calendars),
                    'manual': True
                }
                
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)
                    
                print(f"✓ Updated calendar data with {len(manual_calendars)} calendars")
            else:
                print("× No calendars found from previous step either.")
        else:
            print("× Couldn't extract calendar names from previous step.")
    
    # Conclusion
    print_header("Fix Complete")
    print("Calendar access should now be working properly.")
    print("Please restart your Calendar Screenshot Analyzer application.")
    print("\nIf you still experience issues:")
    print("1. Make sure Calendar app is open when using the analyzer")
    print("2. Check System Preferences > Security & Privacy > Privacy > Automation")
    print("   and ensure all necessary permissions are granted")
    print("3. Consider restarting your computer to clear any permission caches")

if __name__ == "__main__":
    main() 