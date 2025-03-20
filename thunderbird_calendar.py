#!/usr/bin/env python3
import os
import json
from datetime import date, datetime
import sqlite3
import glob
import subprocess

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
    
    # First examine the database structure
    examine_database(calendar_db)
    
    try:
        conn = sqlite3.connect(calendar_db)
        cursor = conn.cursor()
        
        # Get today's date
        today = date.today()
        
        # First check what tables are available
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table[0] for table in cursor.fetchall()]
        
        print("\nAttempting to find calendar events for today...")
        
        # Try different tables that might contain calendar data
        event_tables = [table for table in tables if 'event' in table.lower() or 'cal' in table.lower() or 'item' in table.lower()]
        
        found_events = False
        for table in event_tables:
            try:
                # Get columns in this table
                cursor.execute(f"PRAGMA table_info({table});")
                columns = cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                # Look for datetime columns and title/summary columns
                datetime_cols = [col for col in column_names if 'start' in col.lower() or 'date' in col.lower() or 'time' in col.lower()]
                title_cols = [col for col in column_names if 'title' in col.lower() or 'summary' in col.lower() or 'subject' in col.lower()]
                
                if datetime_cols and title_cols:
                    print(f"\nChecking table: {table}")
                    print(f"Date column: {datetime_cols[0]}")
                    print(f"Title column: {title_cols[0]}")
                    
                    # Try querying this table for today's events
                    query = f"SELECT * FROM {table}"
                    cursor.execute(query)
                    results = cursor.fetchall()
                    
                    if results:
                        print(f"Found {len(results)} rows in table {table}")
                        
                        # Print sample results
                        for i, result in enumerate(results[:5]):  # Show up to 5 events
                            event_data = {}
                            for idx, col in enumerate(column_names):
                                if idx < len(result):
                                    event_data[col] = result[idx]
                            
                            print(f"\nEvent {i+1}:")
                            for key, value in event_data.items():
                                # Truncate long values
                                if isinstance(value, str) and len(value) > 50:
                                    value = value[:47] + "..."
                                print(f"  {key}: {value}")
                        
                        found_events = True
            except sqlite3.Error as e:
                print(f"Error querying table {table}: {e}")
        
        if not found_events:
            print("Could not find any calendar events in the database")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        # If database is locked, suggest closing Thunderbird
        if "database is locked" in str(e):
            print("The database is locked. Try closing Thunderbird before running this script.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    get_thunderbird_calendar_events() 