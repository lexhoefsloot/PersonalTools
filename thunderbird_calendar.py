#!/usr/bin/env python3
import subprocess
from datetime import date, datetime
import os
import json
import shutil

def get_thunderbird_calendar_events():
    # Try to find Thunderbird executable
    thunderbird_path = shutil.which('thunderbird') or '/usr/bin/thunderbird'
    
    if not os.path.exists(thunderbird_path):
        print("Error: Thunderbird not found. Please ensure it's installed.")
        return
    
    try:
        # Get today's date
        today = date.today()
        
        # Create a temporary JavaScript file to query the calendar
        js_content = """
        var calendar = Components.classes["@mozilla.org/calendar/calendar-service;1"]
            .getService(Components.interfaces.calICalendarService)
            .getDefaultCalendar("local");
        
        var start = new Date();
        start.setHours(0, 0, 0, 0);
        var end = new Date();
        end.setHours(23, 59, 59, 999);
        
        var filter = calendar.createItemFilter();
        filter.startDate = start;
        filter.endDate = end;
        
        var items = calendar.getItems(filter, 0);
        var events = [];
        
        while (items.hasMoreElements()) {
            var item = items.getNext().QueryInterface(Components.interfaces.calIEvent);
            events.push({
                title: item.title,
                start: item.startDate.toJSDate().toISOString(),
                end: item.endDate.toJSDate().toISOString(),
                location: item.getProperty("LOCATION") || ""
            });
        }
        
        print(JSON.stringify(events));
        """
        
        # Write the JavaScript to a temporary file
        with open("/tmp/calendar_query.js", "w") as f:
            f.write(js_content)
        
        # Run Thunderbird with the JavaScript file
        cmd = [thunderbird_path, "-chrome", "file:///tmp/calendar_query.js"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("Error running Thunderbird command")
            return
        
        try:
            events = json.loads(result.stdout)
            
            if not events:
                print("No events found for today")
                return
            
            print(f"\nEvents for {today.strftime('%A, %B %d, %Y')}:")
            print("-" * 50)
            
            for event in events:
                start_time = datetime.fromisoformat(event['start']).strftime("%I:%M %p")
                end_time = datetime.fromisoformat(event['end']).strftime("%I:%M %p")
                location_str = f" at {event['location']}" if event['location'] else ""
                print(f"{start_time} - {end_time}: {event['title']}{location_str}")
                
        except json.JSONDecodeError:
            print("Error parsing calendar data")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Clean up temporary file
        if os.path.exists("/tmp/calendar_query.js"):
            os.remove("/tmp/calendar_query.js")

if __name__ == "__main__":
    get_thunderbird_calendar_events() 