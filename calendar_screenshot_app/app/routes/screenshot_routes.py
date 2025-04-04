import os
import tempfile
import logging
import traceback
import platform
import base64
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from app.services import claude_service
from app.services.availability import check_availability, find_available_slots
from app.utils.date_utils import parse_date_range
from app.services.google_calendar import get_google_events
from app.services.microsoft_calendar import get_microsoft_events
from app.services.apple_calendar import get_apple_calendars, get_apple_events
import json
from PIL import Image, ImageGrab
from io import BytesIO
import time
import anthropic
import requests

# Set up logging
logger = logging.getLogger(__name__)

bp = Blueprint('screenshot', __name__, url_prefix='/screenshot')

@bp.route('/upload', methods=['POST'])
def upload_screenshot():
    """Handle screenshot upload and analysis"""
    debug_logs = []
    
    # Check if at least one calendar is selected
    if 'selected_calendars' not in session or not session['selected_calendars']:
        # If no calendars are selected, check available calendar sources
        calendars_found = False
        
        # Check for Thunderbird calendars first
        try:
            from app.services.thunderbird_calendar import find_all_calendar_databases, get_thunderbird_calendars
            thunderbird_dbs = find_all_calendar_databases()
            if thunderbird_dbs:
                thunderbird_calendars = get_thunderbird_calendars()
                if thunderbird_calendars:
                    # Automatically select all Thunderbird calendars
                    session['selected_calendars'] = [cal['id'] for cal in thunderbird_calendars]
                    flash('Using Thunderbird calendars for availability check', 'info')
                    calendars_found = True
                    logger.info(f"Auto-selected {len(thunderbird_calendars)} Thunderbird calendars")
        except Exception as e:
            logger.warning(f"Failed to auto-detect Thunderbird calendars: {e}")
        
        # If no Thunderbird calendars, try Apple Calendar on macOS
        if not calendars_found and platform.system() == 'Darwin':
            apple_calendars = get_apple_calendars()
            if apple_calendars:
                # Automatically select the first Apple Calendar
                session['selected_calendars'] = [apple_calendars[0]['id']]
                flash('Using Apple Calendar for availability check', 'info')
                calendars_found = True
        
        # If still no calendars, redirect to calendar selection
        if not calendars_found:
            flash('Please select at least one calendar before analyzing screenshots', 'warning')
            return redirect(url_for('calendar.list_calendars'))
    
    screenshot = None
    image_data = None
    
    # Check if a file was uploaded
    if 'screenshot' in request.files:
        file = request.files['screenshot']
        if file.filename != '':
            # Read the image data directly
            image_data = file.read()
            print(f"Received file: {file.filename}, Size: {len(image_data)/1024:.2f} KB")
            debug_logs.append({"message": f"Uploaded file: {file.filename}, Size: {len(image_data)/1024:.2f} KB", "type": "info"})
    
    # Check if a base64 encoded image was provided
    elif 'screenshot_data' in request.form:
        image_data_b64 = request.form['screenshot_data']
        if image_data_b64.startswith('data:image'):
            # Extract the base64 part
            image_data_b64 = image_data_b64.split(',')[1]
        
        # Decode the base64 image
        image_data = base64.b64decode(image_data_b64)
        print(f"Received base64 image data, Size: {len(image_data)/1024:.2f} KB")
        debug_logs.append({"message": f"Received base64 image, Size: {len(image_data)/1024:.2f} KB", "type": "info"})
    
    # Check if we should grab from clipboard
    elif request.form.get('clipboard') == 'true':
        try:
            screenshot = ImageGrab.grabclipboard()
            if screenshot:
                # Convert PIL Image to bytes
                img_byte_arr = BytesIO()
                screenshot.save(img_byte_arr, format='PNG')
                image_data = img_byte_arr.getvalue()
                print(f"Clipboard image captured, Size: {len(image_data)/1024:.2f} KB")
                debug_logs.append({"message": f"Clipboard image captured, Size: {len(image_data)/1024:.2f} KB", "type": "info"})
            else:
                return jsonify({'error': 'No image found in clipboard'}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to grab from clipboard: {str(e)}'}), 400
    
    if not image_data:
        return jsonify({'error': 'No screenshot provided'}), 400
    
    try:
        # Analyze the screenshot using the Claude service
        print("\n===== STARTING CLAUDE ANALYSIS =====")
        result = claude_service.analyze_screenshot(image_data, debug_logs)
        print("===== ANALYSIS COMPLETE =====\n")
        
        if not result or not result.get('success', False):
            # Use a more detailed error message and ensure debug logs are passed
            error_result = {
                'error': result.get('error', 'No time slots detected in the screenshot'),
                'analysis': result.get('analysis', 'The analysis could not detect any time slots in the image.'),
                'debug_logs': result.get('debug_logs', debug_logs)
            }
            return render_template('analysis_results.html', result=error_result)
        
        # Get all calendar events for the time range to display in the calendar view
        all_events = []
        
        # Get time slots from result
        time_slots = result.get('time_slots', [])
        
        if not time_slots:
            error_result = {
                'error': 'No time slots detected in the screenshot',
                'analysis': result.get('analysis', 'The analysis could not detect any time slots in the image.'),
                'debug_logs': result.get('debug_logs', debug_logs)
            }
            return render_template('analysis_results.html', result=error_result)
        
        # Ensure time slots have timezone information
        for slot in time_slots:
            # Make timezone-aware if they're naive
            if slot['start_time'].tzinfo is None:
                slot['start_time'] = slot['start_time'].replace(tzinfo=timezone.utc)
            if slot['end_time'].tzinfo is None:
                slot['end_time'] = slot['end_time'].replace(tzinfo=timezone.utc)
            
            # Extract the current calendar year from session or default to now
            calendar_year = datetime.now().year
            try:
                # Look at the first event's year to determine what year the calendar is displaying
                if all_events and len(all_events) > 0:
                    first_event = all_events[0]
                    if isinstance(first_event['start'], datetime):
                        calendar_year = first_event['start'].year
                    elif isinstance(first_event['start'], str):
                        # Parse ISO date string
                        calendar_year = int(first_event['start'].split('-')[0])
            except Exception as e:
                print(f"DEBUG: Error determining calendar year: {e}, using current year")

            # Add debug info
            print(f"DEBUG: Calendar year detected as {calendar_year}")
            print(f"DEBUG: Original slot time - Start: {slot['start_time']}, End: {slot['end_time']}")

            # Adjust all slot years to match the calendar year if they differ
            slot_year = slot['start_time'].year
            if slot_year != calendar_year:
                # Create new datetime objects with the calendar year but keep original month/day/time
                slot['start_time'] = slot['start_time'].replace(year=calendar_year)
                slot['end_time'] = slot['end_time'].replace(year=calendar_year)
                print(f"DEBUG: Adjusted slot time to calendar year {calendar_year} - Start: {slot['start_time']}, End: {slot['end_time']}")
                
                # Add a test event for each adjusted time slot for debugging
                all_events.append({
                    'title': f"Test: {slot.get('context', 'Time Slot')}",
                    'start': slot['start_time'],
                    'end': slot['end_time'],
                    'backgroundColor': '#FF9500',
                    'borderColor': '#FF7700',
                    'classNames': ['test-event'],
                    'provider': 'test'
                })
                print(f"DEBUG: Added test event for adjusted slot: {slot['start_time']} - {slot['end_time']}")
            
            # Ensure available is not null (prevents rendering issues)
            if slot['available'] is None:
                slot['available'] = True  # Default to available if not specified
                
            # Make sure conflicts is initialized
            if 'conflicts' not in slot:
                slot['conflicts'] = []
        
        # Find the earliest start time and latest end time from all slots
        earliest_start = min(slot['start_time'] for slot in result['time_slots'])
        latest_end = max(slot['end_time'] for slot in result['time_slots'])
        
        # Always use current date range for calendar display
        # This ensures we show current calendar events even if screenshot has historical dates
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get a date range that covers all the slots from the screenshot
        # Use the dates directly from the time slots for more accurate display
        slot_dates = set([slot['start_time'].date() for slot in result['time_slots']])
        
        # Create a range from the earliest to latest date
        min_date = min(slot_dates)
        max_date = max(slot_dates)
        
        # Set calendar range to include the dates from the screenshot plus buffer
        calendar_start = datetime.combine(min_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        calendar_end = datetime.combine(max_date, datetime.max.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
        
        print(f"DEBUG: Using date range for calendar display: {calendar_start} to {calendar_end}")
        print(f"DEBUG: Original date range from screenshot: {earliest_start} to {latest_end}")
        
        print("\n========================")
        print("= THUNDERBIRD CALENDAR DATA RETRIEVAL =")
        print("========================\n")
        
        # IMPORTANT: Get Thunderbird calendar events BEFORE conflict checking
        try:
            from app.services.thunderbird_calendar import get_thunderbird_calendars, get_thunderbird_events
            
            print("THUNDERBIRD DEBUG: Starting Thunderbird calendar search")
            thunderbird_calendars = get_thunderbird_calendars()
            
            if thunderbird_calendars:
                print(f"THUNDERBIRD DEBUG: Found {len(thunderbird_calendars)} calendars")
                for cal in thunderbird_calendars:
                    print(f"THUNDERBIRD DEBUG: Calendar: {cal.get('name')} (ID: {cal.get('id')})")
                
                thunderbird_ids = [cal['id'] for cal in thunderbird_calendars]
                
                # Set up date range for March-April 2025
                calendar_year = 2025
                month_start = datetime(calendar_year, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
                month_end = datetime(calendar_year, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
                
                print(f"THUNDERBIRD DEBUG: Searching for events between {month_start} and {month_end}")
                
                for cal_id in thunderbird_ids:
                    print(f"THUNDERBIRD DEBUG: Getting events for calendar {cal_id}")
                    
                    try:
                        # Call function directly to get events
                        thunderbird_events = get_thunderbird_events([cal_id], month_start, month_end)
                        print(f"THUNDERBIRD DEBUG: Retrieved {len(thunderbird_events)} events")
                        
                        # Print details of each event
                        for i, event in enumerate(thunderbird_events):
                            print(f"THUNDERBIRD DEBUG: Event {i+1} - '{event.get('title')}' on {event.get('start')} to {event.get('end')}")
                            
                            # Add event to our all_events list with distinct color
                            event_copy = event.copy()  # Make a copy to avoid modifying original
                            event_copy['backgroundColor'] = '#0057B7'  # Blue
                            event_copy['borderColor'] = '#004494'
                            event_copy['classNames'] = ['real-event', 'thunderbird-event']
                            
                            all_events.append(event_copy)
                            print(f"THUNDERBIRD DEBUG: Added event: {event_copy.get('title')}")
                    except Exception as cal_err:
                        print(f"THUNDERBIRD DEBUG: Error getting events for calendar {cal_id}: {cal_err}")
                        import traceback
                        print(f"THUNDERBIRD DEBUG: {traceback.format_exc()}")
            else:
                print("THUNDERBIRD DEBUG: No Thunderbird calendars found")
        except Exception as tb_err:
            print(f"THUNDERBIRD DEBUG: Error in Thunderbird event retrieval: {tb_err}")
            import traceback
            print(f"THUNDERBIRD DEBUG: {traceback.format_exc()}")
        
        print("\n========================")
        print("= END THUNDERBIRD RETRIEVAL =")
        print("========================\n")

        # Debug event information
        print(f"EVENTS DEBUG: Total events after Thunderbird retrieval: {len(all_events)}")
        for i, event in enumerate(all_events[:10]):  # Log first 10 events for debugging
            print(f"EVENTS DEBUG: Event {i+1} - '{event.get('title')}' on {event.get('start')} to {event.get('end')}")
        
        # Check availability for each time slot
        for slot in result['time_slots']:
            try:
                # Find conflicts with any event
                slot['conflicts'] = []
                slot['available'] = True
                
                # Get slot times for easier comparison
                slot_start = slot['start_time']
                slot_end = slot['end_time']
                
                # Debug print
                print(f"DEBUG: Checking conflicts for slot {slot.get('context', '')}: {slot_start} - {slot_end}")
                
                for event in all_events:
                    # Extract the event start/end times, handling both datetime objects and strings
                    if isinstance(event['start'], str):
                        # Convert ISO string to datetime
                        if event['start'].endswith('Z'):
                            event_start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                        else:
                            event_start = datetime.fromisoformat(event['start'])
                    else:
                        event_start = event['start']
                    
                    if isinstance(event['end'], str):
                        # Convert ISO string to datetime
                        if event['end'].endswith('Z'):
                            event_end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
                        else:
                            event_end = datetime.fromisoformat(event['end'])
                    else:
                        event_end = event['end']
                    
                    # Make sure both have timezone info
                    if event_start.tzinfo is None:
                        event_start = event_start.replace(tzinfo=timezone.utc)
                    if event_end.tzinfo is None:
                        event_end = event_end.replace(tzinfo=timezone.utc)
                    
                    # Check for overlap: if start_time < event_end and end_time > event_start
                    if slot_start < event_end and slot_end > event_start:
                        slot['available'] = False
                        # Create a conflict entry with clean display info
                        conflict = {
                            'title': event.get('title', 'Untitled Event'),
                            'start': event_start,
                            'end': event_end,
                            'calendar_id': event.get('calendar_id', 'unknown'),
                            'provider': event.get('provider', 'unknown')
                        }
                        slot['conflicts'].append(conflict)
                        print(f"DEBUG: Conflict found with '{event.get('title', 'Untitled Event')}' ({event_start} - {event_end})")
            except Exception as e:
                slot['available'] = False
                slot['error'] = str(e)
                print(f"ERROR checking availability for slot {slot['start_time']}: {str(e)}")
                debug_logs.append({"message": f"Error checking availability for slot: {str(e)}", "type": "error"})
        
        # Find available slots
        suggested_slots = find_alternative_slots(result['time_slots'], all_events)
        
        # Debug: Output information about calendar events
        print(f"DEBUG: Passing {len(all_events)} calendar events to template")
        if all_events:
            print(f"DEBUG: Sample event: {all_events[0]}")
        else:
            print("DEBUG: No calendar events found, not generating any sample events")
        
        return render_template('analysis_results.html', 
                            result=result, 
                            suggested_slots=suggested_slots,
                            all_calendar_events=all_events)
    
    except Exception as e:
        error_message = str(e)
        print(f"ERROR in upload_screenshot: {error_message}")
        traceback.print_exc()
        
        return render_template('analysis_results.html', result={
            'error': error_message,
            'success': False,
            'debug_logs': debug_logs
        })

@bp.route('/analyze', methods=['POST'])
def analyze_screenshot_route():
    """
    Analyze a screenshot to extract calendar time slots.
    """
    debug_logs = []
    
    try:
        # Check if file was uploaded
        if 'screenshot' not in request.files:
            flash('No screenshot provided', 'danger')
            return redirect(url_for('index'))
            
        file = request.files['screenshot']
        
        # Check if file is empty
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('index'))
            
        # Read the image data directly
        image_data = file.read()
        
        # Print file details for debugging
        print(f"Received file: {file.filename}, Size: {len(image_data)/1024:.2f} KB")
        
        # Get analysis from Claude API using the new analyze_screenshot function
        print("\n===== STARTING CLAUDE ANALYSIS =====")
        result = claude_service.analyze_screenshot(image_data, debug_logs)
        print("===== ANALYSIS COMPLETE =====\n")
        
        # Check for selected calendars
        selected_calendars = get_selected_calendars()
        
        # If no calendars are selected, show error
        if not selected_calendars:
            flash('Please select at least one calendar before analyzing screenshots', 'warning')
            return redirect(url_for('calendar.select_calendars'))
            
        # Get all events from selected calendars
        all_events = []
        
        # If we have time slots in the result, check availability
        if result.get('success') and 'time_slots' in result:
            time_slots = result.get('time_slots', [])
            
            # Merge user's events from all selected calendars
            all_events = get_all_calendar_events(selected_calendars)
            
            # Extract the current calendar year from events or default to now
            calendar_year = datetime.now().year
            try:
                # Look at the first event's year to determine what year the calendar is displaying
                if all_events and len(all_events) > 0:
                    first_event = all_events[0]
                    if isinstance(first_event['start'], datetime):
                        calendar_year = first_event['start'].year
                    elif isinstance(first_event['start'], str):
                        # Parse ISO date string
                        calendar_year = int(first_event['start'].split('-')[0])
            except Exception as e:
                print(f"DEBUG: Error determining calendar year: {e}, using current year")
            
            print(f"DEBUG: Calendar year detected as {calendar_year}")
            
            # Ensure time slots have timezone information and correct year
            for slot in time_slots:
                # Make timezone-aware if they're naive
                if slot['start_time'].tzinfo is None:
                    slot['start_time'] = slot['start_time'].replace(tzinfo=timezone.utc)
                if slot['end_time'].tzinfo is None:
                    slot['end_time'] = slot['end_time'].replace(tzinfo=timezone.utc)
                
                # Adjust year if it doesn't match the calendar year
                print(f"DEBUG: Original slot time - Start: {slot['start_time']}, End: {slot['end_time']}")
                slot_year = slot['start_time'].year
                if slot_year != calendar_year:
                    # Create new datetime objects with the calendar year but keep original month/day/time
                    slot['start_time'] = slot['start_time'].replace(year=calendar_year)
                    slot['end_time'] = slot['end_time'].replace(year=calendar_year)
                    print(f"DEBUG: Adjusted slot time to calendar year {calendar_year} - Start: {slot['start_time']}, End: {slot['end_time']}")
                
                # Initialize conflicts list if not present
                if 'conflicts' not in slot:
                    slot['conflicts'] = []
                    
                # Default to available
                slot['available'] = True
        
        # Render template with results
        return render_template('analysis_results.html', 
                              result=result, 
                              all_calendar_events=all_events)
                              
    except Exception as e:
        error_message = str(e)
        print(f"ERROR in analyze_screenshot_route: {error_message}")
        traceback.print_exc()
        
        return render_template('analysis_results.html', 
                              result={
                                  'error': f"Error analyzing screenshot: {error_message}",
                                  'success': False,
                                  'debug_logs': debug_logs
                              })

@bp.route('/analyze_clipboard', methods=['POST'])
def analyze_clipboard():
    """Analyze image from clipboard"""
    debug_logs = []
    
    try:
        # Get clipboard image from request
        clipboard_image = request.form.get('clipboard_image') or ''
        
        if not clipboard_image:
            # Create temp file for image
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                temp_path = temp_file.name
                
                # Use pyscreenshot to capture clipboard
                try:
                    # On Linux, use xclip
                    if os.name != 'nt' and os.name != 'darwin':  
                        import subprocess
                        result = subprocess.run(['xclip', '-selection', 'clipboard', '-t', 'image/png', '-o'], 
                                              stdout=temp_file, check=True)
                    # On macOS, use applescript 
                    elif os.name == 'darwin':
                        import subprocess
                        applescript = '''
                        set theFile to "%s"
                        set theData to the clipboard as «class PNGf»
                        set outFile to (open for access theFile with write permission)
                        write theData to outFile
                        close access outFile
                        ''' % temp_path
                        subprocess.run(['osascript', '-e', applescript], check=True)
                    # On Windows, use pillow with win32clipboard
                    else:
                        import win32clipboard
                        from io import BytesIO
                        from PIL import Image
                        
                        win32clipboard.OpenClipboard()
                        data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)
                        win32clipboard.CloseClipboard()
                        
                        image = Image.open(BytesIO(data))
                        image.save(temp_path)
                        
                    print(f"Clipboard image saved to {temp_path}")
                    debug_logs.append({"message": f"Clipboard image saved to temporary file", "type": "info"})
                except Exception as e:
                    return render_template('analysis_results.html', result={
                        'error': f"Could not capture clipboard: {str(e)}",
                        'success': False,
                        'debug_logs': debug_logs
                    })
                
                # Read the image data from the temporary file
                with open(temp_path, 'rb') as f:
                    image_data = f.read()
                
                # Remove temp file after reading
                try:
                    os.unlink(temp_path)
                except:
                    pass
        else:
            # Base64 image from HTML5 clipboard
            if clipboard_image.startswith('data:image'):
                image_data_b64 = clipboard_image.split(',')[1]
                image_data = base64.b64decode(image_data_b64)
                debug_logs.append({"message": "Image data extracted from base64 clipboard", "type": "info"})
            else:
                return render_template('analysis_results.html', result={
                    'error': "Invalid clipboard data format",
                    'success': False,
                    'debug_logs': debug_logs
                })
                
        # Now analyze the image data with Claude
        print(f"Analyzing clipboard image ({len(image_data)/1024:.2f} KB)")
        print("\n===== STARTING CLAUDE ANALYSIS =====")
        result = claude_service.analyze_screenshot(image_data, debug_logs)
        print("===== ANALYSIS COMPLETE =====\n")
            
        # Check for selected calendars
        selected_calendars = get_selected_calendars()
        
        # If no calendars are selected, show error
        if not selected_calendars:
            flash('Please select at least one calendar before analyzing screenshots', 'warning')
            return redirect(url_for('calendar.select_calendars'))
            
        # Get all events from selected calendars
        all_events = []
        
        # If we have time slots in the result, check availability
        if result.get('success') and 'time_slots' in result:
            time_slots = result.get('time_slots', [])
            
            # Merge user's events from all selected calendars
            all_events = get_all_calendar_events(selected_calendars)
            
            # For each time slot, check if it conflicts with any events
            for slot in time_slots:
                slot_start = slot['start_time']
                slot_end = slot['end_time']
                
                # Initialize conflicts list if not present
                if 'conflicts' not in slot:
                    slot['conflicts'] = []
                    
                # Default to available
                slot['available'] = True
                
                # Check for conflicts
                for event in all_events:
                    event_start = event['start']
                    event_end = event['end']
                    
                    try:
                        # Check if event overlaps with slot
                        if ((event_start <= slot_start < event_end) or
                            (event_start < slot_end <= event_end) or
                            (slot_start <= event_start and event_end <= slot_end)):
                            
                            # Mark as unavailable and add to conflicts
                            slot['available'] = False
                            slot['conflicts'].append({
                                'title': event['title'],
                                'start': event_start,
                                'end': event_end
                            })
                    except Exception as e:
                        print(f"ERROR checking conflict for event {event['title']}: {str(e)}")
                        debug_logs.append({"message": f"Error checking conflict: {str(e)}", "type": "error"})
            
            # If it's a time request (not suggestion), find alternative slots
            if 'is_suggestion' in result and not result['is_suggestion']:
                suggested_slots = find_alternative_slots(time_slots, all_events)
                return render_template('analysis_results.html', 
                                      result=result, 
                                      suggested_slots=suggested_slots, 
                                      all_calendar_events=all_events)
        
        # Render template with results
        return render_template('analysis_results.html', 
                              result=result, 
                              all_calendar_events=all_events)
                              
    except Exception as e:
        error_message = str(e)
        print(f"ERROR in analyze_clipboard: {error_message}")
        traceback.print_exc()
        
        return render_template('analysis_results.html', 
                              result={
                                  'error': f"Error analyzing clipboard: {error_message}",
                                  'success': False,
                                  'debug_logs': debug_logs
                              })

def check_availability(start_time, end_time):
    """
    Check if the user is available at the given time slot.
    
    Args:
        start_time: Datetime object representing the start time
        end_time: Datetime object representing the end time
    
    Returns:
        bool: True if the user is available, False otherwise
    """
    selected_calendars = session.get('selected_calendars', [])
    if not selected_calendars:
        raise ValueError("No calendars selected")
    
    all_events = []
    
    # Get Apple Calendar events if on macOS
    if platform.system() == 'Darwin':
        apple_calendars = get_apple_calendars()
        apple_selected = [cal for cal in apple_calendars if cal['id'] in selected_calendars]
        if apple_selected:
            all_events.extend(get_apple_events(apple_selected, start_time, end_time))
    
    # Get Google Calendar events if authenticated
    if 'google_token' in session:
        from app.services.google_calendar import get_google_calendars
        google_calendars = get_google_calendars()
        google_selected = [cal for cal in google_calendars if cal['id'] in selected_calendars]
        if google_selected:
            all_events.extend(get_google_events(google_selected, start_time, end_time))
    
    # Get Microsoft Calendar events if authenticated
    if 'microsoft_token' in session:
        from app.services.microsoft_calendar import get_microsoft_calendars
        microsoft_calendars = get_microsoft_calendars()
        microsoft_selected = [cal for cal in microsoft_calendars if cal['id'] in selected_calendars]
        if microsoft_selected:
            all_events.extend(get_microsoft_events(microsoft_selected, start_time, end_time))
    
    # Check if any events overlap with the given time slot
    for event in all_events:
        event_start = event['start'] if isinstance(event['start'], datetime) else datetime.fromisoformat(event['start'])
        event_end = event['end'] if isinstance(event['end'], datetime) else datetime.fromisoformat(event['end'])
        
        # Check for overlap: if start_time < event_end and end_time > event_start
        if start_time < event_end and end_time > event_start:
            return False
    
    return True

def find_available_slots(time_slots, date):
    """
    Find available time slots from the list of time slots.
    
    Args:
        time_slots: List of time slot dictionaries with start_time, end_time, and available fields
        date: The date for the time slots
    
    Returns:
        list: List of available time slots
    """
    available_slots = []
    
    for slot in time_slots:
        if slot.get('available', False):
            available_slots.append(slot)
    
    # If no slots are available, try to find alternative slots
    if not available_slots and time_slots:
        # Get the working hours range from the first and last time slot
        first_slot = min(time_slots, key=lambda x: x['start_time'])
        last_slot = max(time_slots, key=lambda x: x['end_time'])
        
        start_hour = first_slot['start_time'].hour
        end_hour = last_slot['end_time'].hour
        
        # Try 30-minute slots between the start and end time
        current_time = datetime.combine(date, dt_time(start_hour, 0))
        end_time = datetime.combine(date, dt_time(end_hour, 0))
        
        while current_time < end_time:
            slot_start = current_time
            slot_end = current_time + timedelta(minutes=30)
            
            if check_availability(slot_start, slot_end):
                available_slots.append({
                    'start_time': slot_start,
                    'end_time': slot_end,
                    'available': True,
                    'title': f"{slot_start.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                })
            
            current_time += timedelta(minutes=30)
    
    return available_slots

@bp.route('/api_status', methods=['GET'])
def api_status():
    """Check the status of the Claude API and display results"""
    debug_logs = []
    
    # Check for API key
    api_key = os.environ.get('CLAUDE_API_KEY')
    
    if not api_key:
        debug_logs.append({"message": "Claude API key not found in environment variables", "type": "error"})
    else:
        if api_key.startswith('sk-'):
            masked_key = f"{api_key[:5]}...{api_key[-2:]}"
            debug_logs.append({"message": f"API key found with correct format (masked: {masked_key})", "type": "success"})
        else:
            debug_logs.append({"message": f"API key has invalid format (should start with 'sk-')", "type": "error"})
    
    # Check network connectivity to Claude API
    from app.services.claude_service import check_network_connectivity
    connectivity_result = check_network_connectivity()
    
    # Determine if connectivity was successful
    connectivity_success = connectivity_result.get("success", False)
    
    # Add connectivity log to our debug logs
    if connectivity_success:
        debug_logs.append({"message": connectivity_result.get("message", "Connected to Anthropic API"), "type": "success"})
    else:
        debug_logs.append({"message": connectivity_result.get("error", "Failed to connect to Anthropic API"), "type": "error"})
    
    # Create network status for the template
    network_status = {
        "success": connectivity_success,
        "message": connectivity_result.get("message") if connectivity_success else connectivity_result.get("error", "Unknown connectivity issue")
    }
    
    # Check API access by making a simple test request if key is available
    api_access = {"success": False, "message": "API access not tested"}
    
    if api_key and api_key.startswith('sk-') and connectivity_success:
        try:
            import anthropic
            import time
            
            debug_logs.append({"message": "Testing Claude API access with a simple request...", "type": "info"})
            
            client = anthropic.Anthropic(api_key=api_key)
            start_time = time.time()
            
            # Simple request to test the API
            try:
                debug_logs.append({"message": "Sending test request to Claude API...", "type": "info"})
                
                # Print request details
                print("\n---------- API STATUS TEST REQUEST ----------")
                print(f"Model: claude-3-5-sonnet-20240620")
                print(f"Prompt: 'Say hello'")
                print(f"API Key (masked): {api_key[:5]}...{api_key[-2:]}")
                print("---------------------------------------------\n")
                
                start_time = time.time()
                response = client.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Say hello"}]
                )
                
                duration = time.time() - start_time
                
                # Print response details
                print("\n---------- API STATUS TEST RESPONSE ----------")
                print(f"Response time: {duration:.2f} seconds")
                print(f"Content type: {type(response.content)}")
                print(f"Full content: {response.content}")
                print(f"Stop reason: {response.stop_reason}")
                print(f"Stop sequence: {response.stop_sequence}")
                print(f"Model: {response.model}")
                print(f"Usage: {response.usage}")
                print("-----------------------------------------------\n")
                
                api_access = {
                    "success": True, 
                    "message": f"API access successful (response time: {duration:.2f}s)",
                    "model": "claude-3-5-sonnet-20240620",
                    "response": response.content[0].text if response.content else "No content"
                }
                
                debug_logs.append({"message": api_access["message"], "type": "success"})
                debug_logs.append({"message": f"API response: {api_access['response']}", "type": "info"})
                
            except anthropic.APIError as api_error:
                error_code = getattr(api_error, 'status_code', 'unknown')
                error_type = getattr(api_error, 'type', 'unknown')
                error_message = str(api_error)
                
                debug_logs.append({"message": f"API error (status {error_code}, type {error_type}): {error_message}", "type": "error"})
                
                if error_code == 401:
                    debug_logs.append({"message": "Authentication failed. Your API key may be invalid or expired.", "type": "error"})
                elif error_code == 429:
                    debug_logs.append({"message": "Rate limit exceeded. Your account may be out of credits or over quota.", "type": "error"})
                elif error_code == 400:
                    debug_logs.append({"message": "Bad request. There might be an issue with the API parameters.", "type": "error"})
                elif error_code in [500, 502, 503, 504]:
                    debug_logs.append({"message": "Server error. The Claude API may be experiencing issues.", "type": "error"})
                
                api_access = {"success": False, "message": error_message}
                
            except anthropic.APIConnectionError as conn_error:
                debug_logs.append({"message": f"API connection error: {str(conn_error)}", "type": "error"})
                debug_logs.append({"message": "This might be due to network issues or the API being down.", "type": "info"})
                api_access = {"success": False, "message": f"Connection error: {str(conn_error)}"}
                
            except anthropic.RateLimitError as rate_error:
                debug_logs.append({"message": f"Rate limit error: {str(rate_error)}", "type": "error"})
                debug_logs.append({"message": "Your account may be out of credits or over quota.", "type": "info"})
                api_access = {"success": False, "message": f"Rate limit exceeded: {str(rate_error)}"}
                
        except Exception as e:
            debug_logs.append({"message": f"Error setting up API client: {str(e)}", "type": "error"})
            debug_logs.append({"message": "Check if the anthropic package is installed correctly.", "type": "info"})
            api_access = {"success": False, "message": str(e)}
    
    # Return the status information
    status_result = {
        "python": f"Python {platform.python_version()} on {platform.system()}",
        "packages": {"required": ["anthropic", "PIL", "flask", "requests"]},
        "api_key": {"configured": bool(api_key), "valid_format": bool(api_key and api_key.startswith('sk-'))},
        "network": network_status,
        "api_access": api_access,
        "debug_logs": debug_logs
    }
    
    return render_template('api_status.html', result=status_result)

@bp.route('/api_test', methods=['GET'])
def claude_api_test():
    """Direct test of Claude API with detailed output"""
    debug_logs = []
    
    # Check API key configuration
    api_key = os.environ.get('CLAUDE_API_KEY')
    if not api_key:
        debug_logs.append({"message": "CLAUDE_API_KEY environment variable not set", "type": "error"})
        return render_template('api_status.html', result={
            "python": f"Python {platform.python_version()} on {platform.system()}",
            "api_key": {"configured": False, "valid_format": False},
            "debug_logs": debug_logs
        })
    
    # Basic check for key format (Claude API keys start with 'sk-')
    if not api_key.startswith('sk-'):
        debug_logs.append({"message": f"API key has invalid format (should start with 'sk-')", "type": "error"})
        return render_template('api_status.html', result={
            "python": f"Python {platform.python_version()} on {platform.system()}",
            "api_key": {"configured": True, "valid_format": False},
            "debug_logs": debug_logs
        })
        
    # Log masked API key
    masked_key = f"{api_key[:5]}...{api_key[-2:]}"
    debug_logs.append({"message": f"API key found with correct format (masked: {masked_key})", "type": "success"})
    
    # Check network connectivity to Claude API
    from app.services.claude_service import check_network_connectivity
    connectivity_success, connectivity_logs = check_network_connectivity()
    
    # Add connectivity logs to our debug logs
    debug_logs.extend(connectivity_logs)
    
    # Test API directly with detailed logs
    try:
        import anthropic
        import time
        
        debug_logs.append({"message": "Testing Claude API access with a simple request...", "type": "info"})
        
        try:
            client = anthropic.Anthropic(api_key=api_key)
            debug_logs.append({"message": "Claude client initialized successfully", "type": "success"})
            
            # Print request details to console
            print("\n---------- CLAUDE API TEST REQUEST ----------")
            print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Model: claude-3-5-sonnet-20240620")
            print(f"Max tokens: 10")
            print(f"Prompt: 'Say hello'")
            print(f"API Key (masked): {masked_key}")
            print("--------------------------------------------\n")
            
            # Make a simple API request
            start_time = time.time()
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=10,
                messages=[{"role": "user", "content": "Say hello"}]
            )
            
            duration = time.time() - start_time
            
            # Print response details to console
            print("\n---------- CLAUDE API TEST RESPONSE ----------")
            print(f"Response time: {duration:.2f} seconds")
            print(f"Type: {type(response)}")
            print(f"Content: {response.content}")
            print(f"Content type: {type(response.content)}")
            if response.content and len(response.content) > 0:
                print(f"Content[0]: {response.content[0]}")
                print(f"Content[0].type: {response.content[0].type}")
                print(f"Content[0].text: {response.content[0].text}")
            print(f"ID: {response.id}")
            print(f"Model: {response.model}")
            print(f"Role: {response.role}")
            print(f"Stop reason: {response.stop_reason}")
            print(f"Usage: {response.usage}")
            print(f"Usage tokens: {response.usage.input_tokens} input, {response.usage.output_tokens} output")
            print("---------------------------------------------\n")
            
            # Add success results to logs
            api_response = response.content[0].text if response.content and len(response.content) > 0 else "No content"
            debug_logs.append({"message": f"API response successful (took {duration:.2f}s): '{api_response}'", "type": "success"})
            debug_logs.append({"message": f"Input tokens: {response.usage.input_tokens}, Output tokens: {response.usage.output_tokens}", "type": "info"})
            
            # Return success template
            return render_template('api_status.html', result={
                "python": f"Python {platform.python_version()} on {platform.system()}",
                "api_key": {"configured": True, "valid_format": True},
                "network": {"success": connectivity_success},
                "api_access": {
                    "success": True,
                    "message": f"API access successful (response time: {duration:.2f}s)",
                    "model": "claude-3-5-sonnet-20240620",
                    "response": api_response
                },
                "debug_logs": debug_logs
            })
            
        except anthropic.APIError as api_err:
            error_code = getattr(api_err, 'status_code', 'unknown')
            error_type = getattr(api_err, 'type', 'unknown')
            
            print(f"\nAPI ERROR: {str(api_err)}")
            print(f"Status code: {error_code}")
            print(f"Error type: {error_type}")
            print(f"Full error object: {dir(api_err)}\n")
            
            debug_logs.append({"message": f"API error: {str(api_err)}", "type": "error"})
            debug_logs.append({"message": f"Error details - Status: {error_code}, Type: {error_type}", "type": "error"})
            
            return render_template('api_status.html', result={
                "python": f"Python {platform.python_version()} on {platform.system()}",
                "api_key": {"configured": True, "valid_format": True},
                "network": {"success": connectivity_success},
                "api_access": {
                    "success": False,
                    "message": f"API error: {str(api_err)}"
                },
                "debug_logs": debug_logs
            })
            
        except Exception as e:
            print(f"\nERROR: {str(e)}")
            print(f"Error type: {type(e)}")
            print(f"Error details: {dir(e)}\n")
            
            debug_logs.append({"message": f"Error during API test: {str(e)}", "type": "error"})
            
            return render_template('api_status.html', result={
                "python": f"Python {platform.python_version()} on {platform.system()}",
                "api_key": {"configured": True, "valid_format": True},
                "network": {"success": connectivity_success},
                "api_access": {
                    "success": False,
                    "message": f"Error: {str(e)}"
                },
                "debug_logs": debug_logs
            })
            
    except ImportError:
        debug_logs.append({"message": "Failed to import anthropic library", "type": "error"})
        return render_template('api_status.html', result={
            "python": f"Python {platform.python_version()} on {platform.system()}",
            "api_key": {"configured": True, "valid_format": True},
            "network": {"success": connectivity_success},
            "api_access": {
                "success": False,
                "message": "Anthropic library not installed"
            },
            "debug_logs": debug_logs
        }) 

def get_selected_calendars():
    """
    Get selected calendars from the session.
    If no calendars are explicitly selected, try to auto-select Thunderbird or Apple calendars.
    
    Returns:
        list: List of selected calendar IDs
    """
    # Check if calendars are already selected
    if 'selected_calendars' in session and session['selected_calendars']:
        return session['selected_calendars']
    
    # If not, try to auto-select Thunderbird calendars
    try:
        from app.services.thunderbird_calendar import find_all_calendar_databases, get_thunderbird_calendars
        thunderbird_dbs = find_all_calendar_databases()
        if thunderbird_dbs:
            thunderbird_calendars = get_thunderbird_calendars()
            if thunderbird_calendars:
                # Automatically select all Thunderbird calendars
                selected_calendars = [cal['id'] for cal in thunderbird_calendars]
                session['selected_calendars'] = selected_calendars
                print(f"Auto-selected {len(thunderbird_calendars)} Thunderbird calendars")
                return selected_calendars
    except Exception as e:
        print(f"Failed to auto-detect Thunderbird calendars: {e}")
    
    # If no Thunderbird calendars, try Apple Calendar on macOS
    if platform.system() == 'Darwin':
        try:
            from app.services.apple_calendar import get_apple_calendars
            apple_calendars = get_apple_calendars()
            if apple_calendars:
                # Automatically select the first Apple Calendar
                selected_calendars = [apple_calendars[0]['id']]
                session['selected_calendars'] = selected_calendars
                print(f"Auto-selected Apple Calendar: {apple_calendars[0]['name']}")
                return selected_calendars
        except Exception as e:
            print(f"Failed to auto-detect Apple calendars: {e}")
    
    # No calendars selected or auto-detected
    return []

def get_all_calendar_events(selected_calendars, start_date=None, end_date=None):
    """
    Get events from all selected calendars.
    
    Args:
        selected_calendars (list): List of selected calendar IDs
        start_date (datetime, optional): Start date for events. Defaults to today.
        end_date (datetime, optional): End date for events. Defaults to 7 days from today.
        
    Returns:
        list: List of calendar events
    """
    # Use current date range if not provided
    if not start_date:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not end_date:
        end_date = start_date + timedelta(days=7)
    
    # Debug logging
    print(f"\n==== CALENDAR EVENT RETRIEVAL ====")
    print(f"Selected calendars: {selected_calendars}")
    print(f"Time range: {start_date} to {end_date}")
    
    all_events = []
    
    # Get Apple Calendar events if on macOS
    if platform.system() == 'Darwin':
        try:
            print(f"\n-- Checking Apple Calendars --")
            from app.services.apple_calendar import get_apple_calendars, get_apple_events
            apple_calendars = get_apple_calendars()
            print(f"Found {len(apple_calendars)} Apple calendars")
            for cal in apple_calendars:
                print(f"  • {cal['name']} (ID: {cal['id']}) - Selected: {cal['id'] in selected_calendars}")
            
            apple_selected = [cal for cal in apple_calendars if cal['id'] in selected_calendars]
            print(f"Selected {len(apple_selected)} Apple calendars")
            
            if apple_selected:
                apple_events = get_apple_events(apple_selected, start_date, end_date)
                print(f"Retrieved {len(apple_events)} Apple Calendar events")
                for i, event in enumerate(apple_events[:5]):  # Print first 5 for debugging
                    print(f"  • Event {i+1}: {event.get('title')} - {event.get('start')} to {event.get('end')}")
                if len(apple_events) > 5:
                    print(f"  • ... and {len(apple_events) - 5} more events")
                
                all_events.extend(apple_events)
                print(f"Added {len(apple_events)} Apple Calendar events to result")
        except Exception as e:
            print(f"Error getting Apple events: {e}")
            import traceback
            traceback.print_exc()
    
    # Get Thunderbird Calendar events
    try:
        print(f"\n-- Checking Thunderbird Calendars --")
        from app.services.thunderbird_calendar import get_thunderbird_calendars, get_thunderbird_events
        thunderbird_calendars = get_thunderbird_calendars()
        print(f"Found {len(thunderbird_calendars)} Thunderbird calendars")
        for cal in thunderbird_calendars:
            print(f"  • {cal.get('name', 'Unnamed')} (ID: {cal['id']}) - Selected: {cal['id'] in selected_calendars}")
        
        thunderbird_selected = [cal for cal in thunderbird_calendars if cal['id'] in selected_calendars]
        print(f"Selected {len(thunderbird_selected)} Thunderbird calendars")
        
        if thunderbird_selected:
            thunderbird_events = get_thunderbird_events(thunderbird_selected, start_date, end_date)
            print(f"Retrieved {len(thunderbird_events)} Thunderbird Calendar events")
            for i, event in enumerate(thunderbird_events[:5]):  # Print first 5 for debugging
                print(f"  • Event {i+1}: {event.get('title')} - {event.get('start')} to {event.get('end')}")
            if len(thunderbird_events) > 5:
                print(f"  • ... and {len(thunderbird_events) - 5} more events")
            
            all_events.extend(thunderbird_events)
            print(f"Added {len(thunderbird_events)} Thunderbird Calendar events to result")
    except Exception as e:
        print(f"Error getting Thunderbird events: {e}")
        import traceback
        traceback.print_exc()
    
    # Get Google Calendar events if authenticated
    if 'google_token' in session:
        try:
            print(f"\n-- Checking Google Calendars --")
            from app.services.google_calendar import get_google_calendars, get_google_events
            google_calendars = get_google_calendars()
            print(f"Found {len(google_calendars)} Google calendars")
            for cal in google_calendars:
                print(f"  • {cal.get('name', 'Unnamed')} (ID: {cal['id']}) - Selected: {cal['id'] in selected_calendars}")
            
            google_selected = [cal for cal in google_calendars if cal['id'] in selected_calendars]
            print(f"Selected {len(google_selected)} Google calendars")
            
            if google_selected:
                google_events = get_google_events(google_selected, start_date, end_date)
                print(f"Retrieved {len(google_events)} Google Calendar events")
                for i, event in enumerate(google_events[:5]):  # Print first 5 for debugging
                    print(f"  • Event {i+1}: {event.get('title')} - {event.get('start')} to {event.get('end')}")
                if len(google_events) > 5:
                    print(f"  • ... and {len(google_events) - 5} more events")
                
                all_events.extend(google_events)
                print(f"Added {len(google_events)} Google Calendar events to result")
        except Exception as e:
            print(f"Error getting Google events: {e}")
            import traceback
            traceback.print_exc()
    
    # Get Microsoft Calendar events if authenticated
    if 'microsoft_token' in session:
        try:
            print(f"\n-- Checking Microsoft Calendars --")
            from app.services.microsoft_calendar import get_microsoft_calendars, get_microsoft_events
            microsoft_calendars = get_microsoft_calendars()
            print(f"Found {len(microsoft_calendars)} Microsoft calendars")
            for cal in microsoft_calendars:
                print(f"  • {cal.get('name', 'Unnamed')} (ID: {cal['id']}) - Selected: {cal['id'] in selected_calendars}")
            
            microsoft_selected = [cal for cal in microsoft_calendars if cal['id'] in selected_calendars]
            print(f"Selected {len(microsoft_selected)} Microsoft calendars")
            
            if microsoft_selected:
                microsoft_events = get_microsoft_events(microsoft_selected, start_date, end_date)
                print(f"Retrieved {len(microsoft_events)} Microsoft Calendar events")
                for i, event in enumerate(microsoft_events[:5]):  # Print first 5 for debugging
                    print(f"  • Event {i+1}: {event.get('title')} - {event.get('start')} to {event.get('end')}")
                if len(microsoft_events) > 5:
                    print(f"  • ... and {len(microsoft_events) - 5} more events")
                
                all_events.extend(microsoft_events)
                print(f"Added {len(microsoft_events)} Microsoft Calendar events to result")
        except Exception as e:
            print(f"Error getting Microsoft events: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary of all events
    print(f"\n-- Calendar Events Summary --")
    print(f"Total events retrieved: {len(all_events)}")
    
    # Ensure all datetime objects have consistent timezone information
    timezone_fixed = 0
    for event in all_events:
        # Convert string dates to datetime objects
        if isinstance(event['start'], str):
            event['start'] = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
        if isinstance(event['end'], str):
            event['end'] = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
        
        # Make timezone-aware if they're naive
        if event['start'].tzinfo is None:
            # Use UTC as default timezone for naive datetimes
            from datetime import timezone
            event['start'] = event['start'].replace(tzinfo=timezone.utc)
            timezone_fixed += 1
        if event['end'].tzinfo is None:
            from datetime import timezone
            event['end'] = event['end'].replace(tzinfo=timezone.utc)
            timezone_fixed += 1
    
    if timezone_fixed > 0:
        print(f"Fixed timezone for {timezone_fixed} date/time values")
    
    print(f"==== END CALENDAR EVENT RETRIEVAL ====\n")
    
    return all_events

def find_alternative_slots(time_slots, all_events, buffer_minutes=15):
    """
    Find alternative time slots when requested times are unavailable.
    
    Args:
        time_slots (list): List of requested time slots
        all_events (list): List of calendar events
        buffer_minutes (int, optional): Buffer time between events. Defaults to 15.
        
    Returns:
        list: List of alternative time slots
    """
    # This is a placeholder implementation
    # In a real implementation, you would use more sophisticated logic
    suggested_slots = []
    
    try:
        # Ensure we're working with timezone-aware datetimes
        from datetime import timezone
        
        # For now, just suggest times 1 hour later than requested slots
        for slot in time_slots:
            if not slot['available']:
                # Ensure slot times are timezone-aware
                start_time = slot['start_time']
                end_time = slot['end_time']
                
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=timezone.utc)
                
                # Create a new slot 1 hour later
                new_start = start_time + timedelta(hours=1)
                new_end = end_time + timedelta(hours=1)
                
                # Check if this new slot is available
                is_available = True
                for event in all_events:
                    event_start = event['start']
                    event_end = event['end']
                    
                    # Ensure event times are timezone-aware
                    if event_start.tzinfo is None:
                        event_start = event_start.replace(tzinfo=timezone.utc)
                    if event_end.tzinfo is None:
                        event_end = event_end.replace(tzinfo=timezone.utc)
                    
                    try:
                        # Check if new slot overlaps with existing event
                        if ((event_start <= new_start < event_end) or
                            (event_start < new_end <= event_end) or
                            (new_start <= event_start and event_end <= new_end)):
                            is_available = False
                            break
                    except Exception as e:
                        print(f"Error checking availability for alternative slot: {str(e)}")
                        is_available = False
                        break
                
                if is_available:
                    suggested_slots.append({
                        'start_time': new_start,
                        'end_time': new_end,
                        'available': True,
                        'conflicts': [],
                        'context': f"Alternative to {start_time.strftime('%A, %b %d %I:%M %p')}"
                    })
    except Exception as e:
        print(f"Error finding alternative slots: {str(e)}")
    
    return suggested_slots 