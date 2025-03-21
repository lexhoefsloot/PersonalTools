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
from datetime import datetime, timedelta, timezone
import os
import glob
import sqlite3

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
    
    print(f"DEBUG: /events route called with start={start_time_str}, end={end_time_str}")
    
    if not start_time_str or not end_time_str:
        now = datetime.now()
        start_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
        print(f"DEBUG: Using default time range: {start_time} - {end_time}")
    else:
        try:
            # Handle various date format issues
            # 1. Replace space before timezone with '+'
            if ' ' in start_time_str and '+' not in start_time_str and '-' not in start_time_str.split('T')[1]:
                start_time_str = start_time_str.replace(' ', '+', 1)
            if ' ' in end_time_str and '+' not in end_time_str and '-' not in end_time_str.split('T')[1]:
                end_time_str = end_time_str.replace(' ', '+', 1)
            
            # 2. Handle ISO 8601 format with 'Z' for UTC
            if start_time_str.endswith('Z'):
                start_time_str = start_time_str.replace('Z', '+00:00')
            if end_time_str.endswith('Z'):
                end_time_str = end_time_str.replace('Z', '+00:00')
            
            # 3. Add timezone if none specified
            if 'T' in start_time_str and '+' not in start_time_str and '-' not in start_time_str.split('T')[1]:
                start_time_str += '+00:00'
            if 'T' in end_time_str and '+' not in end_time_str and '-' not in end_time_str.split('T')[1]:
                end_time_str += '+00:00'
            
            print(f"DEBUG: Formatted date strings: start={start_time_str}, end={end_time_str}")
            
            try:
                start_time = datetime.fromisoformat(start_time_str)
                end_time = datetime.fromisoformat(end_time_str)
                print(f"DEBUG: Successfully parsed time range: {start_time} - {end_time}")
            except ValueError as e:
                print(f"ERROR: Could not parse dates after formatting: {e}")
                # Last resort: try parsing with dateutil
                try:
                    from dateutil import parser
                    start_time = parser.parse(start_time_str)
                    end_time = parser.parse(end_time_str)
                    print(f"DEBUG: Parsed with dateutil: {start_time} - {end_time}")
                except Exception as e:
                    error_msg = f"Invalid date format: {str(e)}. Received: start={start_time_str}, end={end_time_str}"
                    print(f"ERROR: {error_msg}")
                    return jsonify({'error': error_msg}), 400
        except Exception as e:
            error_msg = f"Error processing dates: {str(e)}. Received: start={start_time_str}, end={end_time_str}"
            print(f"ERROR: {error_msg}")
            return jsonify({'error': error_msg}), 400
    
    # Ensure the datetimes have timezone info for proper comparison
    if start_time.tzinfo is None:
        print(f"DEBUG: Adding timezone info to start_time")
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        print(f"DEBUG: Adding timezone info to end_time")
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    print(f"DEBUG: Final date range with timezone: {start_time} to {end_time}")
    
    selected_calendars = session.get('selected_calendars', [])
    print(f"DEBUG: Selected calendars from session: {selected_calendars}")
    all_events = []
    
    # If no calendars are selected, attempt to use all available calendars
    if not selected_calendars:
        print("DEBUG: No calendars selected, attempting to use all available calendars")
        # Try to get all calendars from all providers
        all_calendars = []
        
        # Check for Apple Calendar if on macOS
        if platform.system() == 'Darwin':
            try:
                apple_calendars = get_apple_calendars()
                for cal in apple_calendars:
                    cal['provider'] = 'apple'
                    all_calendars.append(cal)
                print(f"DEBUG: Found {len(apple_calendars)} Apple calendars")
            except Exception as e:
                logging.error(f"Error getting Apple calendars: {str(e)}")
                print(f"DEBUG: Error getting Apple calendars: {str(e)}")
        
        # Check for Thunderbird Calendar
        try:
            thunderbird_calendars = get_thunderbird_calendars()
            if thunderbird_calendars:
                print(f"DEBUG: Found {len(thunderbird_calendars)} Thunderbird calendars")
                all_calendars.extend(thunderbird_calendars)
            else:
                print(f"DEBUG: No Thunderbird calendars found")
        except Exception as e:
            logging.error(f"Error getting Thunderbird calendars: {str(e)}")
            print(f"DEBUG: Error getting Thunderbird calendars: {str(e)}")
        
        # Check for Google Calendar if authenticated
        if 'google_token' in session:
            try:
                google_calendars = get_google_calendars(session['google_token'])
                for cal in google_calendars:
                    cal['provider'] = 'google'
                    all_calendars.append(cal)
                print(f"DEBUG: Found {len(google_calendars)} Google calendars")
            except Exception as e:
                logging.error(f"Error getting Google calendars: {str(e)}")
                print(f"DEBUG: Error getting Google calendars: {str(e)}")
        
        # Check for Microsoft Calendar if authenticated
        if 'microsoft_token' in session:
            try:
                microsoft_calendars = get_microsoft_calendars(session['microsoft_token'])
                for cal in microsoft_calendars:
                    cal['provider'] = 'microsoft'
                    all_calendars.append(cal)
                print(f"DEBUG: Found {len(microsoft_calendars)} Microsoft calendars")
            except Exception as e:
                logging.error(f"Error getting Microsoft calendars: {str(e)}")
                print(f"DEBUG: Error getting Microsoft calendars: {str(e)}")
        
        selected_calendars = all_calendars
        print(f"DEBUG: Using all available calendars: {len(selected_calendars)} total")
    
    # Get events for each calendar based on provider
    for calendar in selected_calendars:
        if isinstance(calendar, str):
            # Convert string calendar ID to dict if needed
            if calendar.startswith('thunderbird:'):
                provider = 'thunderbird'
                cal_id = calendar
            elif calendar.startswith('google:'):
                provider = 'google'
                cal_id = calendar.replace('google:', '')
            elif calendar.startswith('microsoft:'):
                provider = 'microsoft'
                cal_id = calendar.replace('microsoft:', '')
            elif calendar.startswith('apple:'):
                provider = 'apple'
                cal_id = calendar.replace('apple:', '')
            else:
                # Assume Thunderbird if no prefix
                provider = 'thunderbird'
                cal_id = calendar
            
            calendar = {'id': cal_id, 'provider': provider}
        
        provider = calendar.get('provider')
        cal_id = calendar.get('id')
        
        print(f"DEBUG: Getting events for calendar: {cal_id} (Provider: {provider})")
        
        try:
            if provider == 'google' and 'google_token' in session:
                events = get_google_events(session['google_token'], cal_id, start_time, end_time)
                all_events.extend(events)
                print(f"DEBUG: Added {len(events)} Google events")
            
            elif provider == 'microsoft' and 'microsoft_token' in session:
                events = get_microsoft_events(session['microsoft_token'], cal_id, start_time, end_time)
                all_events.extend(events)
                print(f"DEBUG: Added {len(events)} Microsoft events")
            
            elif provider == 'apple' and platform.system() == 'Darwin':
                if not cal_id.startswith('apple:'):
                    cal_id = f"apple:{cal_id}"
                events = get_apple_events([cal_id], start_time, end_time)
                all_events.extend(events)
                print(f"DEBUG: Added {len(events)} Apple events")
            
            elif provider == 'thunderbird':
                if not cal_id.startswith('thunderbird:'):
                    cal_id = f"thunderbird:{cal_id}"
                print(f"DEBUG: Fetching Thunderbird events for {cal_id} from {start_time} to {end_time}")
                events = get_thunderbird_events([cal_id], start_time, end_time)
                all_events.extend(events)
                print(f"DEBUG: Added {len(events)} Thunderbird events from calendar {cal_id}")
            
            else:
                print(f"DEBUG: Skipping calendar with unknown/unsupported provider: {provider}")
        
        except Exception as e:
            error_msg = f"Error getting events for calendar {cal_id} (provider: {provider}): {str(e)}"
            logging.error(error_msg)
            print(f"DEBUG: {error_msg}")
            import traceback
            print(f"DEBUG: {traceback.format_exc()}")
    
    # Convert events to the format expected by FullCalendar
    formatted_events = []
    for event in all_events:
        try:
            # Get start and end times 
            start_time = event.get('start')
            end_time = event.get('end')
            
            # Check if they're already ISO strings (from Thunderbird events)
            if isinstance(start_time, str) and isinstance(end_time, str):
                # Ensure they have 'Z' for UTC timezone if needed
                if start_time.endswith('+00:00'):
                    start_time = start_time.replace('+00:00', 'Z')
                if end_time.endswith('+00:00'):
                    end_time = end_time.replace('+00:00', 'Z')
            # Convert datetime objects to ISO strings if needed
            elif isinstance(start_time, datetime):
                # Add timezone if missing
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                # Convert to ISO string with Z
                start_time = start_time.isoformat().replace('+00:00', 'Z')
                
                # Same for end time
                if end_time is not None:
                    if end_time.tzinfo is None:
                        end_time = end_time.replace(tzinfo=timezone.utc)
                    end_time = end_time.isoformat().replace('+00:00', 'Z')
            else:
                print(f"DEBUG: Invalid start/end time format for event {event.get('id')}")
                continue
            
            # Format the event
            formatted_event = {
                'id': event.get('id'),
                'title': event.get('title', 'Untitled Event'),
                'start': start_time,
                'end': end_time,
                'allDay': event.get('all_day', False),
            }
            
            # Add location if available
            if 'location' in event and event['location']:
                formatted_event['location'] = event['location']
            
            # Add color if available
            if 'color' in event and event['color']:
                formatted_event['color'] = event['color']
            else:
                # Set color based on calendar ID
                calendar_id = event.get('calendar_id')
                if calendar_id:
                    for cal in selected_calendars:
                        cal_id = cal.get('id') if isinstance(cal, dict) else cal
                        if cal_id == calendar_id:
                            formatted_event['color'] = cal.get('color', '#3366CC') if isinstance(cal, dict) else '#3366CC'
                            break
            
            # Add provider to event
            formatted_event['provider'] = event.get('provider', 'unknown')
            
            # Add calendar_id to event
            formatted_event['calendar_id'] = event.get('calendar_id', '')
            
            formatted_events.append(formatted_event)
        except Exception as e:
            print(f"DEBUG: Error formatting event: {str(e)}")
            print(f"DEBUG: Problem event: {event}")
    
    print(f"DEBUG: Returning {len(formatted_events)} events in total")
    
    # Sample the first few events for debugging
    if formatted_events:
        for i, event in enumerate(formatted_events[:3]):
            print(f"DEBUG: Sample event {i+1}: {event['title']} - {event['start']} to {event['end']}")
    
    return jsonify(formatted_events)

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

