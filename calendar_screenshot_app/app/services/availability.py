from datetime import datetime, timedelta
import pytz
from app.utils.date_utils import parse_time_slot

def check_availability(time_slots, events):
    """
    Check if suggested time slots conflict with existing calendar events
    
    Args:
        time_slots: List of time slot dictionaries with start and end keys
        events: List of calendar event dictionaries with start and end keys
    
    Returns:
        Dictionary mapping each time slot to availability status and conflicts
    """
    availability_results = {}
    
    for slot in time_slots:
        slot_start, slot_end = parse_time_slot(slot)
        
        # Skip invalid time slots
        if not slot_start or not slot_end:
            availability_results[f"{slot.get('start', 'Unknown')} - {slot.get('end', 'Unknown')}"] = {
                'available': False,
                'conflicts': [],
                'error': 'Invalid time format'
            }
            continue
        
        # Find conflicts with events
        conflicts = []
        for event in events:
            event_start = event['start']
            event_end = event['end']
            
            # Check for overlap
            if (slot_start < event_end and slot_end > event_start):
                conflicts.append({
                    'title': event['title'],
                    'calendar_id': event.get('calendar_id', 'Unknown'),
                    'provider': event.get('provider', 'Unknown'),
                    'start': event_start.isoformat(),
                    'end': event_end.isoformat()
                })
        
        # Add result for this time slot
        slot_key = f"{slot['start']} - {slot.get('end', 'Unknown')}"
        availability_results[slot_key] = {
            'available': len(conflicts) == 0,
            'conflicts': conflicts,
            'start': slot_start.isoformat(),
            'end': slot_end.isoformat(),
            'context': slot.get('context', '')
        }
    
    return availability_results

def find_available_slots(start_date, end_date, events, duration_minutes=60, start_hour=9, end_hour=17):
    """
    Find available time slots within a date range
    
    Args:
        start_date: Start date of the range to search
        end_date: End date of the range to search
        events: List of calendar events within the date range
        duration_minutes: Duration of the meeting in minutes (default: 60)
        start_hour: Start hour of the workday (default: 9)
        end_hour: End hour of the workday (default: 17)
    
    Returns:
        List of available time slots
    """
    # Convert to tz-aware datetimes if they aren't already
    if start_date.tzinfo is None:
        start_date = pytz.UTC.localize(start_date)
    if end_date.tzinfo is None:
        end_date = pytz.UTC.localize(end_date)
    
    # Set start_date to start of workday and end_date to end of workday
    start_date = start_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    
    # Duration as timedelta
    duration = timedelta(minutes=duration_minutes)
    
    # Make a list of busy periods from events
    busy_periods = []
    for event in events:
        busy_periods.append((event['start'], event['end']))
    
    # Sort busy periods by start time
    busy_periods.sort(key=lambda x: x[0])
    
    # Find available slots by iterating through the date range
    available_slots = []
    current_date = start_date
    
    while current_date <= end_date:
        # Skip weekends (0 = Monday, 6 = Sunday)
        if current_date.weekday() >= 5:  # Saturday or Sunday
            current_date = current_date + timedelta(days=1)
            current_date = current_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            continue
        
        # Set workday start and end for the current day
        day_start = current_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        day_end = current_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        
        # Check for available slots in this day
        slot_start = day_start
        
        while slot_start + duration <= day_end:
            slot_end = slot_start + duration
            
            # Check if this slot overlaps with any busy period
            is_available = True
            for busy_start, busy_end in busy_periods:
                if slot_start < busy_end and slot_end > busy_start:
                    is_available = False
                    # Move slot_start to the end of this busy period
                    slot_start = busy_end
                    break
            
            # If available, add to results and move to next slot
            if is_available:
                available_slots.append({
                    'start': slot_start.isoformat(),
                    'end': slot_end.isoformat()
                })
                slot_start = slot_end
            
            # Add 30-minute increments
            if slot_start == slot_end:
                slot_start = slot_start + timedelta(minutes=30)
        
        # Move to next day
        current_date = current_date + timedelta(days=1)
        current_date = current_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    
    return available_slots 