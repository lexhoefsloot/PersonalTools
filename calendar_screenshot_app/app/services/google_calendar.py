import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime
import pytz

# Set up OAuth 2.0 scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def get_google_auth_url():
    """Get the authorization URL for Google OAuth"""
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        raise ValueError("Google API credentials not found in environment variables")
    
    # Create the flow using client secrets
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:5000/auth/google/callback"]
            }
        },
        scopes=SCOPES,
        redirect_uri="http://localhost:5000/auth/google/callback"
    )
    
    # Generate URL for authorization
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    return auth_url

def get_google_token(auth_code):
    """Exchange authorization code for access token"""
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        raise ValueError("Google API credentials not found in environment variables")
    
    # Create the flow using client secrets
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:5000/auth/google/callback"]
            }
        },
        scopes=SCOPES,
        redirect_uri="http://localhost:5000/auth/google/callback"
    )
    
    # Exchange auth code for access token
    flow.fetch_token(code=auth_code)
    
    # Get credentials
    credentials = flow.credentials
    
    # Return token information as dictionary
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

def get_google_service(token_info):
    """Create Google Calendar service from token information"""
    # Create credentials object from token info
    credentials = Credentials(
        token=token_info['token'],
        refresh_token=token_info.get('refresh_token'),
        token_uri=token_info['token_uri'],
        client_id=token_info['client_id'],
        client_secret=token_info['client_secret'],
        scopes=token_info['scopes']
    )
    
    # Build the service
    service = build('calendar', 'v3', credentials=credentials)
    
    return service

def get_google_calendars(token_info):
    """Get list of Google calendars for the authenticated user"""
    try:
        service = get_google_service(token_info)
        
        # Get list of calendars
        calendar_list = service.calendarList().list().execute()
        
        # Format calendar information
        calendars = []
        for calendar in calendar_list.get('items', []):
            calendars.append({
                'id': f"google:{calendar['id']}",
                'name': calendar.get('summary', 'Unnamed Calendar'),
                'description': calendar.get('description', ''),
                'primary': calendar.get('primary', False)
            })
        
        return calendars
    
    except Exception as e:
        print(f"Error getting Google calendars: {str(e)}")
        return []

def get_google_events(token_info, calendar_id, start_date, end_date):
    """Get events from a Google calendar within specified date range"""
    try:
        service = get_google_service(token_info)
        
        # Format date range for API
        start_datetime = start_date.isoformat() + 'Z'  # 'Z' indicates UTC time
        end_datetime = end_date.isoformat() + 'Z'
        
        # Get events from calendar
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_datetime,
            timeMax=end_datetime,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        # Format event information
        events = []
        for event in events_result.get('items', []):
            # Get start and end time
            start = event['start'].get('dateTime')
            end = event['end'].get('dateTime')
            
            # Skip all-day events or events without specific times
            if not start or not end:
                continue
            
            # Convert to datetime objects
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            events.append({
                'id': event['id'],
                'title': event.get('summary', 'Untitled Event'),
                'start': start_dt,
                'end': end_dt,
                'calendar_id': calendar_id,
                'provider': 'google'
            })
        
        return events
    
    except Exception as e:
        print(f"Error getting Google events: {str(e)}")
        return [] 