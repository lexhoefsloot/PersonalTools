import subprocess
import json
import os
import tempfile
from datetime import datetime, timedelta
import platform
import uuid
from flask import flash
import re
import logging
import sys

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_applescript(script):
    """Run AppleScript and return the result"""
    try:
        process = subprocess.Popen(['osascript', '-e', script], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE,
                                  text=True)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            print(f"AppleScript error: {stderr}")
            return None
        
        return stdout.strip()
    except Exception as e:
        print(f"Error running AppleScript: {e}")
        return None

def get_apple_calendars():
    """
    Get a list of calendars from the macOS Calendar app
    Returns a list of calendar dictionaries with id, name, and description
    """
    print("DEBUG: Starting get_apple_calendars function")
    if platform.system() != 'Darwin':
        print("DEBUG: Not running on macOS, returning empty list")
        return []
    
    print("DEBUG: Running on macOS, continuing with Apple Calendar access")
    
    # First, try to load from cached JSON file
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'app', 'data')
    cache_file = os.path.join(data_dir, 'apple_calendars.json')
    
    if os.path.exists(cache_file):
        try:
            print(f"DEBUG: Found cached calendar data at {cache_file}")
            with open(cache_file, 'r') as f:
                data = json.load(f)
                
            # Always use manual data if available (bypassing AppleScript)
            if data.get('manual', False):
                print(f"DEBUG: Using manual calendar data with {len(data['calendars'])} calendars")
                return data['calendars']
            
            # Check if data is still fresh (less than 1 day old)
            cached_time = datetime.fromisoformat(data.get('timestamp', '2000-01-01'))
            time_diff = datetime.now() - cached_time
            
            if time_diff.days < 1 and data.get('calendars') and not data.get('is_sample', False):
                print(f"DEBUG: Using cached data with {len(data['calendars'])} calendars")
                return data['calendars']
            else:
                print("DEBUG: Cached data is too old, sample data, or empty - fetching fresh data")
        except Exception as e:
            print(f"DEBUG: Error reading cached calendar data: {e}")
    else:
        print(f"DEBUG: No cached calendar data found at {cache_file}")
        # Create data directory if it doesn't exist
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
    
    # Sample data to use if unable to fetch from Calendar app
    sample_calendars = [
        {
            'id': 'apple:sample1',
            'name': 'Sample Calendar 1',
            'description': 'Sample calendar 1 (not connected to actual Calendar app)',
            'provider': 'apple',
            'primary': True
        },
        {
            'id': 'apple:sample2',
            'name': 'Sample Calendar 2',
            'description': 'Sample calendar 2 (not connected to actual Calendar app)',
            'provider': 'apple'
        }
    ]
    
    # AppleScript to get list of calendars
    script = '''
    set calendarList to ""
    
    tell application "Calendar"
        set calList to every calendar
        repeat with aCal in calList
            set calendarName to name of aCal
            set calendarId to id of aCal
            set calendarList to calendarList & "{name:" & calendarName & ", id:" & calendarId & "}, "
        end repeat
    end tell
    
    return calendarList
    '''
    
    try:
        # Execute AppleScript and get the output
        print("DEBUG: Executing AppleScript to get calendars")
        result = subprocess.run(['osascript', '-e', script], 
                               capture_output=True, text=True, check=True)
        
        output = result.stdout.strip()
        
        # If there's an error in the output
        if output.startswith("Error:"):
            print(f"DEBUG: Error in AppleScript output: {output}")
            # Save sample data to cache
            sample_data = {
                'calendars': sample_calendars,
                'timestamp': datetime.now().isoformat(),
                'count': len(sample_calendars),
                'is_sample': True
            }
            
            try:
                with open(cache_file, 'w') as f:
                    json.dump(sample_data, f, indent=2)
                print(f"DEBUG: Saved sample data to cache file")
            except Exception as e:
                print(f"DEBUG: Error saving sample data to cache: {e}")
                
            return sample_calendars
        
        # Parse the output to get calendar list
        calendar_list = []
        
        # The output is a series of {name:X, id:Y} records 
        # Parse these by splitting correctly on record boundaries
        
        # Split the output into individual calendar records
        # First clean up the output by removing outer braces if present
        if output.startswith("{") and output.endswith("}"):
            output = output[1:-1]
            
        # Split on "}, {" to get individual records
        raw_entries = output.replace("}, {", "}|{").split("|")
        print(f"DEBUG: Found {len(raw_entries)} calendar entries in output")
        
        for i, entry in enumerate(raw_entries):
            entry = entry.strip()
            if not entry:
                continue
                
            # Extract name and id from each record
            # Example format: {name:CalName, id:CalID}
            name = None
            cal_id = None
            
            if "name:" in entry and "id:" in entry:
                # Extract name
                name_start = entry.find("name:") + 5
                name_end = entry.find(", id:")
                if name_end == -1:  # If id: comes before name:
                    name_end = entry.find("}")
                
                if name_start > 5 and name_end > name_start:
                    name = entry[name_start:name_end].strip()
                
                # Extract id
                id_start = entry.find("id:") + 3
                id_end = entry.find(", name:")
                if id_end == -1:  # If name: comes before id:
                    id_end = entry.find("}")
                
                if id_start > 3 and id_end > id_start:
                    cal_id = entry[id_start:id_end].strip()
            
            if name and cal_id:
                calendar = {
                    'id': f"apple:{cal_id}",
                    'name': name,
                    'description': f"Apple Calendar: {name}",
                    'provider': 'apple'
                }
                
                if i == 0:  # Mark first calendar as primary
                    calendar['primary'] = True
                    
                calendar_list.append(calendar)
                print(f"DEBUG: Added calendar: {calendar['name']} with ID {calendar['id']}")
        
        # Save to cache file
        if calendar_list:
            timestamp = datetime.now().isoformat()
            data = {
                'calendars': calendar_list,
                'timestamp': timestamp,
                'count': len(calendar_list)
            }
            
            try:
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"DEBUG: Saved {len(calendar_list)} calendars to cache file")
            except Exception as e:
                print(f"DEBUG: Error saving to cache file: {e}")
        
        print(f"DEBUG: Final calendar list has {len(calendar_list)} calendars")
        return calendar_list
        
    except subprocess.CalledProcessError as e:
        print(f"DEBUG: AppleScript error: {e.stderr}")
        
        # Check for permission errors
        if "not allowed to send Apple events" in e.stderr or "AppleEvent handler failed" in e.stderr:
            print("\nDEBUG: Permission Error: You need to grant permission to access Calendar.")
            print("DEBUG: Please check 'System Preferences > Security & Privacy > Privacy > Automation'")
            print("DEBUG: Make sure Terminal (or whatever app you're running this from) has access to Calendar.")
        
        # Save sample data to cache
        sample_data = {
            'calendars': sample_calendars,
            'timestamp': datetime.now().isoformat(),
            'count': len(sample_calendars),
            'is_sample': True
        }
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(sample_data, f, indent=2)
            print(f"DEBUG: Saved sample data to cache file due to error")
        except Exception as cache_err:
            print(f"DEBUG: Error saving sample data to cache: {cache_err}")
            
        return sample_calendars
        
    except Exception as e:
        print(f"DEBUG: General error getting calendars: {e}")
        
        # Save sample data to cache
        sample_data = {
            'calendars': sample_calendars,
            'timestamp': datetime.now().isoformat(),
            'count': len(sample_calendars),
            'is_sample': True
        }
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(sample_data, f, indent=2)
            print(f"DEBUG: Saved sample data to cache file due to error")
        except Exception as cache_err:
            print(f"DEBUG: Error saving sample data to cache: {cache_err}")
            
        return sample_calendars

