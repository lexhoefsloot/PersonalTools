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
    
    # Check the specific path mentioned by user first
    specific_path = os.path.expanduser("~/.thunderbird/qw0vnk3t.default-default/calendar-data/cache.sqlite")
    if os.path.exists(specific_path):
        print(f"DEBUG: Found specified Thunderbird calendar database at {specific_path}")
        file_size = os.path.getsize(specific_path)
        print(f"DEBUG: Database size: {file_size / (1024*1024):.2f} MB")
        if file_size > 0:
            try:
                # Validate database
                conn = sqlite3.connect(specific_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [t[0] for t in cursor.fetchall()]
                
                # Check if it has calendar tables
                if 'cal_calendars' in tables or 'cal_events' in tables:
                    print(f"DEBUG: Valid calendar database found at specified path: {specific_path}")
                    conn.close()
                    return [specific_path]  # Return only this specific path
                conn.close()
            except sqlite3.Error as e:
                print(f"DEBUG: Error checking specified database: {e}")
    
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
    
    # Debug found paths with file sizes
    for path in possible_paths:
        file_size = os.path.getsize(path) if os.path.exists(path) else 0
        print(f"DEBUG: Found potential calendar database: {path} (Size: {file_size / (1024*1024):.2f} MB)")
    
    # Sort by size to prioritize the larger file (almost always the active one)
    possible_paths.sort(key=lambda path: os.path.getsize(path) if os.path.exists(path) else 0, reverse=True)
    print(f"DEBUG: Sorted databases by size (largest first): {[p for p in possible_paths]}")
    
    # Now validate them
    valid_paths = []
    for path in possible_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            try:
                # Test if we can connect to the database
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                
                # Get tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [t[0] for t in cursor.fetchall()]
                print(f"DEBUG: Tables in {path}: {tables}")
                
                # Check if the database has the necessary tables
                has_calendars = 'cal_calendars' in tables
                has_events = 'cal_events' in tables
                
                if has_calendars or has_events:
                    valid_paths.append(path)
                    print(f"DEBUG: Valid calendar database found at: {path}")
                    
                    # Print further details
                    print(f"DEBUG: Has cal_calendars table: {has_calendars}")
                    print(f"DEBUG: Has cal_events table: {has_events}")
                    
                    if has_events:
                        try:
                            # Count events
                            cursor.execute("SELECT COUNT(*) FROM cal_events")
                            event_count = cursor.fetchone()[0]
                            print(f"DEBUG: Database contains {event_count} events")
                            
                            # Check calendar IDs
                            cursor.execute("SELECT DISTINCT cal_id FROM cal_events")
                            cal_ids = [c[0] for c in cursor.fetchall()]
                            print(f"DEBUG: Found calendar IDs in events: {cal_ids}")
                        except sqlite3.Error as e:
                            print(f"DEBUG: Error querying events: {e}")
                else:
                    print(f"DEBUG: Database {path} doesn't have required calendar tables")
                
                conn.close()
            except sqlite3.Error as e:
                print(f"DEBUG: Error checking database {path}: {e}")
    
    # If we have both cache.sqlite and local.sqlite in the same folder, prioritize cache.sqlite
    prioritized_paths = []
    by_dir = group_by_directory(valid_paths)
    for directory, files in by_dir.items():
        if len(files) > 1:
            # Prioritize cache.sqlite over local.sqlite
            cache_files = [f for f in files if 'cache.sqlite' in f]
            if cache_files:
                largest_cache = max(cache_files, key=os.path.getsize)
                print(f"DEBUG: Multiple databases found in {directory}, prioritizing cache.sqlite: {largest_cache}")
                prioritized_paths.append(largest_cache)
            else:
                # If no cache.sqlite, use the largest file
                largest_file = max(files, key=os.path.getsize)
                print(f"DEBUG: Multiple databases found in {directory}, prioritizing largest: {largest_file}")
                prioritized_paths.append(largest_file)
        else:
            prioritized_paths.extend(files)
    
    return prioritized_paths

def group_by_directory(paths):
    """Group files by their directory"""
    by_dir = {}
    for path in paths:
        directory = os.path.dirname(path)
        if directory not in by_dir:
            by_dir[directory] = []
        by_dir[directory].append(path)
    return by_dir

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
            
            # Check available tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"DEBUG: Available tables: {tables}")
            
            # First look for calendar IDs in cal_metadata, which often has calendar information
            if 'cal_metadata' in tables:
                print(f"DEBUG: Checking cal_metadata table for calendar information")
                try:
                    # Find the actual calendar IDs first - they are often prefixed with 'calendar-'
                    cursor.execute("""
                        SELECT DISTINCT item_id FROM cal_metadata 
                        WHERE item_id LIKE 'calendar-%'
                    """)
                    cal_items = cursor.fetchall()
                    
                    if cal_items:
                        print(f"DEBUG: Found {len(cal_items)} potential calendars in cal_metadata")
                        
                        # For each calendar ID, get the name and other properties
                        for item in cal_items:
                            cal_id = item[0]
                            print(f"DEBUG: Processing calendar ID: {cal_id}")
                            
                            # Get calendar name
                            cursor.execute("""
                                SELECT value FROM cal_metadata 
                                WHERE item_id = ? AND key = 'name'
                            """, [cal_id])
                            name_row = cursor.fetchone()
                            cal_name = name_row[0] if name_row else cal_id.replace('calendar-', '')
                            
                            # Get calendar color
                            cursor.execute("""
                                SELECT value FROM cal_metadata 
                                WHERE item_id = ? AND key = 'color'
                            """, [cal_id])
                            color_row = cursor.fetchone()
                            cal_color = color_row[0] if color_row else "#3366CC"
                            
                            # Add calendar to list
                            cal_id_clean = cal_id.replace('calendar-', '')
                            calendar = {
                                'id': f"thunderbird:{cal_id_clean}",
                                'name': cal_name,
                                'color': cal_color,
                                'provider': 'thunderbird'
                            }
                            calendars.append(calendar)
                except Exception as e:
                    print(f"DEBUG: Error getting calendar info from cal_metadata: {e}")
            
            # If no calendars were found in cal_metadata, look in cal_calendars
            if not calendars and 'cal_calendars' in tables:
                print(f"DEBUG: Checking cal_calendars table for calendar information")
                try:
                    # Get all calendars
                    cursor.execute("SELECT id, name, color FROM cal_calendars")
                    results = cursor.fetchall()
                    
                    print(f"DEBUG: Found {len(results)} calendars in cal_calendars")
                    
                    for result in results:
                        cal_id, cal_name, cal_color = result
                        calendar = {
                            'id': f"thunderbird:{cal_id}",
                            'name': cal_name or f"Calendar {cal_id}",
                            'color': cal_color or "#3366CC",
                            'provider': 'thunderbird'
                        }
                        calendars.append(calendar)
                except Exception as e:
                    print(f"DEBUG: Error getting calendar info from cal_calendars: {e}")
            
            # Close database connection
            conn.close()
            
        except Exception as e:
            print(f"DEBUG: Error getting calendars from Thunderbird database: {e}")
    
    print(f"DEBUG: Found {len(calendars)} Thunderbird calendars")
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
            start_timestamp = int(start_date.timestamp() * 1000000)
            end_timestamp = int(end_date.timestamp() * 1000000)
            
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
                    # Convert timestamps to datetime
                    start_dt = datetime.fromtimestamp(event_start / 1000000, timezone.utc)
                    end_dt = datetime.fromtimestamp(event_end / 1000000, timezone.utc)
                    
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
                        'start': start_dt,
                        'end': end_dt,
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