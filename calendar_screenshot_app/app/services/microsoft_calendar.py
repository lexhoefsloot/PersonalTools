import os
import json
import msal
import requests
from datetime import datetime
import pytz

# Microsoft Graph API endpoints
GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'
AUTHORITY = 'https://login.microsoftonline.com/common'

# Set up OAuth 2.0 scopes
SCOPES = ['Calendars.Read']

def get_microsoft_auth_url():
    """Get the authorization URL for Microsoft OAuth"""
    client_id = os.environ.get('MICROSOFT_CLIENT_ID')
    
    if not client_id:
        raise ValueError("Microsoft API credentials not found in environment variables")
    
    # Initialize MSAL app
    app = msal.PublicClientApplication(
        client_id,
        authority=AUTHORITY
    )
    
    # Generate URL for authorization
    auth_url = app.get_authorization_request_url(
        SCOPES,
        redirect_uri="http://localhost:5000/auth/microsoft/callback",
        prompt="select_account"
    )
    
    return auth_url

def get_microsoft_token(auth_code):
    """Exchange authorization code for access token"""
    client_id = os.environ.get('MICROSOFT_CLIENT_ID')
    client_secret = os.environ.get('MICROSOFT_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        raise ValueError("Microsoft API credentials not found in environment variables")
    
    # Initialize confidential client application
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=AUTHORITY,
        client_credential=client_secret
    )
    
    # Acquire token by authorization code
    result = app.acquire_token_by_authorization_code(
        auth_code,
        scopes=SCOPES,
        redirect_uri="http://localhost:5000/auth/microsoft/callback"
    )
    
    if "error" in result:
        raise ValueError(f"Error getting Microsoft token: {result['error_description']}")
    
    # Return token information
    return {
        'access_token': result['access_token'],
        'refresh_token': result.get('refresh_token'),
        'expires_in': result['expires_in'],
        'client_id': client_id,
        'client_secret': client_secret
    }

def get_microsoft_headers(token_info):
    """Get headers for Microsoft Graph API requests"""
    return {
        'Authorization': f"Bearer {token_info['access_token']}",
        'Content-Type': 'application/json'
    }

def refresh_microsoft_token(token_info):
    """Refresh Microsoft access token if expired"""
    client_id = token_info['client_id']
    client_secret = token_info['client_secret']
    refresh_token = token_info.get('refresh_token')
    
    if not refresh_token:
        raise ValueError("No refresh token available")
    
    # Initialize confidential client application
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=AUTHORITY,
        client_credential=client_secret
    )
    
    # Acquire token by refresh token
    result = app.acquire_token_by_refresh_token(
        refresh_token,
        scopes=SCOPES
    )
    
    if "error" in result:
        raise ValueError(f"Error refreshing Microsoft token: {result['error_description']}")
    
    # Update token information
    token_info['access_token'] = result['access_token']
    token_info['refresh_token'] = result.get('refresh_token', token_info['refresh_token'])
    token_info['expires_in'] = result['expires_in']
    
    return token_info

def get_microsoft_calendars(token_info):
    """Get list of Microsoft calendars for the authenticated user"""
    try:
        headers = get_microsoft_headers(token_info)
        
        # Get list of calendars
        response = requests.get(
            f"{GRAPH_API_ENDPOINT}/me/calendars",
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"Error getting Microsoft calendars: {response.text}")
            return []
        
        calendar_list = response.json()
        
        # Format calendar information
        calendars = []
        for calendar in calendar_list.get('value', []):
            calendars.append({
                'id': f"microsoft:{calendar['id']}",
                'name': calendar.get('name', 'Unnamed Calendar'),
                'description': calendar.get('description', ''),
                'primary': calendar.get('isDefaultCalendar', False)
            })
        
        return calendars
    
    except Exception as e:
        print(f"Error getting Microsoft calendars: {str(e)}")
        return []

def get_microsoft_events(token_info, calendar_id, start_date, end_date):
    """Get events from a Microsoft calendar within specified date range"""
    try:
        headers = get_microsoft_headers(token_info)
        
        # Format date range for API (ISO 8601)
        start_datetime = start_date.strftime("%Y-%m-%dT%H:%M:%S") + 'Z'
        end_datetime = end_date.strftime("%Y-%m-%dT%H:%M:%S") + 'Z'
        
        # Get events from calendar
        response = requests.get(
            f"{GRAPH_API_ENDPOINT}/me/calendars/{calendar_id}/calendarView",
            headers=headers,
            params={
                'startDateTime': start_datetime,
                'endDateTime': end_datetime,
                '$select': 'id,subject,start,end,isAllDay'
            }
        )
        
        if response.status_code != 200:
            print(f"Error getting Microsoft events: {response.text}")
            return []
        
        events_result = response.json()
        
        # Format event information
        events = []
        for event in events_result.get('value', []):
            # Skip all-day events
            if event.get('isAllDay', False):
                continue
            
            # Convert to datetime objects
            start = event['start']['dateTime'] + 'Z'
            end = event['end']['dateTime'] + 'Z'
            
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            events.append({
                'id': event['id'],
                'title': event.get('subject', 'Untitled Event'),
                'start': start_dt,
                'end': end_dt,
                'calendar_id': calendar_id,
                'provider': 'microsoft'
            })
        
        return events
    
    except Exception as e:
        print(f"Error getting Microsoft events: {str(e)}")
        return [] 