@bp.route('/debug')
def debug_calendars():
    """Debug endpoint to check calendar status and events"""
    # Security check - only allow in development mode
    if os.environ.get('FLASK_ENV') != 'development' and os.environ.get('DEBUG') != 'True':
        return jsonify({'error': 'Debug endpoints only available in development mode'}), 403
        
    now = datetime.now()
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (week_start + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Get session data
    selected_calendars = session.get('selected_calendars', [])
    
    # Available calendar sources
    sources = {}
    calendar_providers = []
    
    # Check for Apple Calendar if on macOS
    if platform.system() == 'Darwin':
        try:
            apple_calendars = get_apple_calendars()
            sources['apple'] = {
                'available': len(apple_calendars) > 0,
                'count': len(apple_calendars),
                'calendars': apple_calendars
            }
            calendar_providers.append('apple')
        except Exception as e:
            sources['apple'] = {
                'available': False,
                'error': str(e)
            }
    
    # Check for Thunderbird Calendar
    try:
        from app.services.thunderbird_calendar import find_all_calendar_databases
        thunderbird_dbs = find_all_calendar_databases()
        
        if thunderbird_dbs:
            thunderbird_calendars = get_thunderbird_calendars()
            sources['thunderbird'] = {
                'available': len(thunderbird_calendars) > 0,
                'count': len(thunderbird_calendars),
                'calendars': thunderbird_calendars,
                'databases': thunderbird_dbs
            }
            calendar_providers.append('thunderbird')
            
            # Get sample events for debugging
            if thunderbird_calendars:
                try:
                    sample_events = get_thunderbird_events(thunderbird_calendars, week_start, week_end)
                    sources['thunderbird']['events_count'] = len(sample_events)
                    sources['thunderbird']['sample_events'] = sample_events[:5] if sample_events else []
                except Exception as e:
                    sources['thunderbird']['events_error'] = str(e)
        else:
            sources['thunderbird'] = {
                'available': False,
                'error': 'No databases found'
            }
    except Exception as e:
        sources['thunderbird'] = {
            'available': False,
            'error': str(e)
        }
    
    # Check for Google Calendar if authenticated
    if 'google_token' in session:
        try:
            google_calendars = get_google_calendars(session['google_token'])
            sources['google'] = {
                'available': len(google_calendars) > 0,
                'count': len(google_calendars),
                'calendars': google_calendars
            }
            calendar_providers.append('google')
            
            # Get sample events for debugging
            if google_calendars:
                try:
                    sample_events = get_google_events(google_calendars, week_start, week_end)
                    sources['google']['events_count'] = len(sample_events)
                    sources['google']['sample_events'] = sample_events[:5] if sample_events else []
                except Exception as e:
                    sources['google']['events_error'] = str(e)
        except Exception as e:
            sources['google'] = {
                'available': False,
                'error': str(e)
            }
    
    # Check for Microsoft Calendar if authenticated
    if 'microsoft_token' in session:
        try:
            microsoft_calendars = get_microsoft_calendars(session['microsoft_token'])
            sources['microsoft'] = {
                'available': len(microsoft_calendars) > 0,
                'count': len(microsoft_calendars),
                'calendars': microsoft_calendars
            }
            calendar_providers.append('microsoft')
            
            # Get sample events for debugging
            if microsoft_calendars:
                try:
                    sample_events = get_microsoft_events(microsoft_calendars, week_start, week_end)
                    sources['microsoft']['events_count'] = len(sample_events)
                    sources['microsoft']['sample_events'] = sample_events[:5] if sample_events else []
                except Exception as e:
                    sources['microsoft']['events_error'] = str(e)
        except Exception as e:
            sources['microsoft'] = {
                'available': False,
                'error': str(e)
            }
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'week_range': {
            'start': week_start.isoformat(),
            'end': week_end.isoformat()
        },
        'session': {
            'selected_calendars': selected_calendars
        },
        'platform': platform.system(),
        'providers': calendar_providers,
        'sources': sources
    })

