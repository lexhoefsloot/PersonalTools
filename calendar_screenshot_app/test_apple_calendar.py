import subprocess
import platform
import sys

def test_apple_calendar_access():
    """Test if we can access Apple Calendar via AppleScript"""
    
    print(f"Current platform: {platform.system()}")
    
    if platform.system() != 'Darwin':
        print("Not running on macOS, cannot access Apple Calendar")
        return False
    
    # Simple AppleScript to check if Calendar app is accessible
    script = '''
    try
        tell application "Calendar"
            set calCount to count of calendars
            return "Success: Found " & calCount & " calendars"
        end tell
    on error errMsg
        return "Error: " & errMsg
    end try
    '''
    
    print("Executing test AppleScript...")
    
    try:
        # Execute AppleScript
        result = subprocess.run(['osascript', '-e', script], 
                               capture_output=True, text=True, check=True)
        
        print(f"Return code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        
        if result.stderr:
            print(f"Stderr: {result.stderr}")
        
        if "Success" in result.stdout:
            print("Calendar app is accessible!")
            return True
        else:
            print("Calendar app returned an error or unexpected response")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"Error executing AppleScript: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_apple_calendar_access()
    sys.exit(0 if success else 1) 