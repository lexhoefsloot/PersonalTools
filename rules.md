# Calendar Screenshot App - Rules & Architecture

## Core Functionality

The Calendar Screenshot App is designed to help users manage meeting scheduling by analyzing screenshots of conversations and integrating with their calendar data. The application follows these core rules:

### Screenshot Analysis

1. When a screenshot is detected (either uploaded or from clipboard):
   - The screenshot is sent to Claude's API with a specialized prompt
   - Claude analyzes the image to extract meeting-related information
   - Claude determines whether someone is suggesting times or requesting times
   - Claude extracts all time slots, dates, and other relevant context

2. The analysis result will contain:
   - A determination of whether times are being suggested or requested
   - A structured list of all time slots mentioned
   - Contextual information about each time slot (priority, duration, etc.)
   - A confidence score for the analysis

### Calendar Integration

1. The app connects to multiple calendar services:
   - Google Calendar (Gmail accounts)
   - Microsoft 365 Calendar
   - Apple Calendar (local macOS calendars)

2. Users can:
   - Choose which calendars from each service to include in availability checks
   - View their availability for the time slots extracted from screenshots
   - See visualizations of their calendar alongside suggested time slots

### Scheduling Workflow

1. When someone is suggesting times (is_suggestion = true):
   - Show the user's calendar with the suggested time slots highlighted
   - Indicate which suggestions conflict with existing events
   - Allow the user to select which time slots work for them

2. When someone is requesting times (is_suggestion = false):
   - Show the user's calendar with available time slots highlighted
   - Allow the user to select suitable times from their available slots
   - Generate formatted text for these selected times to copy into a response

## Technical Architecture

1. **Frontend**: Flask-based web application with Jinja2 templates
   - Responsive interface for mobile and desktop use
   - Real-time calendar visualization

2. **Backend Services**:
   - Claude API integration for screenshot analysis
   - Calendar service integrations (Google, Microsoft, Apple)
   - Clipboard monitoring for automatic screenshot detection

3. **Data Flow**:
   - Screenshots → Claude API → Structured time data
   - Calendar APIs → Calendar events → Availability data
   - Combined data → User interface → Selection options → Clipboard

4. **Security & Privacy**:
   - API keys stored in environment variables (.env file)
   - OAuth tokens stored securely
   - Local processing where possible
   - No persistent storage of screenshots

## Development Guidelines

1. **Error Handling**:
   - Graceful degradation when services are unavailable
   - Clear error messages for permission issues
   - Fallback to manual entry when automatic analysis fails

2. **Performance**:
   - Optimize calendar queries to minimize API calls
   - Cache calendar data when appropriate
   - Minimize processing time for screenshots

3. **User Experience**:
   - Minimize clicks required for common tasks
   - Provide clear visual feedback for availability
   - Make copying suggestions to clipboard seamless 