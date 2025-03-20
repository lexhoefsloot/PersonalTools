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
    calendar_dbs = find_all_calendar_databases()
    
    if not calendar_dbs:
        print("Error: No calendar databases found")
        print("Thunderbird may not be configured with a calendar or events")
        return
    
    # Get today's date
    today = date.today()
    
    found_events = False
    for db_path in calendar_dbs:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get database schema to determine correct query
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [table[0] for table in cursor.fetchall()]
            
            query = None
            if 'cal_items' in tables:
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
            elif 'cal_events' in tables:
                query = """
                SELECT 
                    summary,
                    event_start,
                    event_end,
                    location
                FROM cal_events
                WHERE date(event_start) = date(?)
                ORDER BY event_start
                """
            elif 'calendaritems' in tables:
                query = """
                SELECT 
                    title,
                    dtstart,
                    dtend,
                    location
                FROM calendaritems
                WHERE date(dtstart) = date(?)
                ORDER BY dtstart
                """
            
            if query:
                cursor.execute(query, (today.isoformat(),))
                events = cursor.fetchall()
                
                if events:
                    found_events = True
                    print(f"\nEvents for {today.strftime('%A, %B %d, %Y')} from {db_path}:")
                    print("-" * 50)
                    
                    for event in events:
                        title, start, end, location = event
                        try:
                            start_time = datetime.fromisoformat(start).strftime("%I:%M %p")
                            end_time = datetime.fromisoformat(end).strftime("%I:%M %p")
                        except ValueError:
                            # Try different date format if ISO format fails
                            start_time = "All day"
                            end_time = "All day"
                        
                        location_str = f" at {location}" if location else ""
                        print(f"{start_time} - {end_time}: {title}{location_str}")
            
            conn.close()
            
        except sqlite3.Error as e:
            print(f"Database error with {db_path}: {e}")
        except Exception as e:
            print(f"An error occurred with {db_path}: {e}")
    
    if not found_events:
        print("No events found for today")

if __name__ == "__main__":
    get_thunderbird_calendar_events() 