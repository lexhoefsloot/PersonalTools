from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for, flash
from app.services.google_calendar import get_google_calendars, get_google_events
from app.services.microsoft_calendar import get_microsoft_calendars, get_microsoft_events
from app.services.apple_calendar import get_apple_calendars, get_apple_events
from app.services.thunderbird_calendar import get_thunderbird_calendars, get_thunderbird_events
from app.services.availability import check_availability, find_available_slots
from app.utils.date_utils import parse_date_range
import json
import platform
import logging
from datetime import datetime, timedelta
import os
import glob

bp = Blueprint('calendar', __name__, url_prefix='/calendar')

@bp.route('/list')
def list_calendars():
    """List all available calendars from connected accounts"""
    calendars = []
    
    print("DEBUG: Starting list_calendars function")
    print(f"DEBUG: Current platform is {platform.system()}")
    
    # Check if running on macOS for Apple Calendar
    if platform.system() == 'Darwin':
        print("DEBUG: Attempting to get Apple calendars")
        try:
            apple_calendars = get_apple_calendars()
            print(f"DEBUG: Found {len(apple_calendars)} Apple calendars")
            calendars.extend(apple_calendars)
        except Exception as e:
            print(f"DEBUG: Error getting Apple calendars: {str(e)}")
    
    # Check for Thunderbird calendars using improved detection
    print("DEBUG: Attempting to get Thunderbird calendars with improved detection")
    try:
        from app.services.thunderbird_calendar import find_all_calendar_databases
        thunderbird_dbs = find_all_calendar_databases()
        
        if thunderbird_dbs:
            thunderbird_calendars = get_thunderbird_calendars()
            print(f"DEBUG: Found {len(thunderbird_calendars)} Thunderbird calendars")
            calendars.extend(thunderbird_calendars)
            
            # If no calendars are selected yet, auto-select all Thunderbird calendars
            if ('selected_calendars' not in session or not session['selected_calendars']) and thunderbird_calendars:
                print("DEBUG: Auto-selecting Thunderbird calendars")
                session['selected_calendars'] = [cal['id'] for cal in thunderbird_calendars]
                flash('Using Thunderbird calendars for availability check', 'info')
                logging.info(f"Auto-selected {len(thunderbird_calendars)} Thunderbird calendars")
    except Exception as e:
        print(f"DEBUG: Error with improved Thunderbird detection: {str(e)}")
        # Fall back to the old method
        thunderbird_available = False
        thunderbird_profile_paths = [
            os.path.expanduser("~/.thunderbird/*/"),
            os.path.expanduser("~/.icedove/*/"),  # Debian's fork of Thunderbird
            os.path.expanduser("~/.mozilla-thunderbird/*/"),  # Older versions
            os.path.expanduser("~/.local/share/thunderbird/*/"),
            os.path.expanduser("~/Library/Thunderbird/Profiles/*/")  # macOS
        ]
        
        for path_pattern in thunderbird_profile_paths:
            profiles = glob.glob(path_pattern)
            for profile in profiles:
                if os.path.exists(os.path.join(profile, "calendar-data")):
                    thunderbird_available = True
                    break
        
        if thunderbird_available:
            print("DEBUG: Attempting to get Thunderbird calendars with legacy method")
            try:
                thunderbird_calendars = get_thunderbird_calendars()
                print(f"DEBUG: Found {len(thunderbird_calendars)} Thunderbird calendars")
                calendars.extend(thunderbird_calendars)
                
                # If no calendars are selected yet, auto-select all Thunderbird calendars
                if ('selected_calendars' not in session or not session['selected_calendars']) and thunderbird_calendars:
                    print("DEBUG: Auto-selecting Thunderbird calendars")
                    session['selected_calendars'] = [cal['id'] for cal in thunderbird_calendars]
                    flash('Using Thunderbird calendars for availability check', 'info')
                    logging.info(f"Auto-selected {len(thunderbird_calendars)} Thunderbird calendars")
            except Exception as e:
                print(f"DEBUG: Error getting Thunderbird calendars: {str(e)}")
    
    # Get Google calendars if authenticated
    if 'google_token' in session:
        print("DEBUG: Google token found in session")
        try:
            google_calendars = get_google_calendars(session['google_token'])
            print(f"DEBUG: Found {len(google_calendars)} Google calendars")
            for cal in google_calendars:
                cal['provider'] = 'google'
                calendars.append(cal)
        except Exception as e:
            print(f"DEBUG: Error getting Google calendars: {str(e)}")
    else:
        print("DEBUG: No Google token found in session")
    
    # Get Microsoft calendars if authenticated
    if 'microsoft_token' in session:
        print("DEBUG: Microsoft token found in session")
        try:
            microsoft_calendars = get_microsoft_calendars(session['microsoft_token'])
            print(f"DEBUG: Found {len(microsoft_calendars)} Microsoft calendars")
            for cal in microsoft_calendars:
                cal['provider'] = 'microsoft'
                calendars.append(cal)
        except Exception as e:
            print(f"DEBUG: Error getting Microsoft calendars: {str(e)}")
    else:
        print("DEBUG: No Microsoft token found in session")
    
    print(f"DEBUG: Total calendars found: {len(calendars)}")
    return render_template('calendars.html', calendars=calendars)

