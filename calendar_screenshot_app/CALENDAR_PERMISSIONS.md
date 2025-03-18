# Calendar Permissions Guide

## The Problem

The application needs permission to access your Apple Calendar, but Terminal or Python cannot always properly trigger the permission dialog.

## Solution Options

### Option 1: Grant Permission Manually

1. Open **System Preferences** 
2. Go to **Security & Privacy** → **Privacy** → **Automation**
3. Find **Terminal** in the list
4. Check the box next to **Calendar**

If the box is greyed out or you can't check it:

### Option 2: Try the Simple Permission Script

1. Open Terminal
2. Run: `cd ~/PersonalTools/calendar_screenshot_app && python3 force_permission.py`
3. When the permission dialog appears, click **OK**

### Option 3: Create a Simple macOS App

If the above methods don't work, we can create a simple macOS app to properly request Calendar permissions:

1. Open **Script Editor** (you can find it with Spotlight Search)
2. Paste this code:
```applescript
tell application "Calendar"
    get name of calendars
end tell
```
3. Save as an application (File → Export → File Format: Application)
4. Run the app you just created - it will ask for Calendar permissions
5. Grant the permission

### Option 4: Use Another Calendar Provider

As an alternative, you can:
1. Use Google Calendar integration instead
2. Click the "Connect Google Calendar" button on the app's calendar page

## After Granting Permission

Once permission is granted:
1. Restart the Flask application
2. Navigate to the Manage Calendars page 