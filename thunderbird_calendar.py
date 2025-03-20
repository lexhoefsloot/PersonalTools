#!/usr/bin/env python3
import sqlite3
from datetime import datetime, date
import os

def get_thunderbird_calendar_events():
    # Path to the Thunderbird calendar database
    thunderbird_path = os.path.expanduser("~/.thunderbird/qw0vnk3t.default-default/calendar-data/local.sqlite")
    
    if not os.path.exists(thunderbird_path):
        print("Error: Thunderbird calendar database not found")
        return
    
    try:
        conn = sqlite3.connect(thunderbird_path)
        cursor = conn.cursor()
        
        # Get today's date in the format Thunderbird uses
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
        print(f"Error accessing calendar database: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    get_thunderbird_calendar_events() 