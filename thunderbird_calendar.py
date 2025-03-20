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
    # Direct path to the calendar database
    calendar_db = os.path.expanduser("~/.thunderbird/qw0vnk3t.default-default/calendar-data/local.sqlite")
    
    if not os.path.exists(calendar_db):
        print(f"Error: Calendar database not found at {calendar_db}")
        return
    
    print(f"Using calendar database: {calendar_db}")
    
    try:
        conn = sqlite3.connect(calendar_db)
        cursor = conn.cursor()
        
        # Get today's date
        today = date.today()
        
        # Query for events today
        query = """
        SELECT 
            item_title,
            item_start_date,
            item_end_date,
            item_location
        FROM cal_items
        WHERE date(item_start_date) = date(?)
        ORDER BY item_start_date
        """
        
        cursor.execute(query, (today.isoformat(),))
        events = cursor.fetchall()
        
        if not events:
            print(f"No events found for today ({today.strftime('%A, %B %d, %Y')})")
            return
        
        print(f"\nEvents for {today.strftime('%A, %B %d, %Y')}:")
        print("-" * 50)
        
        for event in events:
            title, start, end, location = event
            try:
                start_time = datetime.fromisoformat(start).strftime("%I:%M %p")
                end_time = datetime.fromisoformat(end).strftime("%I:%M %p")
            except ValueError:
                # Handle all-day events
                start_time = "All day"
                end_time = "All day"
            
            location_str = f" at {location}" if location else ""
            print(f"{start_time} - {end_time}: {title}{location_str}")
        
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