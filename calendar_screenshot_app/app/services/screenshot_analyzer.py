import os
import json
import requests
import re
import cv2
import numpy as np
import pytesseract
from datetime import datetime, timedelta
import logging
from flask import current_app
import platform

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def analyze_screenshot(image_path):
    """
    Analyze a screenshot to extract time slots and date information.
    
    This function uses OCR (Optical Character Recognition) to extract text from
    the provided image and then looks for time patterns to identify meeting times.
    
    Args:
        image_path: Path to the screenshot image file
        
    Returns:
        dict: A dictionary containing the extracted information:
            - date: The date mentioned in the screenshot (or today if none found)
            - is_suggestion: Whether the screenshot suggests times or requests a time
            - time_slots: List of time slots with start_time and end_time as datetime objects
            - text: The extracted text from the image
    """
    # Extract text from the image using OCR
    extracted_text = extract_text_from_image(image_path)
    
    if not extracted_text:
        return {'error': 'No text could be extracted from the image'}
    
    # Find date mentions in the text
    date = extract_date(extracted_text)
    
    # Detect if this is a suggested time or a request for time
    is_suggestion = detect_suggestion(extracted_text)
    
    # Extract time slots
    time_slots = extract_time_slots(extracted_text, date)
    
    return {
        'date': date,
        'is_suggestion': is_suggestion,
        'time_slots': time_slots,
        'text': extracted_text
    }

def extract_text_from_image(image_path):
    """
    Extract text from an image using Tesseract OCR
    
    Args:
        image_path: Path to the image file
        
    Returns:
        str: Extracted text from the image
    """
    try:
        # Check if Tesseract is available
        if platform.system() == 'Darwin':  # macOS
            if not os.path.exists('/usr/local/bin/tesseract') and not os.path.exists('/opt/homebrew/bin/tesseract'):
                logger.warning("Tesseract not found. Please install it with: brew install tesseract")
                return None
        
        # Read the image
        image = cv2.imread(image_path)
        if image is None:
            logger.error(f"Failed to read image: {image_path}")
            return None
        
        # Preprocess the image
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply thresholding to get a binary image
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # Extract text using Tesseract OCR
        text = pytesseract.image_to_string(binary)
        
        return text
    
    except Exception as e:
        logger.error(f"Error extracting text from image: {e}")
        return None

def extract_date(text):
    """
    Extract date information from text
    
    Args:
        text: The text to extract date from
        
    Returns:
        date: The extracted date (today if none found)
    """
    # Try to find common date formats
    date_patterns = [
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}',
        r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?',
        r'\d{1,2}/\d{1,2}/\d{2,4}',
        r'\d{4}-\d{1,2}-\d{1,2}',
        r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}'
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Try to parse the date
            for date_str in matches:
                try:
                    # Handle various date formats
                    if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', date_str):
                        parts = date_str.split('/')
                        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
                        if year < 100:
                            year += 2000  # Assume 21st century for 2-digit years
                        return datetime(year, month, day).date()
                    
                    elif re.search(r'\d{4}-\d{1,2}-\d{1,2}', date_str):
                        parts = date_str.split('-')
                        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
                        return datetime(year, month, day).date()
                    
                    else:
                        # Try to parse more complex date formats
                        # Remove ordinal indicators (st, nd, rd, th)
                        clean_date = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
                        # Try different date formats
                        for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y', 
                                   '%A, %B %d', '%A %B %d']:
                            try:
                                parsed_date = datetime.strptime(clean_date, fmt)
                                # If no year in format, use current year
                                if '%Y' not in fmt:
                                    current_year = datetime.now().year
                                    parsed_date = parsed_date.replace(year=current_year)
                                return parsed_date.date()
                            except ValueError:
                                continue
                except Exception as e:
                    logger.debug(f"Error parsing date '{date_str}': {e}")
                    continue
    
    # Default to today if no date is found
    return datetime.now().date()

