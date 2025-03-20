from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for, flash
from app.services.claude_service import analyze_screenshot as claude_analyze_screenshot
from app.services.availability import check_availability, find_available_slots
from app.utils.date_utils import parse_date_range
from app.services.google_calendar import get_google_events
from app.services.microsoft_calendar import get_microsoft_events
from app.services.apple_calendar import get_apple_calendars, get_apple_events
import json
import base64
import os
import platform
from datetime import datetime, timedelta, time as dt_time
from PIL import Image, ImageGrab
from io import BytesIO
import tempfile
import logging

# Set up logging
logger = logging.getLogger(__name__)

bp = Blueprint('screenshot', __name__, url_prefix='/screenshot')

def analyze_screenshot(filename):
    """
    Analyze screenshot using Claude API only
    """
    try:
        # Log start of analysis
        logger.info(f"Starting screenshot analysis for: {filename}")
        
        # Add debug info for the template
        debug_logs = []
        debug_logs.append({"message": f"Starting screenshot analysis for: {filename}", "type": "info"})
        
        # Check API configuration
        api_key = os.environ.get('CLAUDE_API_KEY')
        if not api_key:
            debug_logs.append({"message": "Claude API key not configured in environment", "type": "error"})
            debug_logs.append({"message": "Set CLAUDE_API_KEY environment variable", "type": "info"})
            debug_logs.append({"message": "Visit /screenshot/api_status to debug API setup", "type": "info"})
        else:
            mask = api_key[:4] + "..." + api_key[-2:] if len(api_key) > 6 else "***masked***"
            debug_logs.append({"message": f"API key found (masked: {mask})", "type": "info"})
            
        # Check image details
        try:
            image_size_kb = os.path.getsize(filename) / 1024
            with Image.open(filename) as img:
                width, height = img.size
                format = img.format
                mode = img.mode
                debug_logs.append({
                    "message": f"Image details: {width}x{height} pixels, {format}, {mode}, {image_size_kb:.1f} KB",
                    "type": "info"
                })
        except Exception as e:
            debug_logs.append({
                "message": f"Error getting image details: {str(e)}",
                "type": "warning"
            })
            
        debug_logs.append({"message": "Analyzing with Claude API...", "type": "info"})
        
        # Use Claude API for analysis
        result = claude_analyze_screenshot(filename)
        
        # Check if Claude analysis returned results
        if result and 'time_slots' in result and len(result.get('time_slots', [])) > 0:
            # Log success
            logger.info(f"Claude analysis successful: {len(result['time_slots'])} time slots found")
            debug_logs.append({"message": f"Claude analysis successful: {len(result['time_slots'])} time slots found", "type": "success"})
            
            # Format time slots for compatibility with existing code
            for slot in result['time_slots']:
                # Convert ISO format times to datetime objects
                if 'start' in slot:
                    start_time = datetime.fromisoformat(slot['start'])
                    slot['start_time'] = start_time
                
                if 'end' in slot:
                    end_time = datetime.fromisoformat(slot['end'])
                    slot['end_time'] = end_time
                elif 'duration_minutes' in slot and 'start_time' in slot:
                    # Calculate end time from start time and duration
                    slot['end_time'] = slot['start_time'] + timedelta(minutes=slot['duration_minutes'])
            
            # Add date field for compatibility
            if len(result['time_slots']) > 0 and 'start_time' in result['time_slots'][0]:
                result['date'] = result['time_slots'][0]['start_time'].date()
            
            # Add debug logs to result
            result['debug_logs'] = debug_logs
            return result
        else:
            # Claude didn't find any time slots
            logger.warning("Claude analysis didn't detect any time slots")
            debug_logs.append({"message": "Claude AI couldn't find any time slots in this image", "type": "warning"})
            debug_logs.append({"message": "Try a clearer screenshot or ensure the image contains time information", "type": "info"})
            
            # Get error message if available
            error_msg = result.get('error', "No time slots detected in the screenshot")
            analysis = result.get('analysis', "The image analysis couldn't detect any time information.")
            
            return {
                "error": error_msg,
                "analysis": analysis,
                "time_slots": [],
                "is_suggestion": False,
                "debug_logs": debug_logs
            }
    
    except Exception as e:
        logger.exception(f"Error in screenshot analysis: {str(e)}")
        return {
            "error": f"Error analyzing screenshot: {str(e)}",
            "time_slots": [],
            "is_suggestion": False,
            "analysis": "An error occurred while analyzing the screenshot",
            "debug_logs": [
                {"message": f"Error in screenshot analysis: {str(e)}", "type": "error"}
            ]
        }

