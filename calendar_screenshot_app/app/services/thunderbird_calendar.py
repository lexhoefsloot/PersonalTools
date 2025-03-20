import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import glob
import logging
import pytz

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def microseconds_to_datetime(microseconds, tz_name=None):
    """Convert microseconds since epoch to datetime object"""
    if not microseconds:
        return None
    
    # Convert to seconds and create UTC datetime
    seconds = microseconds / 1000000
    dt = datetime.fromtimestamp(seconds, timezone.utc)
    
    # Convert to specified timezone if provided
    if tz_name:
        try:
            tz = pytz.timezone(tz_name)
            dt = dt.astimezone(tz)
        except pytz.exceptions.UnknownTimeZoneError:
            pass
    
    return dt

def find_thunderbird_profiles():
    """Find all possible Thunderbird profile directories"""
    # Common profile locations on different systems
    profile_paths = [
        os.path.expanduser("~/.thunderbird/*/"),
        os.path.expanduser("~/.icedove/*/"),  # Debian's fork of Thunderbird
        os.path.expanduser("~/.mozilla-thunderbird/*/"),  # Older versions
        os.path.expanduser("~/.local/share/thunderbird/*/"),
        os.path.expanduser("~/Library/Thunderbird/Profiles/*/")  # macOS
    ]
    
    profiles = []
    for path_pattern in profile_paths:
        profiles.extend(glob.glob(path_pattern))
    
    return profiles

def find_calendar_database():
    """Find the Thunderbird calendar database"""
    profiles = find_thunderbird_profiles()
    
    for profile in profiles:
        # Check common locations for calendar database
        for db_name in ['cache.sqlite', 'local.sqlite']:
            calendar_db = os.path.join(profile, "calendar-data", db_name)
            if os.path.exists(calendar_db):
                return calendar_db
    
    return None

def get_thunderbird_calendars():
    """
    Get a list of calendars from Thunderbird
    Returns a list of calendar dictionaries with id, name, and description
    """
    calendar_db = find_calendar_database()
    if not calendar_db:
        logger.warning("Thunderbird calendar database not found")
        return []
    
    logger.info(f"Using Thunderbird calendar database: {calendar_db}")
    
    try:
        conn = sqlite3.connect(calendar_db)
        cursor = conn.cursor()
        
        # Check if the cal_calendars table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cal_calendars';")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            logger.warning("cal_calendars table not found in the database")
            # Try alternative method: look for unique cal_id values in cal_events
            cursor.execute("SELECT DISTINCT cal_id FROM cal_events;")
            cal_ids = cursor.fetchall()
            
            calendars = []
            for cal_id in cal_ids:
                calendars.append({
                    'id': f"thunderbird:{cal_id[0]}",
                    'name': f"Calendar {cal_id[0]}",
                    'description': f"Thunderbird Calendar {cal_id[0]}",
                    'provider': 'thunderbird'
                })
            
            conn.close()
            return calendars
        
        # Query calendars from cal_calendars table
        cursor.execute("SELECT cal_id, name, type FROM cal_calendars;")
        cal_rows = cursor.fetchall()
        
        calendars = []
        for row in cal_rows:
            cal_id, name, cal_type = row
            calendars.append({
                'id': f"thunderbird:{cal_id}",
                'name': name or f"Calendar {cal_id}",
                'description': f"Thunderbird Calendar ({cal_type})",
                'provider': 'thunderbird'
            })
        
        conn.close()
        return calendars
    
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []

def get_thunderbird_events(calendars, start_time, end_time, timezone=None):
    """
    Get events from Thunderbird calendars within the specified time range
    
    Args:
        calendars: List of calendar dictionaries 
        start_time: Start time as datetime object
        end_time: End time as datetime object
        timezone: Timezone string, e.g., 'Europe/Berlin'
    
    Returns:
        List of event dictionaries with start, end, and title keys
    """
    # Make sure we only process Thunderbird calendars
    thunderbird_cals = [cal for cal in calendars if cal.get('provider') == 'thunderbird']
    if not thunderbird_cals:
        return []
    
    # Get cal_ids from the calendar list
    cal_ids = [cal['id'].split(':')[1] for cal in thunderbird_cals]
    
    calendar_db = find_calendar_database()
    if not calendar_db:
        logger.warning("Thunderbird calendar database not found")
        return []
    
    # Convert start_time and end_time to microseconds since epoch
    start_microsec = int(start_time.timestamp() * 1000000)
    end_microsec = int(end_time.timestamp() * 1000000)
    
    try:
        conn = sqlite3.connect(calendar_db)
        cursor = conn.cursor()
        
        # Prepare query parameters
        query_params = (start_microsec, end_microsec)
        cal_id_placeholders = ','.join(['?' for _ in cal_ids])
        
        # Query events from cal_events table
        query = f"""
        SELECT cal_id, id, title, event_start, event_end, event_start_tz, event_end_tz, flags
        FROM cal_events
        WHERE (event_start BETWEEN ? AND ? OR event_end BETWEEN ? AND ? OR (event_start <= ? AND event_end >= ?))
        AND cal_id IN ({cal_id_placeholders})
        ORDER BY event_start;
        """
        
        cursor.execute(query, (start_microsec, end_microsec, start_microsec, end_microsec, start_microsec, end_microsec) + tuple(cal_ids))
        event_rows = cursor.fetchall()
        
        events = []
        for row in event_rows:
            cal_id, event_id, title, start, end, start_tz, end_tz, flags = row
            
            # Skip cancelled events if the flag is set
            if flags & 1:  # Cancelled flag
                continue
            
            # Convert timestamps to datetime objects
            start_dt = microseconds_to_datetime(start, start_tz)
            end_dt = microseconds_to_datetime(end, end_tz)
            
            # Create event dictionary
            event = {
                'id': event_id,
                'title': title,
                'start': start_dt,
                'end': end_dt,
                'calendar_id': cal_id,
                'provider': 'thunderbird'
            }
            
            events.append(event)
        
        conn.close()
        return events
    
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return [] 