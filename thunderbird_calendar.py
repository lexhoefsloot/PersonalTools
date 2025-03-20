#!/usr/bin/env python3
import os
import json
from datetime import date, datetime
import sqlite3
import glob

def find_thunderbird_profile():
    """Find the Thunderbird profile directory"""
    # Common profile locations
    possible_paths = [
        os.path.expanduser("~/.thunderbird/*.default"),
        os.path.expanduser("~/.thunderbird/*.default-release"),
        os.path.expanduser("~/.thunderbird/*.default-esr"),
        os.path.expanduser("~/.thunderbird/*.default-nightly")
    ]
    
    for path_pattern in possible_paths:
        matches = glob.glob(path_pattern)
        if matches:
            return matches[0]
    return None

def find_calendar_database(profile_dir):
    """Find the calendar database in various possible locations"""
    possible_locations = [
        os.path.join(profile_dir, "calendar-data", "local.sqlite"),
        os.path.join(profile_dir, "calendar-data", "storage.sqlite"),
        os.path.join(profile_dir, "calendar-data", "calendars.sqlite"),
        os.path.join(profile_dir, "calendar-data", "events.sqlite"),
        os.path.join(profile_dir, "calendar-data", "calendar.sqlite"),
        os.path.join(profile_dir, "calendar.sqlite"),
        os.path.join(profile_dir, "calendar-data", "calendar.sqlite")
    ]
    
    for location in possible_locations:
        if os.path.exists(location):
            return location
    return None

def check_calendar_enabled(profile_dir):
    """Check if calendar functionality is enabled in Thunderbird"""
    prefs_path = os.path.join(profile_dir, "prefs.js")
    if not os.path.exists(prefs_path):
        return False
    
    try:
        with open(prefs_path, 'r') as f:
            prefs = f.read()
            return '"calendar.enabled", true' in prefs
    except Exception:
        return False

def get_thunderbird_calendar_events():
    profile_dir = find_thunderbird_profile()
    if not profile_dir:
        print("Error: Could not find Thunderbird profile directory")
        print("Searched in:", os.path.expanduser("~/.thunderbird/"))
        return
    
    print(f"Found Thunderbird profile at: {profile_dir}")
    
    # Check if calendar is enabled
    if not check_calendar_enabled(profile_dir):
        print("Calendar functionality appears to be disabled in Thunderbird.")
        print("Please enable it in Thunderbird's settings:")
        print("1. Open Thunderbird")
        print("2. Go to Edit > Preferences")
        print("3. Click on 'Calendar' in the left sidebar")
        print("4. Make sure 'Enable Calendar' is checked")
        return
    
    calendar_db = find_calendar_database(profile_dir)
    if not calendar_db:
        print("Error: Calendar database not found")
        print("Searched in:", os.path.join(profile_dir, "calendar-data/"))
        print("\nPlease ensure that:")
        print("1. Calendar functionality is enabled in Thunderbird")
        print("2. You have created at least one calendar")
        print("3. You have added at least one event to your calendar")
        return
    
    print(f"Found calendar database at: {calendar_db}")
    
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
            print("No events found for today")
            return
        
        print(f"\nEvents for {today.strftime('%A, %B %d, %Y')}:")
        print("-" * 50)
        
        for event in events:
            title, start, end, location = event
            start_time = datetime.fromisoformat(start).strftime("%I:%M %p")
            end_time = datetime.fromisoformat(end).strftime("%I:%M %p")
            location_str = f" at {location}" if location else ""
            print(f"{start_time} - {end_time}: {title}{location_str}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    get_thunderbird_calendar_events() 