def get_thunderbird_events(calendars, start_date, end_date):
    """Get events from Thunderbird calendars for a specific date range"""
    events = []
    
    # Log parameters
    print(f"DEBUG: Fetching Thunderbird events. Start: {start_date}, End: {end_date}")
    print(f"DEBUG: Calendars requested: {calendars}")
    
    # Find all calendar databases
    calendar_databases = find_all_calendar_databases()
    
    if not calendar_databases:
        print("DEBUG: No Thunderbird calendar databases found.")
        return events
    
    # For each database, fetch events
    for db_path in calendar_databases:
        print(f"DEBUG: Checking database: {db_path}")
        db_events = []
        
        try:
            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Extract calendar IDs from the requested calendars
            calendar_ids = []
            for calendar in calendars:
                # Extract calendar ID from the combined string
                if isinstance(calendar, dict) and 'id' in calendar:
                    cal_id = calendar['id'].replace('thunderbird:', '') if calendar['id'].startswith('thunderbird:') else calendar['id']
                else:
                    cal_id = calendar.replace('thunderbird:', '') if calendar.startswith('thunderbird:') else calendar
                calendar_ids.append(cal_id)
            
            print(f"DEBUG: Looking for events from calendar IDs: {calendar_ids}")
            
            # Convert dates to Unix timestamp for SQLite query (microseconds)
            # Ensure the timestamps are in UTC for consistency
            if start_date.tzinfo is not None:
                start_timestamp = int(start_date.astimezone(timezone.utc).timestamp() * 1000000)
            else:
                start_timestamp = int(start_date.replace(tzinfo=timezone.utc).timestamp() * 1000000)
                
            if end_date.tzinfo is not None:
                end_timestamp = int(end_date.astimezone(timezone.utc).timestamp() * 1000000)
            else:
                end_timestamp = int(end_date.replace(tzinfo=timezone.utc).timestamp() * 1000000)
            
            # Get available tables in the database
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"DEBUG: Available tables: {tables}")
            
            # Check if events table exists
            if 'cal_events' not in tables:
                print(f"DEBUG: No cal_events table found in {db_path}")
                conn.close()
                continue
            
            # Get the columns in the events table
            cursor.execute("PRAGMA table_info(cal_events)")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"DEBUG: cal_events columns: {columns}")
            
            # Determine which time columns to use based on the database schema
            start_time_col = 'event_start'
            end_time_col = 'event_end'
            
            if 'start_time' in columns and 'end_time' in columns:
                start_time_col = 'start_time'
                end_time_col = 'end_time'
            
            print(f"DEBUG: Using time columns: {start_time_col} and {end_time_col}")
            
            # Format calendar IDs for SQL query
            cal_id_placeholders = ','.join(['?'] * len(calendar_ids)) if calendar_ids else '1'
            query_params = calendar_ids.copy() if calendar_ids else []
            
            # If no specific calendar IDs are provided, get all events
            if not calendar_ids:
                query = f"""
                SELECT cal_id, title, {start_time_col}, {end_time_col}, id
                FROM cal_events
                WHERE (({start_time_col} >= ? AND {start_time_col} <= ?) OR 
                       ({end_time_col} >= ? AND {end_time_col} <= ?) OR
                       ({start_time_col} <= ? AND {end_time_col} >= ?))
                ORDER BY {start_time_col} ASC
                """
                query_params = [start_timestamp, end_timestamp, start_timestamp, end_timestamp, start_timestamp, end_timestamp]
            else:
                query = f"""
                SELECT cal_id, title, {start_time_col}, {end_time_col}, id
                FROM cal_events
                WHERE cal_id IN ({cal_id_placeholders})
                AND (({start_time_col} >= ? AND {start_time_col} <= ?) OR 
                     ({end_time_col} >= ? AND {end_time_col} <= ?) OR
                     ({start_time_col} <= ? AND {end_time_col} >= ?))
                ORDER BY {start_time_col} ASC
                """
                query_params.extend([start_timestamp, end_timestamp, start_timestamp, end_timestamp, start_timestamp, end_timestamp])
            
            print(f"DEBUG: Running query: {query}")
            print(f"DEBUG: Query parameters: {query_params}")
            
            # Execute the query
            cursor.execute(query, query_params)
            results = cursor.fetchall()
            print(f"DEBUG: Found {len(results)} events in database {db_path}")
            
            # Process each event
            for event in results:
                cal_id, title, event_start, event_end, event_id = event
                
                try:
                    # Convert timestamps to datetime objects with UTC timezone
                    start_dt = datetime.fromtimestamp(event_start / 1000000, timezone.utc)
                    end_dt = datetime.fromtimestamp(event_end / 1000000, timezone.utc)
                    
                    # Format as ISO 8601 strings with 'Z' to indicate UTC
                    start_iso = start_dt.isoformat().replace('+00:00', 'Z')
                    end_iso = end_dt.isoformat().replace('+00:00', 'Z')
                    
                    print(f"DEBUG: Converted event times - Start: {start_iso}, End: {end_iso}")
                    
                    # Try to get event location if available
                    location = None
                    if 'cal_properties' in tables:
                        try:
                            # Look up the location property for this event
                            cursor.execute("""
                                SELECT value FROM cal_properties 
                                WHERE item_id = ? AND key = 'LOCATION'
                            """, [event_id])
                            loc_row = cursor.fetchone()
                            if loc_row:
                                location = loc_row[0]
                        except Exception as e:
                            print(f"DEBUG: Error getting event location: {e}")
                    
                    # Add event to results
                    event_data = {
                        'id': f"thunderbird:{event_id}",
                        'calendar_id': f"thunderbird:{cal_id}",
                        'title': title,
                        'start': start_iso,
                        'end': end_iso,
                        'provider': 'thunderbird'
                    }
                    
                    # Add location if available
                    if location:
                        event_data['location'] = location
                    
                    db_events.append(event_data)
                except Exception as e:
                    print(f"DEBUG: Error processing event {event_id}: {e}")
            
            # Add a sample of events for debugging
            if db_events:
                print(f"DEBUG: Sample event data (first up to 3 events):")
                for i, event in enumerate(db_events[:3]):
                    print(f"DEBUG: Event {i+1}: Calendar: {event['calendar_id']}, Title: {event['title']}, Start: {event['start']}, End: {event['end']}")
            
            # Add events from this database to the overall result
            events.extend(db_events)
            
            # Close database connection
            conn.close()
            
        except Exception as e:
            print(f"DEBUG: Error fetching events from Thunderbird database: {e}")
            import traceback
            print(f"DEBUG: {traceback.format_exc()}")
    
    print(f"DEBUG: Total Thunderbird events found: {len(events)}")
    return events 