@bp.route('/upload', methods=['POST'])
def upload_screenshot():
    """Handle screenshot upload and analysis"""
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
    filename = None
    
    # Check if a file was uploaded
    if 'screenshot' in request.files:
        file = request.files['screenshot']
        if file.filename != '':
            # Create a temporary file to save the uploaded image
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp:
                file.save(temp.name)
                filename = temp.name
                screenshot = Image.open(filename)
    
    # Check if a base64 encoded image was provided
    elif 'screenshot_data' in request.form:
        image_data = request.form['screenshot_data']
        if image_data.startswith('data:image'):
            # Extract the base64 part
            image_data = image_data.split(',')[1]
        
        # Decode the base64 image
        image_bytes = base64.b64decode(image_data)
        screenshot = Image.open(BytesIO(image_bytes))
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp:
            screenshot.save(temp.name)
            filename = temp.name
    
    # Check if we should grab from clipboard
    elif request.form.get('clipboard') == 'true':
        try:
            screenshot = ImageGrab.grabclipboard()
            if screenshot:
                # Save to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp:
                    screenshot.save(temp.name)
                    filename = temp.name
            else:
                return jsonify({'error': 'No image found in clipboard'}), 400
        except Exception as e:
            return jsonify({'error': f'Failed to grab from clipboard: {str(e)}'}), 400
    
    if not screenshot or not filename:
        return jsonify({'error': 'No screenshot provided'}), 400
    
    try:
        # Analyze the screenshot using our wrapper function that uses Claude
        result = analyze_screenshot(filename)
        
        # Delete the temporary file
        os.unlink(filename)
        
        if not result or 'time_slots' not in result or not result['time_slots']:
            # Use a more detailed error message and ensure debug logs are passed
            error_result = {
                'error': 'No time slots detected in the screenshot',
                'analysis': result.get('analysis', 'The analysis could not detect any time slots in the image.'),
                'debug_logs': result.get('debug_logs', [
                    {"message": "No time slots were detected in the screenshot", "type": "error"},
                    {"message": "Check that your screenshot contains clearly visible time information", "type": "info"},
                    {"message": "Make sure text in the image is clear and readable", "type": "info"}
                ])
            }
            return render_template('analysis_results.html', result=error_result)
        
        # Get all calendar events for the time range to display in the calendar view
        all_events = []
        
        # Find the earliest start time and latest end time from all slots
        earliest_start = min(slot['start_time'] for slot in result['time_slots'])
        latest_end = max(slot['end_time'] for slot in result['time_slots'])
        
        # Always use current date range for calendar display
        # This ensures we show current calendar events even if screenshot has historical dates
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        calendar_start = today
        calendar_end = today + timedelta(days=7)  # Look 1 week ahead
        
        print(f"DEBUG: Using current date range for calendar display: {calendar_start} to {calendar_end}")
        print(f"DEBUG: Original date range from screenshot: {earliest_start} to {latest_end}")
        
        # Get selected calendars from session
        selected_calendars = session.get('selected_calendars', [])
        
        # Get Apple Calendar events if on macOS
        if platform.system() == 'Darwin':
            apple_calendars = get_apple_calendars()
            apple_selected = [cal for cal in apple_calendars if cal['id'] in selected_calendars]
            if apple_selected:
                try:
                    apple_events = get_apple_events(apple_selected, calendar_start, calendar_end)
                    all_events.extend(apple_events)
                except Exception as e:
                    print(f"Error getting Apple events: {e}")
        
        # Get Google Calendar events if authenticated
        if 'google_token' in session:
            from app.services.google_calendar import get_google_calendars, get_google_events
            google_calendars = get_google_calendars()
            google_selected = [cal for cal in google_calendars if cal['id'] in selected_calendars]
            if google_selected:
                try:
                    google_events = get_google_events(google_selected, calendar_start, calendar_end)
                    all_events.extend(google_events)
                except Exception as e:
                    print(f"Error getting Google events: {e}")
        
        # Get Microsoft Calendar events if authenticated
        if 'microsoft_token' in session:
            from app.services.microsoft_calendar import get_microsoft_calendars, get_microsoft_events
            microsoft_calendars = get_microsoft_calendars()
            microsoft_selected = [cal for cal in microsoft_calendars if cal['id'] in selected_calendars]
            if microsoft_selected:
                try:
                    microsoft_events = get_microsoft_events(microsoft_selected, calendar_start, calendar_end)
                    all_events.extend(microsoft_events)
                except Exception as e:
                    print(f"Error getting Microsoft events: {e}")
        
        # Check availability for each time slot
        for slot in result['time_slots']:
            try:
                # Find conflicts with any event
                slot['conflicts'] = []
                slot['available'] = True
                
                for event in all_events:
                    event_start = event['start'] if isinstance(event['start'], datetime) else datetime.fromisoformat(event['start'])
                    event_end = event['end'] if isinstance(event['end'], datetime) else datetime.fromisoformat(event['end'])
                    
                    # Check for overlap: if start_time < event_end and end_time > event_start
                    if slot['start_time'] < event_end and slot['end_time'] > event_start:
                        slot['available'] = False
                        slot['conflicts'].append(event)
            except Exception as e:
                slot['available'] = False
                slot['error'] = str(e)
        
        # Find available slots
        suggested_slots = find_available_slots(result['time_slots'], result.get('date'))
        
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
        return render_template('analysis_results.html', result={
            'error': str(e),
            'debug_logs': [
                {"message": f"Error processing screenshot: {str(e)}", "type": "error"},
                {"message": "Check application logs for more details", "type": "info"}
            ]
        })

