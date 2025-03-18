# Make sure to always update this documentation when structure of functionality of the app changes

# Calendar Screenshot Analyzer - Project Documentation

## Project Overview
A Python web application that:
1. Connects to multiple calendar sources (Google Calendar, Microsoft Office 365, and Apple Calendar on macOS)
2. Analyzes screenshots of conversations to extract meeting time suggestions
3. Identifies whether the text suggests time slots or requests availability
4. Checks calendar availability for detected time slots
5. Provides alternative time suggestions when no suitable slots are found
6. Allows copying of suitable meeting times to clipboard

## Current Project Structure

```
calendar_screenshot_app/
├── app/
│   ├── __init__.py           # Flask application factory
│   ├── main.py               # Legacy entry point (run.py is now used)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth_routes.py    # Google/Microsoft authentication
│   │   ├── calendar_routes.py # Calendar management routes
│   │   └── screenshot_routes.py # Screenshot upload/analysis routes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── apple_calendar.py  # Apple Calendar integration (macOS only)
│   │   ├── availability.py    # Availability checking logic
│   │   ├── clipboard_monitor.py # Clipboard monitoring for screenshots
│   │   ├── claude_service.py  # Anthropic Claude API integration
│   │   ├── google_calendar.py # Google Calendar API integration
│   │   ├── microsoft_calendar.py # Microsoft Graph API integration
│   │   └── screenshot_analyzer.py # OCR and time extraction logic
│   ├── static/               # CSS, JS, and static assets
│   ├── templates/            # HTML templates
│   │   ├── analysis_results.html # Results display
│   │   ├── base.html         # Base template with layout
│   │   ├── calendars.html    # Calendar selection page
│   │   ├── dashboard.html    # Main dashboard
│   │   └── index.html        # Landing page
│   ├── utils/                # Utility functions
│   └── models/               # Data models
├── docs/                     # Documentation
├── tests/                    # Unit and integration tests
├── .env.example              # Environment variables template
├── README.md                 # Project documentation
├── requirements.txt          # Python dependencies
└── run.py                    # Application entry point
```

## Technical Implementation

### Core Components

1. **Multi-Calendar Integration**
   - Google Calendar via Google API
   - Microsoft Calendar via Microsoft Graph API
   - Apple Calendar via AppleScript (macOS only)
   - Calendar selection and filtering interface

2. **Screenshot Analysis**
   - OCR with Tesseract to extract text from images
   - Regular expression patterns to identify date/time information
   - Detection of suggestion vs. request context
   - Time slot extraction and normalization

3. **Availability Engine**
   - Cross-calendar availability checking
   - Conflict detection and resolution
   - Alternative time slot suggestions
   - Time zone handling

4. **User Interface**
   - Responsive Bootstrap-based design
   - Clipboard integration for quick analysis
   - Copy-to-clipboard functionality for time slots
   - Calendar status indicators
   - Modal-based screenshot upload

### Key Features

- **Platform Integration**: Automatic Apple Calendar detection on macOS without authentication
- **Multiple Calendar Sources**: Support for Google, Microsoft, and Apple calendars
- **Clipboard Analysis**: Direct analysis from clipboard screenshots
- **OCR Processing**: Text extraction from images using Tesseract
- **Intelligent Time Detection**: Pattern matching for various time formats
- **Availability Checking**: Cross-reference with all connected calendars
- **Alternative Suggestions**: Recommends available time slots when conflicts exist
- **Responsive UI**: Works on desktop and mobile devices
- **Quick Copy**: Copy time slots with a single click

## Environment Setup

- **Authentication Credentials**: Google Client ID/Secret, Microsoft Client ID/Secret
- **Flask Configuration**: Secret key, debug mode, port settings
- **Feature Flags**: Optional features can be enabled/disabled
- **Development Tools**: Python virtual environment, debug utilities

## Usage Workflow

1. User connects calendar accounts (Google/Microsoft) or uses Apple Calendar on macOS
2. User takes a screenshot of a conversation with time suggestions
3. User either:
   - Copies the screenshot to clipboard and clicks "Analyze from Clipboard"
   - Uploads the screenshot manually
4. Application extracts dates and times from the screenshot
5. Application checks availability across all selected calendars
6. User views results showing which times work with their schedule
7. User can copy suitable time slots to clipboard with one click

## Technologies

- **Backend**: Python 3.8+, Flask
- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5
- **APIs**: Google Calendar API, Microsoft Graph API, AppleScript (macOS)
- **OCR**: Tesseract, OpenCV, Pillow
- **Authentication**: OAuth 2.0
- **Deployment**: Local development server with dotenv configuration 