def format_date_for_applescript(date):
    """Format a Python datetime object for AppleScript"""
    return date.strftime("%Y-%m-%d %H:%M:%S")

def get_apple_events(calendars, start_time, end_time, timezone=None):
    """
    Get events from Apple Calendar for the specified calendars and time range
    
    Args:
        calendars: List of calendar dictionaries with ids
        start_time: Start datetime
        end_time: End datetime
        timezone: Optional timezone string
        
    Returns:
        List of event dictionaries
    """
    print(f"DEBUG: Getting Apple events from {start_time} to {end_time}")
    
    if platform.system() != 'Darwin' or not calendars:
        print("DEBUG: Not on macOS or no calendars provided")
        return []
    
    # Generate some sample events if we're using sample calendars
    if any(cal['id'].startswith('apple:sample') for cal in calendars):
        print("DEBUG: Using sample calendars, but not generating sample events")
        return []
    
    # Now check the actual calendar IDs we have
    print(f"DEBUG: Checking calendar IDs: {calendars}")
    
    # Format dates for AppleScript
    start_date_str = start_time.strftime('%d/%m/%y %H:%M:%S')  # Short day/month/year format
    end_date_str = end_time.strftime('%d/%m/%y %H:%M:%S')
    
    # Extract calendar names from the list
    calendar_names = []
    for cal in calendars:
        if cal['id'].startswith('apple:'):
            calendar_names.append(cal['name'])
    
    if not calendar_names:
        print("DEBUG: No valid Apple calendar names found")
        return []
    
    calendar_names_str = ", ".join(f'"{name}"' for name in calendar_names)
    print(f"DEBUG: Calendar names for AppleScript: {calendar_names_str}")
    
    # Let's first try a very simple AppleScript to test if Calendar access works
    test_script = '''
    tell application "Calendar"
        return "Calendar access works"
    end tell
    '''
    
    try:
        print("DEBUG: Testing basic Calendar access...")
        test_result = subprocess.run(['osascript', '-e', test_script], 
                                   capture_output=True, text=True, check=True)
        print(f"DEBUG: Test result: {test_result.stdout.strip()}")
    except Exception as e:
        print(f"DEBUG: Test failed: {e}")
        print("DEBUG: Calendar access failed, returning empty events list")
        return []
    
    # Now let's try a very simple event query on the first calendar
    if calendar_names:
        first_cal_name = calendar_names[0]
        test_event_script = f'''
        set eventCount to 0
        
        tell application "Calendar"
            try
                set theCal to first calendar whose name is "{first_cal_name}"
                set eventCount to count of events of theCal
                return "Found " & eventCount & " events in calendar " & name of theCal
            on error errMsg
                return "Error: " & errMsg
            end try
        end tell
        '''
        
        try:
            print(f"DEBUG: Testing event count for calendar name '{first_cal_name}'...")
            test_event_result = subprocess.run(['osascript', '-e', test_event_script], 
                                             capture_output=True, text=True, check=True)
            print(f"DEBUG: Test event result: {test_event_result.stdout.strip()}")
        except Exception as e:
            print(f"DEBUG: Test event query failed: {e}")
    
    # Optimized AppleScript to get events - uses a more efficient approach to limit event search
    # Format dates in a way that AppleScript can reliably parse
    start_date_str = start_time.strftime('%d/%m/%y %H:%M:%S')  # Short day/month/year format
    end_date_str = end_time.strftime('%d/%m/%y %H:%M:%S')
    
    # Debug dates before passing to AppleScript
    print(f"DEBUG: Date range for AppleScript: {start_date_str} to {end_date_str}")
    
    script = f'''
    try
        -- Convert date strings to AppleScript dates using explicit coercion
        set theStartDate to date "{start_date_str}"
        set theEndDate to date "{end_date_str}"
        
        log "Start date: " & theStartDate as string
        log "End date: " & theEndDate as string
        
        -- Ensure end date is not before start date
        if theEndDate < theStartDate then
            log "Error: End date is before start date, swapping dates"
            set tempDate to theStartDate
            set theStartDate to theEndDate
            set theEndDate to tempDate
        end if
        
        tell application "Calendar"
            set eventList to ""
            set maxEventsPerCalendar to 30 -- Limit to prevent slowdowns with massive calendars
            
            repeat with calName in {{{calendar_names_str}}}
                try
                    set theCal to first calendar whose name is calName
                    log "Processing calendar: " & name of theCal
                    
                    -- For performance, limit the search to a smaller window
                    set searchStart to theStartDate - (1 * days)
                    set searchEnd to theEndDate + (1 * days)
                    
                    -- Get events in the search window
                    set theEvents to (every event of theCal whose start date ≥ searchStart and start date ≤ searchEnd)
                    
                    -- Take at most maxEventsPerCalendar
                    if (count of theEvents) > maxEventsPerCalendar then
                        set eventsCount to maxEventsPerCalendar
                    else
                        set eventsCount to count of theEvents
                    end if
                    
                    log "Found " & (count of theEvents) & " events, processing up to " & eventsCount
                    
                    repeat with i from 1 to eventsCount
                        try
                            set anEvent to item i of theEvents
                            set evtId to uid of anEvent
                            set evtTitle to summary of anEvent
                            set evtStart to start date of anEvent
                            set evtEnd to end date of anEvent
                            set evtLocation to location of anEvent
                            
                            log "Processing event: " & evtTitle
                            
                            -- Use basic delimiters that won't appear in the data
                            set eventData to evtId & "||SEP||" & evtTitle & "||SEP||" & (evtStart as string) & "||SEP||" & (evtEnd as string) & "||SEP||" & evtLocation & "||SEP||" & calName
                            set eventList to eventList & eventData & "||EVENT||"
                        on error errMsg
                            log "Error processing event: " & errMsg
                        end try
                    end repeat
                on error errMsg
                    log "Error with calendar " & calName & ": " & errMsg
                end try
            end repeat
            
            return eventList
        end tell
    on error errorMsg
        log "AppleScript error: " & errorMsg
        return "ERROR: " & errorMsg
    end try
    '''
    
    # Also write this script to a temporary file for easier debugging
    with tempfile.NamedTemporaryFile(delete=False, suffix='.scpt', mode='w') as f:
        script_file = f.name
        f.write(script)
    
    print(f"DEBUG: Wrote AppleScript to temporary file: {script_file}")
    
    try:
        # Execute AppleScript
        print("DEBUG: Executing AppleScript to get events")
        print("DEBUG: Script contents:")
        print(script)
        
        # Try both methods: inline script and script file
        try:
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True, check=True)
            print(f"DEBUG: Execution via inline script successful")
        except Exception as e:
            print(f"DEBUG: Execution via inline script failed: {e}")
            print(f"DEBUG: Trying script file...")
            result = subprocess.run(['osascript', script_file], 
                                  capture_output=True, text=True, check=True)
        
        # Delete the temp script file
        try:
            os.unlink(script_file)
        except:
            pass
        
        output = result.stdout.strip()
        stderr = result.stderr if hasattr(result, 'stderr') else ""
        
        print(f"DEBUG: AppleScript stdout received: {len(output)} characters")
        print(f"DEBUG: AppleScript stderr received: {len(stderr)} characters")
        
        # If stderr has content, print it for debugging
        if stderr:
            print(f"DEBUG: AppleScript stderr: {stderr}")
        
        # If we actually got no events (empty string)
        if not output or output == "":
            print("DEBUG: No events found or empty output")
            return []
        
        # Show a sample of the output for debugging
        if len(output) > 200:
            print(f"DEBUG: Output sample: {output[:200]}...")
        else:
            print(f"DEBUG: Complete output: {output}")
        
        # Parse the AppleScript output to extract events
        events = []
        
        # Split output by event delimiter
        raw_events = output.split("||EVENT||")
        print(f"DEBUG: Found {len(raw_events)} event entries in output")
        
        for entry in raw_events:
            entry = entry.strip()
            if not entry:
                continue
            
            # Split each event by field delimiter
            fields = entry.split("||SEP||")
            if len(fields) < 6:
                print(f"DEBUG: Skipping incomplete event: {entry}")
                continue
            
            try:
                event_id, title, start_date, end_date, location, calendar_name = fields
                
                # Parse the date strings, which now have a string format like
                # "Tuesday, September 19, 2023 at 8:00:00 AM"
                try:
                    # Parse AppleScript date string format - multiple possible formats
                    if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', start_date):
                        # MM/DD/YY format
                        start_dt = datetime.strptime(start_date, '%m/%d/%y %H:%M:%S')
                    elif re.search(r'\w+, \w+ \d{1,2}, \d{4}', start_date):
                        # "Tuesday, September 19, 2023 at 8:00:00 AM" format
                        start_match = re.search(r'(\w+), (\w+) (\d{1,2}), (\d{4}) at (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)', start_date)
                        if start_match:
                            month = start_match.group(2)
                            day = int(start_match.group(3))
                            year = int(start_match.group(4))
                            hour = int(start_match.group(5))
                            minute = int(start_match.group(6))
                            second = int(start_match.group(7))
                            ampm = start_match.group(8)
                            
                            # Convert 12-hour to 24-hour
                            if ampm == 'PM' and hour < 12:
                                hour += 12
                            elif ampm == 'AM' and hour == 12:
                                hour = 0
                                
                            # Convert month name to number
                            month_num = {
                                'January': 1, 'February': 2, 'March': 3, 'April': 4,
                                'May': 5, 'June': 6, 'July': 7, 'August': 8,
                                'September': 9, 'October': 10, 'November': 11, 'December': 12
                            }.get(month, 1)
                            
                            start_dt = datetime(year, month_num, day, hour, minute, second)
                        else:
                            # Fallback - try direct parsing
                            start_dt = datetime.now()
                            print(f"DEBUG: Could not parse date: {start_date}")
                    else:
                        # Try standard ISO format as fallback
                        start_dt = datetime.fromisoformat(start_date)
                except Exception as e:
                    print(f"DEBUG: Error parsing start date '{start_date}': {e}")
                    continue
                    
                # End time parsing with same approach
                try:
                    # Parse AppleScript date string format - multiple possible formats
                    if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', end_date):
                        # MM/DD/YY format
                        end_dt = datetime.strptime(end_date, '%m/%d/%y %H:%M:%S')
                    elif re.search(r'\w+, \w+ \d{1,2}, \d{4}', end_date):
                        # "Tuesday, September 19, 2023 at 8:00:00 AM" format
                        end_match = re.search(r'(\w+), (\w+) (\d{1,2}), (\d{4}) at (\d{1,2}):(\d{2}):(\d{2}) (AM|PM)', end_date)
                        if end_match:
                            month = end_match.group(2)
                            day = int(end_match.group(3))
                            year = int(end_match.group(4))
                            hour = int(end_match.group(5))
                            minute = int(end_match.group(6))
                            second = int(end_match.group(7))
                            ampm = end_match.group(8)
                            
                            # Convert 12-hour to 24-hour
                            if ampm == 'PM' and hour < 12:
                                hour += 12
                            elif ampm == 'AM' and hour == 12:
                                hour = 0
                                
                            # Convert month name to number
                            month_num = {
                                'January': 1, 'February': 2, 'March': 3, 'April': 4,
                                'May': 5, 'June': 6, 'July': 7, 'August': 8,
                                'September': 9, 'October': 10, 'November': 11, 'December': 12
                            }.get(month, 1)
                            
                            end_dt = datetime(year, month_num, day, hour, minute, second)
                        else:
                            # Fallback - try direct parsing
                            end_dt = datetime.now() + timedelta(hours=1)
                            print(f"DEBUG: Could not parse date: {end_date}")
                    else:
                        # Try standard ISO format as fallback
                        end_dt = datetime.fromisoformat(end_date)
                except Exception as e:
                    print(f"DEBUG: Error parsing end date '{end_date}': {e}")
                    continue
                
                # Create a safe ID for the calendar
                safe_cal_id = re.sub(r'[^\w\s-]', '', calendar_name).strip().replace(' ', '-').lower()
                
                # Create the event dictionary
                event_dict = {
                    'id': event_id,
                    'title': title,
                    'start': start_dt.isoformat(),
                    'end': end_dt.isoformat(),
                    'location': location,
                    'calendar_id': f"apple:{safe_cal_id}",
                    'provider': 'apple'
                }
                
                events.append(event_dict)
                print(f"DEBUG: Added event: {event_dict['title']} ({event_dict['start']} - {event_dict['end']}) from calendar: {event_dict['calendar_id']}")
                sys.stdout.flush()
            except Exception as e:
                print(f"DEBUG: Error parsing event: {e} - Data: {entry}")
                continue
        
        print(f"DEBUG: Successfully parsed {len(events)} events")
        
        # If no events found or parsing failed, return empty list
        if not events:
            print("DEBUG: No events found or failed to parse events, returning empty list")
            return []
            
        return events
    
    except subprocess.CalledProcessError as e:
        print(f"DEBUG: AppleScript error getting events: {e.stderr if hasattr(e, 'stderr') else str(e)}")
        return []
    
    except Exception as e:
        print(f"DEBUG: General error getting events: {e}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return [] 