@bp.route('/analyze', methods=['POST'])
def analyze_clipboard():
    """Analyze screenshot from clipboard"""
    # This route is mainly for when JS sends a request to analyze the clipboard
    # The actual implementation is similar to the upload route but always uses clipboard
    
    # Check if at least one calendar is selected or if Apple Calendar is available on macOS
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
        
        # If still no calendars, return an error
        if not calendars_found:
            return jsonify({'error': 'Please select at least one calendar before analyzing screenshots'}), 400
    
    try:
        screenshot = ImageGrab.grabclipboard()
        if not screenshot:
            return jsonify({'error': 'No image found in clipboard'}), 400
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp:
            screenshot.save(temp.name)
            filename = temp.name
        
        # Analyze the screenshot using our wrapper function that uses Claude
        result = analyze_screenshot(filename)
        
        # Delete the temporary file
        os.unlink(filename)
        
        if not result or 'time_slots' not in result or not result['time_slots']:
            # Use a more detailed error message and ensure debug logs are passed
            error_result = {
                'error': 'No time slots detected in the screenshot',
                'analysis': result.get('analysis', 'The analysis could not detect any time slots in the image.'),
                'debug_logs': result.get('debug_logs', [
                    {"message": "No time slots were detected in the screenshot", "type": "error"},
                    {"message": "Check that your screenshot contains clearly visible time information", "type": "info"},
                    {"message": "Make sure text in the image is clear and readable", "type": "info"}
                ])
            }
            return render_template('analysis_results.html', result=error_result)
        
        # Get all calendar events for the time range to display in the calendar view
        all_events = []
        
        # Find the earliest start time and latest end time from all slots
        earliest_start = min(slot['start_time'] for slot in result['time_slots'])
        latest_end = max(slot['end_time'] for slot in result['time_slots'])
        
        # Always use current date range for calendar display
        # This ensures we show current calendar events even if screenshot has historical dates
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        calendar_start = today
        calendar_end = today + timedelta(days=7)  # Look 1 week ahead
        
        print(f"DEBUG: Using current date range for calendar display: {calendar_start} to {calendar_end}")
        print(f"DEBUG: Original date range from screenshot: {earliest_start} to {latest_end}")
        
        # Get selected calendars from session
        selected_calendars = session.get('selected_calendars', [])
        
        # Get Apple Calendar events if on macOS
        if platform.system() == 'Darwin':
            apple_calendars = get_apple_calendars()
            apple_selected = [cal for cal in apple_calendars if cal['id'] in selected_calendars]
            if apple_selected:
                try:
                    apple_events = get_apple_events(apple_selected, calendar_start, calendar_end)
                    all_events.extend(apple_events)
                except Exception as e:
                    print(f"Error getting Apple events: {e}")
        
        # Get Google Calendar events if authenticated
        if 'google_token' in session:
            from app.services.google_calendar import get_google_calendars, get_google_events
            google_calendars = get_google_calendars()
            google_selected = [cal for cal in google_calendars if cal['id'] in selected_calendars]
            if google_selected:
                try:
                    google_events = get_google_events(google_selected, calendar_start, calendar_end)
                    all_events.extend(google_events)
                except Exception as e:
                    print(f"Error getting Google events: {e}")
        
        # Get Microsoft Calendar events if authenticated
        if 'microsoft_token' in session:
            from app.services.microsoft_calendar import get_microsoft_calendars, get_microsoft_events
            microsoft_calendars = get_microsoft_calendars()
            microsoft_selected = [cal for cal in microsoft_calendars if cal['id'] in selected_calendars]
            if microsoft_selected:
                try:
                    microsoft_events = get_microsoft_events(microsoft_selected, calendar_start, calendar_end)
                    all_events.extend(microsoft_events)
                except Exception as e:
                    print(f"Error getting Microsoft events: {e}")
        
        # Check availability for each time slot
        for slot in result['time_slots']:
            try:
                # Find conflicts with any event
                slot['conflicts'] = []
                slot['available'] = True
                
                for event in all_events:
                    event_start = event['start'] if isinstance(event['start'], datetime) else datetime.fromisoformat(event['start'])
                    event_end = event['end'] if isinstance(event['end'], datetime) else datetime.fromisoformat(event['end'])
                    
                    # Check for overlap: if start_time < event_end and end_time > event_start
                    if slot['start_time'] < event_end and slot['end_time'] > event_start:
                        slot['available'] = False
                        slot['conflicts'].append(event)
            except Exception as e:
                slot['available'] = False
                slot['error'] = str(e)
        
        # Find available slots
        suggested_slots = find_available_slots(result['time_slots'], result.get('date'))
        
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
        return render_template('analysis_results.html', result={
            'error': str(e),
            'debug_logs': [
                {"message": f"Error processing clipboard image: {str(e)}", "type": "error"},
                {"message": "Check application logs for more details", "type": "info"}
            ]
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
    """Check API status and environment"""
    debug_logs = []
    
    # Check Python version and platform
    import sys
    python_info = f"Python {sys.version.split(' ')[0]} on {platform.system()} {platform.release()}"
    debug_logs.append({"message": python_info, "type": "info"})
    
    # Check for required packages
    required_packages = ["anthropic", "PIL", "flask", "requests"]
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == "PIL":
                import PIL
                debug_logs.append({"message": f"✓ {package} v{PIL.__version__} installed", "type": "success"})
            elif package == "flask":
                import flask
                debug_logs.append({"message": f"✓ {package} v{flask.__version__} installed", "type": "success"})
            elif package == "anthropic":
                import anthropic
                debug_logs.append({"message": f"✓ {package} v{anthropic.__version__} installed", "type": "success"})
            elif package == "requests":
                import requests
                debug_logs.append({"message": f"✓ {package} v{requests.__version__} installed", "type": "success"})
        except (ImportError, AttributeError):
            missing_packages.append(package)
            debug_logs.append({"message": f"✗ {package} not found", "type": "error"})
    
    if missing_packages:
        debug_logs.append({"message": f"Missing required packages: {', '.join(missing_packages)}", "type": "error"})
    
    # Check API key configuration
    api_key = os.environ.get('CLAUDE_API_KEY')
    if not api_key:
        debug_logs.append({"message": "CLAUDE_API_KEY environment variable not set", "type": "error"})
    else:
        # Basic check for key format (Claude API keys start with 'sk-')
        if api_key.startswith('sk-'):
            masked_key = f"{api_key[:5]}...{api_key[-2:]}"
            debug_logs.append({"message": f"API key found with correct format (masked: {masked_key})", "type": "success"})
        else:
            debug_logs.append({"message": f"API key has invalid format (should start with 'sk-')", "type": "error"})
    
    # Check network connectivity to Claude API
    from app.services.claude_service import check_network_connectivity
    connectivity_success, connectivity_results = check_network_connectivity()
    
    # Add connectivity logs to our debug logs
    debug_logs.extend(connectivity_results)
    
    # Create network status for the template
    network_status = {
        "success": connectivity_success,
        "message": connectivity_results[-1]["message"] if connectivity_results else "Unknown connectivity issue"
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
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=10,
                messages=[{"role": "user", "content": "Say hello"}]
            )
            
            duration = time.time() - start_time
            
            api_access = {
                "success": True, 
                "message": f"API access successful (response time: {duration:.2f}s)",
                "model": "claude-3-5-sonnet-20240620",
                "response": response.content[0].text if response.content else "No content"
            }
            
            debug_logs.append({"message": api_access["message"], "type": "success"})
            debug_logs.append({"message": f"API response: {api_access['response']}", "type": "info"})
            
        except Exception as e:
            api_access = {"success": False, "message": str(e)}
            debug_logs.append({"message": f"API access failed: {str(e)}", "type": "error"})
    
    # Return the status information
    status_result = {
        "python": python_info,
        "packages": {"required": required_packages, "missing": missing_packages},
        "api_key": {"configured": bool(api_key), "valid_format": bool(api_key and api_key.startswith('sk-'))},
        "network": network_status,
        "api_access": api_access,
        "debug_logs": debug_logs
    }
    
    return render_template('api_status.html', result=status_result) 