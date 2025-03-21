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
        # Check common locations for calendar database, prioritizing cache.sqlite
        for db_name in ['cache.sqlite', 'local.sqlite']:
            calendar_db = os.path.join(profile, "calendar-data", db_name)
            if os.path.exists(calendar_db):
                print(f"DEBUG: Found calendar database at {calendar_db}")
                return calendar_db
    
    print("DEBUG: No calendar database found in any profile")
    return None

def find_all_calendar_databases():
    """Find all Thunderbird calendar SQLite databases"""
    possible_paths = []
    
    # Print debugging information
    print(f"DEBUG: Searching for Thunderbird calendar databases")
    print(f"DEBUG: Current platform: {platform.system()}")
    
    # Define database filenames to search for (prioritize cache.sqlite)
    db_files = ['cache.sqlite', 'local.sqlite']
    
    # Platform-specific search paths
    if platform.system() == 'Darwin':  # macOS
        # Search for database files in standard macOS locations
        for db_file in db_files:
            possible_paths.extend(glob.glob(os.path.expanduser(f"~/Library/Thunderbird/Profiles/*/calendar-data/{db_file}")))
            possible_paths.extend(glob.glob(os.path.expanduser(f"~/Library/Thunderbird/Profiles/*/storage/default/moz-extension*/*-storage/calendar-data/{db_file}")))
    elif platform.system() == 'Linux':
        # Search for database files in standard Linux locations
        for db_file in db_files:
            possible_paths.extend(glob.glob(os.path.expanduser(f"~/.thunderbird/*/calendar-data/{db_file}")))
            possible_paths.extend(glob.glob(os.path.expanduser(f"~/.icedove/*/calendar-data/{db_file}")))  # Debian's fork of Thunderbird
            possible_paths.extend(glob.glob(os.path.expanduser(f"~/.mozilla-thunderbird/*/calendar-data/{db_file}")))  # Older versions
            possible_paths.extend(glob.glob(os.path.expanduser(f"~/.local/share/thunderbird/*/calendar-data/{db_file}")))
    elif platform.system() == 'Windows':
        appdata = os.getenv('APPDATA', '')
        localappdata = os.getenv('LOCALAPPDATA', '')
        # Search for database files in standard Windows locations
        for db_file in db_files:
            possible_paths.extend(glob.glob(os.path.join(appdata, f"Thunderbird/Profiles/*/calendar-data/{db_file}")))
            possible_paths.extend(glob.glob(os.path.join(localappdata, f"Thunderbird/Profiles/*/calendar-data/{db_file}")))
    
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
                else:
                    print(f"DEBUG: Database {path} exists but doesn't have cal_calendars table")
                    
                    # Try to list the available tables for debugging
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    tables = cursor.fetchall()
                    print(f"DEBUG: Tables in {path}: {[t[0] for t in tables]}")
                
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
            
            # Determine if this is cache.sqlite or local.sqlite format
            is_cache_db = 'cache' in os.path.basename(db_path).lower()
            print(f"DEBUG: Database type: {'cache.sqlite' if is_cache_db else 'local.sqlite'}")
            
            # Check if the database has the cal_calendars table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cal_calendars'")
            has_calendars_table = cursor.fetchone() is not None
            
            if has_calendars_table:
                print(f"DEBUG: Found cal_calendars table, getting data")
                
                # Get the columns in the table to adapt our query
                cursor.execute("PRAGMA table_info(cal_calendars)")
                columns = [col[1] for col in cursor.fetchall()]
                print(f"DEBUG: cal_calendars columns: {columns}")
                
                # Some database versions store active calendars with cal_type = 0
                if 'cal_type' in columns:
                    query = "SELECT id, name, color FROM cal_calendars WHERE cal_type = 0"
                else:
                    query = "SELECT id, name, color FROM cal_calendars"
                
                cursor.execute(query)
                result = cursor.fetchall()
            else:
                print(f"DEBUG: No cal_calendars table found, trying to extract calendars from events")
                
                # Try to extract calendar IDs from events table
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cal_events'")
                if cursor.fetchone():
                    cursor.execute("SELECT DISTINCT cal_id FROM cal_events")
                    result = [(cal_id[0], f"Calendar {cal_id[0]}", "#3366CC") for cal_id in cursor.fetchall()]
                    print(f"DEBUG: Extracted {len(result)} calendars from events")
                else:
                    result = []
                    print(f"DEBUG: No cal_events table found, cannot extract calendars")
            
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
            import traceback
            print(f"DEBUG: {traceback.format_exc()}")
    
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
            
            # Check if the database has the necessary tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cal_events'")
            has_events_table = cursor.fetchone() is not None
            
            if not has_events_table:
                print(f"DEBUG: Database {db_path} doesn't have a cal_events table")
                conn.close()
                continue
            
            # Check if this is cache.sqlite or local.sqlite format
            is_cache_db = 'cache' in os.path.basename(db_path).lower()
            
            # For different database formats, we might need different queries
            if is_cache_db:
                # For cache.sqlite format
                print(f"DEBUG: Using cache.sqlite format query")
                
                # Check for columns
                cursor.execute("PRAGMA table_info(cal_events)")
                columns = [col[1] for col in cursor.fetchall()]
                print(f"DEBUG: Available columns: {columns}")
                
                # Adapt query based on available columns
                if 'start_time' in columns and 'end_time' in columns:
                    # Some versions use start_time/end_time instead of event_start/event_end
                    query = f"""
                    SELECT cal_id, title, start_time, end_time, id
                    FROM cal_events
                    WHERE cal_id IN ({cal_id_placeholders})
                    AND ((start_time >= ? AND start_time <= ?) OR 
                         (end_time >= ? AND end_time <= ?) OR
                         (start_time <= ? AND end_time >= ?))
                    """
                    cursor.execute(query, calendar_ids + [start_timestamp, end_timestamp, start_timestamp, end_timestamp, start_timestamp, end_timestamp])
                else:
                    # Use standard column names
                    query = f"""
                    SELECT cal_id, title, event_start, event_end, id
                    FROM cal_events
                    WHERE cal_id IN ({cal_id_placeholders})
                    AND ((event_start >= ? AND event_start <= ?) OR 
                         (event_end >= ? AND event_end <= ?) OR
                         (event_start <= ? AND event_end >= ?))
                    """
                    cursor.execute(query, calendar_ids + [start_timestamp, end_timestamp, start_timestamp, end_timestamp, start_timestamp, end_timestamp])
            else:
                # For local.sqlite format (older)
                print(f"DEBUG: Using local.sqlite format query")
                query = f"""
                SELECT cal_id, title, event_start, event_end, id
                FROM cal_events
                WHERE cal_id IN ({cal_id_placeholders})
                AND ((event_start >= ? AND event_start <= ?) OR 
                     (event_end >= ? AND event_end <= ?) OR
                     (event_start <= ? AND event_end >= ?))
                """
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
        
        # Determine if this is a newer format (cache.sqlite) or older format (local.sqlite)
        is_cache_db = 'cache' in os.path.basename(db_path).lower()
        print(f"DEBUG: Database type: {'cache.sqlite (newer format)' if is_cache_db else 'local.sqlite (older format)'}")
        
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
            
            # Check if records exist with sample cal_id values
            if count > 0:
                # Get distinct calendar IDs
                cursor.execute("SELECT DISTINCT cal_id FROM cal_events")
                cal_ids = cursor.fetchall()
                print(f"DEBUG: Found {len(cal_ids)} distinct calendar IDs in events: {[c[0] for c in cal_ids]}")
                
                # Check for distinct event fields
                cursor.execute("SELECT COUNT(DISTINCT title) FROM cal_events")
                distinct_titles = cursor.fetchone()[0]
                print(f"DEBUG: Found {distinct_titles} distinct event titles")
                
                # Sample records
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
                
                # Broad query first to see if there are any events in the general timeframe
                cursor.execute("SELECT COUNT(*) FROM cal_events WHERE event_start > ? AND event_start < ?", 
                              [start_timestamp - 86400000000, end_timestamp + 86400000000])  # +/- 1 day in microseconds
                count_timeframe = cursor.fetchone()[0]
                print(f"DEBUG: Found {count_timeframe} events in the general week timeframe (including buffer)")
                
                # Check without overlap conditions first
                cursor.execute("""
                SELECT COUNT(*) FROM cal_events 
                WHERE event_start >= ? AND event_start <= ?
                """, [start_timestamp, end_timestamp])
                count_simple = cursor.fetchone()[0]
                print(f"DEBUG: Found {count_simple} events with start times in the exact week range")
                
                # Now use the more complex overlap condition
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
                
                print(f"DEBUG: Found {len(weekly_events)} events in current week with overlap condition")
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