@bp.route('/select', methods=['POST'])
def select_calendars():
    """Save selected calendars to session"""
    selected_calendars = request.form.getlist('selected_calendars')
    
    if not selected_calendars:
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
                    selected_calendars = [cal['id'] for cal in thunderbird_calendars]
                    flash('Using Thunderbird calendars for availability check', 'info')
                    calendars_found = True
                    logging.info(f"Auto-selected {len(thunderbird_calendars)} Thunderbird calendars")
        except Exception as e:
            logging.warning(f"Failed to auto-detect Thunderbird calendars: {e}")
        
        # If no Thunderbird calendars, try Apple Calendar on macOS
        if not calendars_found and platform.system() == 'Darwin':
            apple_calendars = get_apple_calendars()
            if apple_calendars:
                # Automatically select the first Apple Calendar
                selected_calendars = [apple_calendars[0]['id']]
                flash('Using Apple Calendar for availability check', 'info')
                calendars_found = True
        
        # If still no calendars, return an error
        if not calendars_found:
            flash('Please select at least one calendar', 'warning')
            return redirect(url_for('calendar.list_calendars'))
    
    session['selected_calendars'] = selected_calendars
    flash('Calendar selection saved', 'success')
    return redirect(url_for('index'))

@bp.route('/availability', methods=['POST'])
def check_calendar_availability():
    """Check availability for given time slots"""
    data = request.get_json()
    
    if not data or 'time_slots' not in data:
        return jsonify({'error': 'No time slots provided'}), 400
    
    time_slots = data['time_slots']
    selected_calendars = session.get('selected_calendars', [])
    
    if not selected_calendars:
        return jsonify({'error': 'No calendars selected'}), 400
    
    # Get events from all selected calendars
    all_events = []
    
    for calendar_id in selected_calendars:
        provider, cal_id = calendar_id.split(':', 1)
        
        # Get date range from time slots
        start_date, end_date = parse_date_range(time_slots)
        
        if provider == 'google' and 'google_token' in session:
            events = get_google_events(session['google_token'], cal_id, start_date, end_date)
            all_events.extend(events)
            
        elif provider == 'microsoft' and 'microsoft_token' in session:
            events = get_microsoft_events(session['microsoft_token'], cal_id, start_date, end_date)
            all_events.extend(events)
            
        elif provider == 'apple' and platform.system() == 'Darwin':
            events = get_apple_events([{'id': cal_id, 'provider': 'apple'}], start_date, end_date)
            all_events.extend(events)
            
        elif provider == 'thunderbird':
            events = get_thunderbird_events([{'id': calendar_id, 'provider': 'thunderbird'}], start_date, end_date)
            all_events.extend(events)
    
    # Check availability for each time slot
    availability_results = check_availability(time_slots, all_events)
    
    return jsonify(availability_results)

@bp.route('/suggest', methods=['POST'])
def suggest_times():
    """Suggest available time slots based on date range"""
    data = request.get_json()
    
    if not data or 'date_range' not in data:
        return jsonify({'error': 'No date range provided'}), 400
    
    date_range = data['date_range']
    selected_calendars = session.get('selected_calendars', [])
    
    if not selected_calendars:
        return jsonify({'error': 'No calendars selected'}), 400
    
    # Parse date range
    start_date, end_date = parse_date_range([date_range])
    
    # Get events from all selected calendars
    all_events = []
    
    for calendar_id in selected_calendars:
        provider, cal_id = calendar_id.split(':', 1)
        
        if provider == 'google' and 'google_token' in session:
            events = get_google_events(session['google_token'], cal_id, start_date, end_date)
            all_events.extend(events)
        
        elif provider == 'microsoft' and 'microsoft_token' in session:
            events = get_microsoft_events(session['microsoft_token'], cal_id, start_date, end_date)
            all_events.extend(events)
            
        elif provider == 'apple' and platform.system() == 'Darwin':
            events = get_apple_events([{'id': cal_id, 'provider': 'apple'}], start_date, end_date)
            all_events.extend(events)
            
        elif provider == 'thunderbird':
            events = get_thunderbird_events([{'id': calendar_id, 'provider': 'thunderbird'}], start_date, end_date)
            all_events.extend(events)
    
    # Find available slots
    duration_minutes = data.get('duration_minutes', 60)  # Default to 60-minute meetings
    available_slots = find_available_slots(start_date, end_date, all_events, duration_minutes)
    
    return jsonify(available_slots)

