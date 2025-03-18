from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for, flash
from app.services.screenshot_analyzer import analyze_screenshot
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

bp = Blueprint('screenshot', __name__, url_prefix='/screenshot')

@bp.route('/upload', methods=['POST'])
def upload_screenshot():
    """Handle screenshot upload and analysis"""
    # Check if at least one calendar is selected
    if 'selected_calendars' not in session or not session['selected_calendars']:
        # If no calendars are selected but user is on macOS, check if Apple Calendar is available
        if platform.system() == 'Darwin':
            apple_calendars = get_apple_calendars()
            if apple_calendars:
                # Automatically select the first Apple Calendar
                session['selected_calendars'] = [apple_calendars[0]['id']]
                flash('Using Apple Calendar for availability check', 'info')
            else:
                flash('Please select at least one calendar before analyzing screenshots', 'warning')
                return redirect(url_for('calendar.manage_calendars'))
        else:
            # Not on macOS, need to authenticate with Google or Microsoft
            flash('Please connect to a calendar service before analyzing screenshots', 'warning')
            return redirect(url_for('calendar.manage_calendars'))
    
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
        # Analyze the screenshot
        result = analyze_screenshot(filename)
        
        # Delete the temporary file
        os.unlink(filename)
        
        if not result or 'time_slots' not in result or not result['time_slots']:
            return render_template('analysis_results.html', result={'error': 'No time slots detected in the screenshot'})
        
        # Check availability for each time slot
        for slot in result['time_slots']:
            try:
                slot['available'] = check_availability(slot['start_time'], slot['end_time'])
            except Exception as e:
                slot['available'] = False
                slot['error'] = str(e)
        
        # Find available slots
        suggested_slots = find_available_slots(result['time_slots'], result['date'])
        
        return render_template('analysis_results.html', 
                            result=result, 
                            suggested_slots=suggested_slots)
    
    except Exception as e:
        return render_template('analysis_results.html', result={'error': str(e)})

@bp.route('/analyze', methods=['POST'])
def analyze_clipboard():
    """Analyze screenshot from clipboard"""
    # This route is mainly for when JS sends a request to analyze the clipboard
    # The actual implementation is similar to the upload route but always uses clipboard
    
    # Check if at least one calendar is selected or if Apple Calendar is available on macOS
    if 'selected_calendars' not in session or not session['selected_calendars']:
        # If no calendars are selected but user is on macOS, check if Apple Calendar is available
        if platform.system() == 'Darwin':
            apple_calendars = get_apple_calendars()
            if apple_calendars:
                # Automatically select the first Apple Calendar
                session['selected_calendars'] = [apple_calendars[0]['id']]
                flash('Using Apple Calendar for availability check', 'info')
            else:
                return jsonify({'error': 'Please select at least one calendar before analyzing screenshots'}), 400
        else:
            # Not on macOS, need to authenticate with Google or Microsoft
            return jsonify({'error': 'Please connect to a calendar service before analyzing screenshots'}), 400
    
    try:
        screenshot = ImageGrab.grabclipboard()
        if not screenshot:
            return jsonify({'error': 'No image found in clipboard'}), 400
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp:
            screenshot.save(temp.name)
            filename = temp.name
        
        # Analyze the screenshot
        result = analyze_screenshot(filename)
        
        # Delete the temporary file
        os.unlink(filename)
        
        if not result or 'time_slots' not in result or not result['time_slots']:
            return render_template('analysis_results.html', result={'error': 'No time slots detected in the screenshot'})
        
        # Check availability for each time slot
        for slot in result['time_slots']:
            try:
                slot['available'] = check_availability(slot['start_time'], slot['end_time'])
            except Exception as e:
                slot['available'] = False
                slot['error'] = str(e)
        
        # Find available slots
        suggested_slots = find_available_slots(result['time_slots'], result['date'])
        
        return render_template('analysis_results.html', 
                            result=result, 
                            suggested_slots=suggested_slots)
    
    except Exception as e:
        return render_template('analysis_results.html', result={'error': str(e)})

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