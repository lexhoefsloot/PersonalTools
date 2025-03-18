# Personal Tools

A collection of useful tools and utilities for personal productivity.

## Projects

### Calendar Screenshot Analyzer

A Python web application that analyzes screenshots of conversations to extract meeting time suggestions and check availability against your calendars.

#### Features

- **Multi-Calendar Integration**: Connect with Google Calendar, Microsoft Office 365, and Apple Calendar (macOS only)
- **Screenshot Analysis**: Automatically detect date and time patterns in images
- **Availability Checking**: Check suggested times against your connected calendars
- **Platform Integration**: Automatic Apple Calendar detection on macOS without authentication
- **Clipboard Analysis**: Direct analysis from clipboard screenshots

#### Installation

1. Clone the repository
2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r calendar_screenshot_app/requirements.txt
   ```
3. Configure your environment variables
4. Run the application:
   ```bash
   cd calendar_screenshot_app
   python3 run.py
   ```

See the [Calendar Screenshot Analyzer README](calendar_screenshot_app/README.md) for more detailed instructions.

## License

MIT 