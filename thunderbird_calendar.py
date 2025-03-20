#!/usr/bin/env python3
import os
import json
from datetime import date, datetime, timezone, timedelta
import sqlite3
import glob
import subprocess
import pytz

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

def is_same_day(dt1, dt2):
    """Check if two datetime objects are on the same day"""
    if dt1 is None or dt2 is None:
        return False
    return (dt1.year == dt2.year and 
            dt1.month == dt2.month and 
            dt1.day == dt2.day)

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

def find_sqlite_files(directory, max_depth=3):
    """Find all SQLite files in a directory and its subdirectories up to max_depth"""
    if max_depth <= 0:
        return []
    
    result = []
    try:
        for item in os.listdir(directory):
            path = os.path.join(directory, item)
            if os.path.isfile(path) and path.endswith('.sqlite'):
                result.append(path)
            elif os.path.isdir(path):
                result.extend(find_sqlite_files(path, max_depth - 1))
    except (PermissionError, FileNotFoundError):
        pass
    
    return result

def check_if_calendar_db(db_path):
    """Check if the SQLite database contains calendar tables"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check for common calendar tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='cal_items' OR name='cal_events' OR name='calendaritems' OR name='events');")
        result = cursor.fetchall()
        
        conn.close()
        
        return len(result) > 0
    except sqlite3.Error:
        return False

def examine_database(db_path):
    """Examine database structure to help debugging"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"\nDatabase at {db_path} contains {len(tables)} tables:")
        
        for table in tables:
            table_name = table[0]
            print(f"\n* Table: {table_name}")
            
            # Get table schema
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns = cursor.fetchall()
            print("  Columns:")
            for col in columns:
                col_id, col_name, col_type, col_notnull, col_default, col_pk = col
                print(f"    - {col_name} ({col_type})")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            row_count = cursor.fetchone()[0]
            print(f"  Row count: {row_count}")
            
            # Get sample data if there are rows
            if row_count > 0:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 1;")
                sample = cursor.fetchone()
                print("  Sample data (first row):")
                for i, col in enumerate(columns):
                    col_name = col[1]
                    if i < len(sample):  # Ensure we don't go out of bounds
                        sample_value = sample[i]
                        # Truncate long values
                        if isinstance(sample_value, str) and len(sample_value) > 50:
                            sample_value = sample_value[:47] + "..."
                        print(f"    - {col_name}: {sample_value}")
        
        conn.close()
    except sqlite3.Error as e:
        print(f"Error examining database: {e}")

def find_all_calendar_databases():
    """Find all possible calendar databases"""
    profiles = find_thunderbird_profiles()
    possible_dbs = []
    
    for profile in profiles:
        print(f"Searching in profile: {profile}")
        # Look for specific calendar paths
        calendar_paths = [
            os.path.join(profile, "calendar-data"),
            os.path.join(profile, "storage", "calendar"),
            os.path.join(profile, "storage", "default", "calendar"),
            profile
        ]
        
        # Find all SQLite files in these directories
        for path in calendar_paths:
            if os.path.exists(path):
                sqlite_files = find_sqlite_files(path)
                for db in sqlite_files:
                    if check_if_calendar_db(db):
                        possible_dbs.append(db)
                        print(f"  Found potential calendar database: {db}")
    
    return possible_dbs

def get_thunderbird_calendar_events():
    # Try using cache.sqlite instead of local.sqlite
    calendar_db = os.path.expanduser("~/.thunderbird/qw0vnk3t.default-default/calendar-data/cache.sqlite")
    
    if not os.path.exists(calendar_db):
        print(f"Error: Calendar database not found at {calendar_db}")
        return
    
    print(f"Using calendar database: {calendar_db}")
    
    try:
        conn = sqlite3.connect(calendar_db)
        cursor = conn.cursor()
        
        # Get today's date in UTC
        today = datetime.now(timezone.utc)
        
        # Query events from cal_events table
        query = """
        SELECT cal_id, title, event_start, event_end, event_start_tz, event_end_tz, flags
        FROM cal_events
        ORDER BY event_start;
        """
        
        cursor.execute(query)
        events = cursor.fetchall()
        
        print("\nEvents for today:")
        print("=" * 50)
        
        found_events = False
        for event in events:
            cal_id, title, start, end, start_tz, end_tz, flags = event
            
            # Convert timestamps to datetime objects
            start_dt = microseconds_to_datetime(start, start_tz)
            
            # Skip if not today's event
            if not is_same_day(start_dt, today):
                continue
                
            found_events = True
            end_dt = microseconds_to_datetime(end, end_tz)
            
            # Format the output
            print(f"\nTitle: {title}")
            print(f"Time: {start_dt.strftime('%I:%M %p')} - {end_dt.strftime('%I:%M %p')}")
            print(f"Timezone: {start_tz}")
            print(f"Status: {'Cancelled' if flags & 1 else 'Active'}")
            print("-" * 30)
        
        if not found_events:
            print("No events found for today")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if "database is locked" in str(e):
            print("The database is locked. Try closing Thunderbird before running this script.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    get_thunderbird_calendar_events() 