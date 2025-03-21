import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import glob
import logging
import pytz
import platform

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

def find_all_calendar_databases():
    """Find all Thunderbird calendar SQLite databases"""
    possible_paths = []
    
    # Print debugging information
    print(f"DEBUG: Searching for Thunderbird calendar databases")
    print(f"DEBUG: Current platform: {platform.system()}")
    
    # Platform-specific search paths
    if platform.system() == 'Darwin':  # macOS
        possible_paths.extend(glob.glob(os.path.expanduser("~/Library/Thunderbird/Profiles/*/calendar-data/local.sqlite")))
        possible_paths.extend(glob.glob(os.path.expanduser("~/Library/Thunderbird/Profiles/*/storage/default/moz-extension*/*-storage/calendar-data/local.sqlite")))
    elif platform.system() == 'Linux':
        possible_paths.extend(glob.glob(os.path.expanduser("~/.thunderbird/*/calendar-data/local.sqlite")))
        possible_paths.extend(glob.glob(os.path.expanduser("~/.icedove/*/calendar-data/local.sqlite")))
        possible_paths.extend(glob.glob(os.path.expanduser("~/.mozilla-thunderbird/*/calendar-data/local.sqlite")))
        possible_paths.extend(glob.glob(os.path.expanduser("~/.local/share/thunderbird/*/calendar-data/local.sqlite")))
    elif platform.system() == 'Windows':
        appdata = os.getenv('APPDATA', '')
        localappdata = os.getenv('LOCALAPPDATA', '')
        possible_paths.extend(glob.glob(os.path.join(appdata, "Thunderbird/Profiles/*/calendar-data/local.sqlite")))
        possible_paths.extend(glob.glob(os.path.join(localappdata, "Thunderbird/Profiles/*/calendar-data/local.sqlite")))
    
    # Debug found paths
    print(f"DEBUG: Found {len(possible_paths)} potential calendar databases: {possible_paths}")
    
    valid_paths = []
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                # Test if we can connect to the database
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                
                # Check if the database has the cal_calendars table
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cal_calendars'")
                if cursor.fetchone():
                    valid_paths.append(path)
                    print(f"DEBUG: Valid calendar database found at: {path}")
                
                conn.close()
            except sqlite3.Error as e:
                print(f"DEBUG: Error checking database {path}: {e}")
    
    return valid_paths

def get_thunderbird_calendars():
    """
    Get all Thunderbird calendars
    
    Returns:
        List of dictionaries with calendar information
    """
    calendars = []
    
    # Find all calendar databases
    calendar_databases = find_all_calendar_databases()
    
    if not calendar_databases:
        print("DEBUG: No valid Thunderbird calendar databases found")
        return []
    
    # For each database, fetch calendars
    for db_path in calendar_databases:
        print(f"DEBUG: Getting calendars from database: {db_path}")
        
        try:
            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Query for calendars
            cursor.execute("SELECT id, name, color FROM cal_calendars WHERE cal_type = 0")
            result = cursor.fetchall()
            
            # Debug found calendars
            print(f"DEBUG: Found {len(result)} calendars in database {db_path}")
            
            for calendar in result:
                cal_id, name, color = calendar
                
                # Add calendar to results with prefix to identify source
                calendars.append({
                    'id': f"thunderbird:{cal_id}",
                    'name': name,
                    'color': color,
                    'provider': 'thunderbird'
                })
                print(f"DEBUG: Found calendar with ID: thunderbird:{cal_id}, Name: {name}")
            
            conn.close()
            
        except Exception as e:
            print(f"DEBUG: Error getting calendars from Thunderbird database: {e}")
    
    print(f"DEBUG: Total Thunderbird calendars found: {len(calendars)}")
    return calendars

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
    
    # Debug: Inspect database structure
    for db_path in calendar_databases:
        debug_thunderbird_database(db_path)
    
    # For each database, fetch events
    for db_path in calendar_databases:
        print(f"DEBUG: Checking database: {db_path}")
        
        try:
            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Use calendar IDs to filter events
            calendar_ids = []
            for calendar in calendars:
                # Extract calendar ID from the combined string
                cal_id = calendar['id'].replace('thunderbird:', '') if calendar['id'].startswith('thunderbird:') else calendar['id']
                calendar_ids.append(cal_id)
            
            # Convert dates to Unix timestamp for SQLite query
            start_timestamp = int(start_date.timestamp() * 1000000)  # microseconds
            end_timestamp = int(end_date.timestamp() * 1000000)    # microseconds
            
            # Format calendar IDs for SQL query
            cal_id_placeholders = ','.join(['?'] * len(calendar_ids))
            
            # Debug the query parameters
            print(f"DEBUG: Start timestamp: {start_timestamp}, End timestamp: {end_timestamp}")
            print(f"DEBUG: Calendar IDs for filtering: {calendar_ids}")
            
            # Query events that fall within the date range
            query = f"""
            SELECT cal_id, title, event_start, event_end, id
            FROM cal_events
            WHERE cal_id IN ({cal_id_placeholders})
            AND ((event_start >= ? AND event_start <= ?) OR 
                 (event_end >= ? AND event_end <= ?) OR
                 (event_start <= ? AND event_end >= ?))
            """
            
            # Execute query with parameters
            cursor.execute(query, calendar_ids + [start_timestamp, end_timestamp, start_timestamp, end_timestamp, start_timestamp, end_timestamp])
            
            # Get results
            results = cursor.fetchall()
            print(f"DEBUG: Found {len(results)} events in database {db_path}")
            
            # Debug the first few results
            if results:
                print(f"DEBUG: Sample event data (first up to 3 events):")
                for i, event in enumerate(results[:3]):
                    cal_id, title, event_start, event_end, event_id = event
                    start_dt = datetime.fromtimestamp(event_start / 1000000)
                    end_dt = datetime.fromtimestamp(event_end / 1000000)
                    print(f"DEBUG: Event {i+1}: Calendar: {cal_id}, Title: {title}, Start: {start_dt}, End: {end_dt}")
            
            # Process each event
            for event in results:
                cal_id, title, event_start, event_end, event_id = event
                
                # Convert timestamps to datetime
                start_dt = datetime.fromtimestamp(event_start / 1000000)
                end_dt = datetime.fromtimestamp(event_end / 1000000)
                
                # Add event to results
                events.append({
                    'id': f"thunderbird:{event_id}",
                    'calendar_id': f"thunderbird:{cal_id}",
                    'title': title,
                    'start': start_dt,
                    'end': end_dt,
                    'provider': 'thunderbird'
                })
            
            # Close database connection
            conn.close()
            
        except Exception as e:
            print(f"DEBUG: Error fetching events from Thunderbird database: {e}")
            import traceback
            print(f"DEBUG: {traceback.format_exc()}")
    
    print(f"DEBUG: Total Thunderbird events found: {len(events)}")
    return events

