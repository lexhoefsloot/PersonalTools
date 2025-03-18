from datetime import datetime, timedelta
import pytz
import re
from dateutil import parser

def parse_time_slot(slot):
    """
    Parse time slot dictionary to datetime objects
    
    Args:
        slot: Dictionary with start and end keys in ISO format
    
    Returns:
        Tuple of (start_datetime, end_datetime)
    """
    try:
        # Parse start time
        if 'start' in slot and slot['start']:
            start_time = parser.parse(slot['start'])
            if start_time.tzinfo is None:
                start_time = pytz.UTC.localize(start_time)
        else:
            return None, None
        
        # Parse end time
        if 'end' in slot and slot['end']:
            end_time = parser.parse(slot['end'])
            if end_time.tzinfo is None:
                end_time = pytz.UTC.localize(end_time)
        else:
            # If no end time provided, assume 1-hour duration
            end_time = start_time + timedelta(hours=1)
        
        return start_time, end_time
    
    except (ValueError, TypeError) as e:
        print(f"Error parsing time slot: {str(e)}")
        return None, None

def parse_date_range(time_slots):
    """
    Parse list of time slots to get overall date range
    
    Args:
        time_slots: List of time slot dictionaries with start and end keys
    
    Returns:
        Tuple of (start_date, end_date) covering all slots
    """
    if not time_slots:
        # Default to current week if no time slots provided
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
        
        return start_of_week, end_of_week
    
    # Initialize with extreme values
    min_date = None
    max_date = None
    
    for slot in time_slots:
        start, end = parse_time_slot(slot)
        
        if start:
            if min_date is None or start < min_date:
                min_date = start
        
        if end:
            if max_date is None or end > max_date:
                max_date = end
    
    # If no valid dates found, use default range
    if min_date is None or max_date is None:
        today = datetime.now()
        min_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
        max_date = today + timedelta(days=7)
    
    # Expand range by 1 day on each side
    min_date = min_date - timedelta(days=1)
    max_date = max_date + timedelta(days=1)
    
    return min_date, max_date

def format_datetime_for_display(dt):
    """
    Format datetime for user-friendly display
    
    Args:
        dt: Datetime object
    
    Returns:
        Formatted string
    """
    # Check if datetime has timezone info
    if dt.tzinfo:
        # Convert to local timezone
        local_dt = dt.astimezone(datetime.now().astimezone().tzinfo)
    else:
        # Assume it's already in local timezone
        local_dt = dt
    
    # Format the datetime
    return local_dt.strftime("%A, %B %d, %Y at %I:%M %p")

def format_time_slot_for_display(slot):
    """
    Format time slot for user-friendly display
    
    Args:
        slot: Dictionary with start and end keys
    
    Returns:
        Formatted string
    """
    start, end = parse_time_slot(slot)
    
    if not start:
        return "Invalid time slot"
    
    # If start and end are on the same day
    if start.date() == end.date():
        return f"{start.strftime('%A, %B %d, %Y from %I:%M %p')} to {end.strftime('%I:%M %p')}"
    else:
        return f"{start.strftime('%A, %B %d, %Y at %I:%M %p')} to {end.strftime('%A, %B %d, %Y at %I:%M %p')}"

def format_time_for_clipboard(slot):
    """
    Format time slot for clipboard copying
    
    Args:
        slot: Dictionary with start and end keys
    
    Returns:
        Formatted string
    """
    start, end = parse_time_slot(slot)
    
    if not start:
        return "Invalid time slot"
    
    # If start and end are on the same day
    if start.date() == end.date():
        return f"{start.strftime('%A, %B %d from %I:%M')} to {end.strftime('%I:%M %p')}"
    else:
        return f"{start.strftime('%A, %B %d at %I:%M %p')} to {end.strftime('%A, %B %d at %I:%M %p')}" 