def detect_suggestion(text):
    """
    Detect if the text is suggesting times or requesting a time
    
    Args:
        text: The text to analyze
        
    Returns:
        bool: True if suggesting times, False if requesting a time
    """
    suggestion_phrases = [
        r'(?:I\s+)?(?:am|\'m)\s+available',
        r'(?:I\s+)?(?:can|could)\s+do',
        r'(?:I\s+)?(?:have|\'ve)\s+time',
        r'(?:I\s+)?(?:suggest|propose|offer)',
        r'(?:here\s+are|these\s+are)\s+(?:some|the|my)\s+(?:times|slots)',
        r'(?:works|available|free)\s+for\s+me',
        r'my\s+availability'
    ]
    
    request_phrases = [
        r'(?:are\s+you|would\s+you\s+be)\s+available',
        r'(?:can|could)\s+you\s+(?:do|make)',
        r'(?:what|which)\s+(?:time|times|day|date)\s+(?:works|is\s+good|are\s+you\s+free)',
        r'(?:let\s+me\s+know|please\s+confirm)\s+(?:your|if\s+you\s+are)\s+availability',
        r'(?:when|what\s+time)\s+(?:are\s+you|would\s+you\s+be)\s+free',
        r'(?:would|does)\s+(?:any\s+of\s+)?(?:these|this|those|that)\s+(?:work|time\s+work)',
        r'your\s+availability'
    ]
    
    # Check for suggestion phrases
    for phrase in suggestion_phrases:
        if re.search(phrase, text, re.IGNORECASE):
            return True
    
    # Check for request phrases
    for phrase in request_phrases:
        if re.search(phrase, text, re.IGNORECASE):
            return False
    
    # Default to suggestion if no clear indicators
    return True

def extract_time_slots(text, date):
    """
    Extract time slots from the text
    
    Args:
        text: The text to extract time slots from
        date: The date to associate with the time slots
        
    Returns:
        list: List of dictionaries with start_time and end_time as datetime objects
    """
    # Different time formats to look for
    time_patterns = [
        # 9am-10am, 9am - 10am, 9 am - 10 am
        r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)\s*[-–—to]+\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)',
        
        # 9-10am, 9 - 10am, 9-10 am
        r'(\d{1,2})(?::(\d{2}))?\s*[-–—to]+\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)',
        
        # 9am to 10am
        r'(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)\s*to\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)',
        
        # 09:00-10:00, 09:00 - 10:00 (24-hour format)
        r'(\d{1,2}):(\d{2})\s*[-–—to]+\s*(\d{1,2}):(\d{2})(?!\s*[ap]\.?m\.?)',
        
        # Time in (parentheses or brackets) like: (9am-10am)
        r'[(\[{](\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)\s*[-–—to]+\s*(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)[)\]}]',
    ]
    
    time_slots = []
    
    for pattern in time_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        
        for match in matches:
            try:
                groups = match.groups()
                
                # Handle different pattern matches
                if len(groups) == 6 and groups[2] and groups[5]:  # Pattern with am/pm for both times
                    start_hour = int(groups[0])
                    start_minute = int(groups[1]) if groups[1] else 0
                    start_ampm = groups[2].lower().replace('.', '')
                    
                    end_hour = int(groups[3])
                    end_minute = int(groups[4]) if groups[4] else 0
                    end_ampm = groups[5].lower().replace('.', '')
                    
                    # Convert to 24-hour format
                    if start_ampm.startswith('p') and start_hour < 12:
                        start_hour += 12
                    elif start_ampm.startswith('a') and start_hour == 12:
                        start_hour = 0
                        
                    if end_ampm.startswith('p') and end_hour < 12:
                        end_hour += 12
                    elif end_ampm.startswith('a') and end_hour == 12:
                        end_hour = 0
                
                elif len(groups) == 5 and groups[4]:  # Pattern with shared am/pm
                    start_hour = int(groups[0])
                    start_minute = int(groups[1]) if groups[1] else 0
                    
                    end_hour = int(groups[2])
                    end_minute = int(groups[3]) if groups[3] else 0
                    
                    shared_ampm = groups[4].lower().replace('.', '')
                    
                    # If it's pm and hour < 12, add 12 to convert to 24-hour
                    if shared_ampm.startswith('p'):
                        if start_hour < 12:
                            start_hour += 12
                        if end_hour < 12:
                            end_hour += 12
                    elif shared_ampm.startswith('a'):
                        if start_hour == 12:
                            start_hour = 0
                        if end_hour == 12:
                            end_hour = 0
                
                elif len(groups) == 4:  # 24-hour format pattern
                    start_hour = int(groups[0])
                    start_minute = int(groups[1])
                    end_hour = int(groups[2])
                    end_minute = int(groups[3])
                
                else:
                    continue  # Skip if pattern doesn't match expected groups
                
                # Create datetime objects
                start_time = datetime.combine(date, datetime.min.time().replace(hour=start_hour, minute=start_minute))
                end_time = datetime.combine(date, datetime.min.time().replace(hour=end_hour, minute=end_minute))
                
                # Handle case where end time is earlier than start time (likely next day)
                if end_time <= start_time:
                    end_time += timedelta(days=1)
                
                time_slot = {
                    'start_time': start_time,
                    'end_time': end_time,
                    'title': match.group(0)  # Use the original matched text as title
                }
                
                time_slots.append(time_slot)
                
            except Exception as e:
                logger.debug(f"Error parsing time slot '{match.group(0)}': {e}")
                continue
    
    return time_slots 