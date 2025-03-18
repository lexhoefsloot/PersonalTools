import subprocess
import json
import os
import tempfile
from datetime import datetime, timedelta
import platform
import uuid

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
    if platform.system() != 'Darwin':
        return []
    
    # AppleScript to get calendars
    script = '''
    tell application "Calendar"
        set calendarList to {}
        set allCalendars to every calendar
        repeat with cal in allCalendars
            set calName to name of cal
            set calId to id of cal
            set calInfo to {id:calId, name:calName}
            copy calInfo to end of calendarList
        end repeat
        return calendarList
    end tell
    '''
    
    try:
        # Execute AppleScript and get the output
        result = subprocess.run(['osascript', '-e', script], 
                               capture_output=True, text=True, check=True)
        
        # Parse the output
        calendar_list = []
        
        # Parse the AppleScript output
        lines = result.stdout.strip().split(', ')
        current_calendar = {}
        
        for line in lines:
            if 'id:' in line and 'name:' not in line:
                if current_calendar and 'id' in current_calendar:
                    calendar_list.append(current_calendar)
                current_calendar = {'id': line.split('id:')[1].strip(), 'provider': 'apple'}
            elif 'name:' in line and 'id:' not in line:
                current_calendar['name'] = line.split('name:')[1].strip()
                current_calendar['description'] = f"Apple Calendar: {current_calendar['name']}"
                calendar_list.append(current_calendar)
                current_calendar = {}
            elif 'id:' in line and 'name:' in line:
                parts = line.split(', ')
                id_part = next((p for p in parts if 'id:' in p), None)
                name_part = next((p for p in parts if 'name:' in p), None)
                
                if id_part and name_part:
                    cal_id = id_part.split('id:')[1].strip()
                    cal_name = name_part.split('name:')[1].strip()
                    calendar_list.append({
                        'id': cal_id,
                        'name': cal_name,
                        'description': f"Apple Calendar: {cal_name}",
                        'provider': 'apple'
                    })
        
        # Add primary label to first calendar
        if calendar_list:
            calendar_list[0]['primary'] = True
            
        return calendar_list
    except subprocess.CalledProcessError:
        return []
    except Exception as e:
        print(f"Error getting Apple calendars: {e}")
        return []

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
    if platform.system() != 'Darwin' or not calendars:
        return []
    
    # Format dates for AppleScript
    start_date_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
    end_date_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Get calendar IDs from the list
    calendar_ids = [cal['id'] for cal in calendars]
    calendar_ids_str = ", ".join(f'"{cal_id}"' for cal_id in calendar_ids)
    
    # AppleScript to get events
    script = f'''
    set startDate to (current date) - (time to GMT)
    set startDate to startDate + (time to GMT)
    set endDate to (current date) - (time to GMT)
    set endDate to endDate + (time to GMT)
    
    set theStartDate to date "{start_date_str}"
    set theEndDate to date "{end_date_str}"
    
    set calendarIds to {{{calendar_ids_str}}}
    set eventList to {{}}
    
    tell application "Calendar"
        repeat with calId in calendarIds
            try
                set theCal to first calendar whose id is calId
                set theEvents to every event of theCal whose start date is greater than or equal to theStartDate and start date is less than or equal to theEndDate
                
                repeat with evt in theEvents
                    set evtId to uid of evt
                    set evtTitle to summary of evt
                    set evtStart to start date of evt
                    set evtEnd to end date of evt
                    set evtLocation to location of evt
                    set evtCalId to calId
                    
                    set eventInfo to {{id:evtId, title:evtTitle, start:evtStart, end:evtEnd, location:evtLocation, calendarId:evtCalId}}
                    copy eventInfo to end of eventList
                end repeat
            on error errMsg
                -- Just skip the calendar if there's an error
            end try
        end repeat
        return eventList
    end tell
    '''
    
    try:
        # Execute AppleScript
        result = subprocess.run(['osascript', '-e', script], 
                               capture_output=True, text=True, check=True)
        
        # Parse the output to create event objects
        events = []
        
        # Parse the complex AppleScript output
        output = result.stdout.strip()
        
        # Create a temporary JSON file to make parsing easier
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp:
            temp_path = temp.name
            
            # Convert AppleScript output to JSON-like format
            output = output.replace('id:', '"id":"').replace(', title:', '", "title":"')
            output = output.replace(', start:', '", "start":"').replace(', end:', '", "end":"')
            output = output.replace(', location:', '", "location":"').replace(', calendarId:', '", "calendarId":"')
            
            # Fix the JSON structure
            entries = output.split('}, {')
            json_events = []
            
            for i, entry in enumerate(entries):
                # Clean up entry
                if i == 0:
                    entry = entry.replace('{', '')
                if i == len(entries) - 1:
                    entry = entry.replace('}', '')
                
                # Further cleanup and formatting
                entry = entry.strip()
                
                # Handle quotes in values
                parts = []
                in_quotes = False
                current_part = ""
                
                for char in entry:
                    if char == '"':
                        in_quotes = not in_quotes
                    
                    if char == ',' and not in_quotes:
                        parts.append(current_part)
                        current_part = ""
                    else:
                        current_part += char
                
                if current_part:
                    parts.append(current_part)
                
                # Create event dictionary
                event_dict = {}
                for part in parts:
                    if ':' in part:
                        key, value = part.split(':', 1)
                        key = key.strip().strip('"')
                        value = value.strip().strip('"')
                        event_dict[key] = value
                
                if event_dict:
                    json_events.append(event_dict)
        
        # Convert to standard format
        for event in json_events:
            # Parse dates
            try:
                # Convert AppleScript date format to datetime
                start_str = event.get('start', '')
                end_str = event.get('end', '')
                
                if 'date "' in start_str:
                    start_str = start_str.split('date "')[1].split('"')[0]
                if 'date "' in end_str:
                    end_str = end_str.split('date "')[1].split('"')[0]
                
                # Convert to standardized format
                events.append({
                    'id': event.get('id', str(uuid.uuid4())),
                    'title': event.get('title', 'Untitled Event'),
                    'start': start_str,
                    'end': end_str,
                    'location': event.get('location', ''),
                    'calendar_id': event.get('calendarId', ''),
                    'provider': 'apple'
                })
            except Exception as e:
                print(f"Error parsing event date: {e}")
                continue
        
        return events
    
    except subprocess.CalledProcessError as e:
        print(f"AppleScript error: {e}")
        return []
    except Exception as e:
        print(f"Error getting Apple events: {e}")
        return [] 