def debug_thunderbird_database(db_path):
    """Debug function to inspect tables and data in a Thunderbird calendar database"""
    print(f"DEBUG: Inspecting Thunderbird database at {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"DEBUG: Tables in database: {[t[0] for t in tables]}")
        
        # Check cal_calendars table
        if ('cal_calendars',) in tables:
            print(f"DEBUG: Examining cal_calendars table...")
            cursor.execute("PRAGMA table_info(cal_calendars)")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"DEBUG: cal_calendars columns: {columns}")
            
            # Count records
            cursor.execute("SELECT COUNT(*) FROM cal_calendars")
            count = cursor.fetchone()[0]
            print(f"DEBUG: cal_calendars has {count} records")
            
            # Sample records
            if count > 0:
                cursor.execute("SELECT * FROM cal_calendars LIMIT 3")
                records = cursor.fetchall()
                for i, record in enumerate(records):
                    print(f"DEBUG: cal_calendars record {i+1}: {record}")
        
        # Check cal_events table
        if ('cal_events',) in tables:
            print(f"DEBUG: Examining cal_events table...")
            cursor.execute("PRAGMA table_info(cal_events)")
            columns = [col[1] for col in cursor.fetchall()]
            print(f"DEBUG: cal_events columns: {columns}")
            
            # Count records
            cursor.execute("SELECT COUNT(*) FROM cal_events")
            count = cursor.fetchone()[0]
            print(f"DEBUG: cal_events has {count} records")
            
            # Sample records
            if count > 0:
                cursor.execute("SELECT id, cal_id, title, event_start, event_end FROM cal_events LIMIT 3")
                records = cursor.fetchall()
                for i, record in enumerate(records):
                    event_id, cal_id, title, event_start, event_end = record
                    try:
                        start_dt = datetime.fromtimestamp(event_start / 1000000)
                        end_dt = datetime.fromtimestamp(event_end / 1000000)
                        print(f"DEBUG: cal_events record {i+1}: ID={event_id}, Calendar={cal_id}, Title={title}, Start={start_dt}, End={end_dt}")
                    except Exception as e:
                        print(f"DEBUG: Error parsing event times - Raw record: {record}, Error: {e}")
                
                # Check for events in the current week
                now = datetime.now()
                week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                week_end = (week_start + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=999999)
                
                start_timestamp = int(week_start.timestamp() * 1000000)
                end_timestamp = int(week_end.timestamp() * 1000000)
                
                print(f"DEBUG: Checking for events in current week: {week_start} to {week_end}")
                print(f"DEBUG: Timestamps: {start_timestamp} to {end_timestamp}")
                
                query = """
                SELECT cal_id, title, event_start, event_end, id
                FROM cal_events
                WHERE ((event_start >= ? AND event_start <= ?) OR 
                        (event_end >= ? AND event_end <= ?) OR
                        (event_start <= ? AND event_end >= ?))
                LIMIT 10
                """
                
                cursor.execute(query, [start_timestamp, end_timestamp, start_timestamp, end_timestamp, start_timestamp, end_timestamp])
                weekly_events = cursor.fetchall()
                
                print(f"DEBUG: Found {len(weekly_events)} events in current week")
                for i, event in enumerate(weekly_events):
                    cal_id, title, event_start, event_end, event_id = event
                    try:
                        start_dt = datetime.fromtimestamp(event_start / 1000000)
                        end_dt = datetime.fromtimestamp(event_end / 1000000)
                        print(f"DEBUG: Weekly event {i+1}: Calendar={cal_id}, Title={title}, Start={start_dt}, End={end_dt}")
                    except Exception as e:
                        print(f"DEBUG: Error parsing event times - Raw record: {event}, Error: {e}")
        
        conn.close()
    except Exception as e:
        print(f"DEBUG: Error inspecting Thunderbird database: {e}")
        import traceback
        print(f"DEBUG: {traceback.format_exc()}") 