@bp.route('/events')
def get_events():
    """Get events from all selected calendars for a given time range"""
    start_time_str = request.args.get('start')
    end_time_str = request.args.get('end')
    
    if not start_time_str or not end_time_str:
        now = datetime.now()
        start_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        try:
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
        except ValueError:
            # Handle ISO 8601 format from FullCalendar which may include 'Z' for UTC
            start_time_str = start_time_str.replace('Z', '+00:00')
            end_time_str = end_time_str.replace('Z', '+00:00')
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
    
    selected_calendars = session.get('selected_calendars', [])
    all_events = []
    
    # If no calendars are selected, attempt to use all available calendars
    if not selected_calendars:
        # Try to get all calendars from all providers
        all_calendars = []
        
        # Check for Apple Calendar if on macOS
        if platform.system() == 'Darwin':
            try:
                apple_calendars = get_apple_calendars()
                for cal in apple_calendars:
                    cal['provider'] = 'apple'
                    all_calendars.append(cal)
            except Exception as e:
                logging.error(f"Error getting Apple calendars: {str(e)}")
        
        # Check for Thunderbird Calendar
        try:
            thunderbird_calendars = get_thunderbird_calendars()
            for cal in thunderbird_calendars:
                cal['provider'] = 'thunderbird'
                all_calendars.append(cal)
        except Exception as e:
            logging.error(f"Error getting Thunderbird calendars: {str(e)}")
        
        # Check for Google Calendar if authenticated
        if 'google_token' in session:
            try:
                google_calendars = get_google_calendars(session['google_token'])
                for cal in google_calendars:
                    cal['provider'] = 'google'
                    all_calendars.append(cal)
            except Exception as e:
                logging.error(f"Error getting Google calendars: {str(e)}")
        
        # Check for Microsoft Calendar if authenticated
        if 'microsoft_token' in session:
            try:
                microsoft_calendars = get_microsoft_calendars(session['microsoft_token'])
                for cal in microsoft_calendars:
                    cal['provider'] = 'microsoft'
                    all_calendars.append(cal)
            except Exception as e:
                logging.error(f"Error getting Microsoft calendars: {str(e)}")
        
        # If we found any calendars, use all of them
        if all_calendars:
            selected_calendars = [cal['id'] for cal in all_calendars]
    
    # Collect events from Apple Calendar if on macOS
    if platform.system() == 'Darwin':
        try:
            apple_calendars = [cal for cal in get_apple_calendars() if cal['id'] in selected_calendars]
            if apple_calendars:
                apple_events = get_apple_events(apple_calendars, start_time, end_time)
                for event in apple_events:
                    event['provider'] = 'apple'
                all_events.extend(apple_events)
        except Exception as e:
            logging.error(f"Error getting Apple events: {str(e)}")
    
    # Collect events from Thunderbird Calendar if available
    try:
        thunderbird_calendars = [cal for cal in get_thunderbird_calendars() if cal['id'] in selected_calendars]
        if thunderbird_calendars:
            thunderbird_events = get_thunderbird_events(thunderbird_calendars, start_time, end_time)
            for event in thunderbird_events:
                event['provider'] = 'thunderbird'
            all_events.extend(thunderbird_events)
    except Exception as e:
        logging.error(f"Error getting Thunderbird events: {str(e)}")
    
    # Collect events from Google Calendar if authenticated
    if 'google_token' in session:
        try:
            google_calendars = [cal for cal in get_google_calendars() if cal['id'] in selected_calendars]
            if google_calendars:
                google_events = get_google_events(google_calendars, start_time, end_time)
                for event in google_events:
                    event['provider'] = 'google'
                all_events.extend(google_events)
        except Exception as e:
            logging.error(f"Error getting Google events: {str(e)}")
    
    # Collect events from Microsoft Calendar if authenticated
    if 'microsoft_token' in session:
        try:
            microsoft_calendars = [cal for cal in get_microsoft_calendars() if cal['id'] in selected_calendars]
            if microsoft_calendars:
                microsoft_events = get_microsoft_events(microsoft_calendars, start_time, end_time)
                for event in microsoft_events:
                    event['provider'] = 'microsoft'
                all_events.extend(microsoft_events)
        except Exception as e:
            logging.error(f"Error getting Microsoft events: {str(e)}")
    
    return jsonify({'events': all_events})

@bp.route('/availability')
def check_availability():
    """Check availability for a given time range across all selected calendars"""
    start_time_str = request.args.get('start')
    end_time_str = request.args.get('end')
    
    if not start_time_str or not end_time_str:
        return jsonify({'error': 'Start and end times are required'}), 400
    
    try:
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)
    except ValueError:
        return jsonify({'error': 'Invalid time format. Use ISO format (YYYY-MM-DDTHH:MM:SS)'}), 400
    
    # Get events from the get_events route
    events_response = get_events()
    
    # If there was an error getting events, return that error
    if isinstance(events_response, tuple) and len(events_response) > 1 and events_response[1] != 200:
        return events_response
    
    events_data = events_response.get_json()
    events = events_data.get('events', [])
    
    # Check if the requested time slot overlaps with any existing events
    is_available = True
    conflicting_events = []
    
    for event in events:
        event_start = datetime.fromisoformat(event['start'])
        event_end = datetime.fromisoformat(event['end'])
        
        # Check for overlap
        if (start_time < event_end and end_time > event_start):
            is_available = False
            conflicting_events.append(event)
    
    return jsonify({
        'is_available': is_available,
        'start': start_time.isoformat(),
        'end': end_time.isoformat(),
        'conflicting_events': conflicting_events
    }) 