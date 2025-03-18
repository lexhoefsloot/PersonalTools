#!/usr/bin/env python3
"""
Debug script for diagnosing Calendar access issues.
This script performs multiple tests to identify where the issue might be.
"""

import subprocess
import platform
import sys
import os
import time

def print_section(title):
    """Print a section header for better readability"""
    print("\n" + "=" * 60)
    print(f" {title} ".center(60, "="))
    print("=" * 60)

def run_applescript(script, description):
    """Run an AppleScript and return the result with detailed error reporting"""
    print(f"\nRunning AppleScript: {description}")
    print(f"Script content:\n{script}\n")
    
    try:
        result = subprocess.run(['osascript', '-e', script], 
                               capture_output=True, text=True)
        
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print(f"Stdout: {result.stdout}")
        
        if result.stderr:
            print(f"Stderr: {result.stderr}")
            
        if result.returncode != 0:
            print("ERROR: AppleScript execution failed")
        else:
            print("SUCCESS: AppleScript executed without errors")
            
        return result
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return None

def check_environment():
    """Check the environment for potential issues"""
    print_section("ENVIRONMENT CHECK")
    
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"macOS version: {platform.mac_ver()[0]}")
    print(f"Current user: {os.getlogin()}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Script path: {os.path.abspath(__file__)}")

def test_calendar_app():
    """Test if the Calendar app is running and can be launched"""
    print_section("CALENDAR APP TEST")
    
    # Check if Calendar is running
    ps_script = """
    do shell script "ps aux | grep -v grep | grep Calendar"
    """
    run_applescript(ps_script, "Check if Calendar is running")
    
    # Try to launch Calendar app
    launch_script = """
    tell application "Calendar"
        launch
        delay 1
        if it is running then
            return "Calendar is running"
        else
            return "Calendar failed to launch"
        end if
    end tell
    """
    run_applescript(launch_script, "Launch Calendar app")

def test_calendar_permissions():
    """Test different permission scenarios"""
    print_section("PERMISSIONS TEST")
    
    # Simple test to see if we can get the name of the app
    app_name_script = """
    tell application "Calendar"
        return name
    end tell
    """
    run_applescript(app_name_script, "Get Calendar app name")
    
    # Test if we can get basic calendar info
    calendar_info_script = """
    try
        tell application "Calendar"
            return count of calendars
        end tell
    on error errMsg
        return "Error: " & errMsg
    end try
    """
    run_applescript(calendar_info_script, "Get calendar count")
    
    # More detailed calendar query
    calendar_list_script = """
    try
        tell application "Calendar"
            set calNames to {}
            repeat with c in calendars
                set end of calNames to name of c
            end repeat
            return calNames
        end tell
    on error errMsg
        return "Error: " & errMsg
    end try
    """
    run_applescript(calendar_list_script, "Get calendar names")

def test_alternative_method():
    """Test an alternative method to access calendars"""
    print_section("ALTERNATIVE METHOD TEST")
    
    # Try using 'do shell script' method which uses a different permission model
    alternative_script = """
    set calendars_info to ""
    
    tell application "Calendar"
        set calendars_info to "Calendar count: " & count of calendars
    end tell
    
    return calendars_info
    """
    run_applescript(alternative_script, "Get calendar info using alternative method")
    
    # Try an even more basic test
    basic_script = """
    tell application "Calendar"
        return "Successfully connected to Calendar app"
    end tell
    """
    run_applescript(basic_script, "Basic Calendar connection test")

def main():
    """Main function to run all tests"""
    print_section("CALENDAR ACCESS DEBUG SCRIPT")
    print("This script will perform several tests to diagnose Calendar access issues.")
    print("Please wait while the tests run...")
    
    check_environment()
    test_calendar_app()
    test_calendar_permissions()
    test_alternative_method()
    
    print_section("TESTS COMPLETED")
    print("Check the output above for errors or permission issues.")
    print("If all tests pass but you still can't access calendars, there may be an issue with:")
    print("1. How the permission is being applied")
    print("2. A conflict with another security setting")
    print("3. The specific AppleScript commands being used in your application")

if __name__ == "__main__":
    main() 