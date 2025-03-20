from flask import Flask, render_template, session
import os
import platform
from datetime import datetime
import glob

def create_app(test_config=None):
    # Create and configure the app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        GOOGLE_CLIENT_ID=os.environ.get('GOOGLE_CLIENT_ID', ''),
        GOOGLE_CLIENT_SECRET=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        MICROSOFT_CLIENT_ID=os.environ.get('MICROSOFT_CLIENT_ID', ''),
        MICROSOFT_CLIENT_SECRET=os.environ.get('MICROSOFT_CLIENT_SECRET', ''),
        MICROSOFT_REDIRECT_URI=os.environ.get('MICROSOFT_REDIRECT_URI', ''),
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Register blueprints
    from app.routes import auth_routes, calendar_routes, screenshot_routes

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(calendar_routes.bp)
    app.register_blueprint(screenshot_routes.bp)

    # Add context processor to inject platform info and current time
    @app.context_processor
    def inject_platform_and_now():
        return {
            'platform': platform,
            'now': datetime.now()
        }

    # Homepage route
    @app.route('/')
    def index():
        # Check if running on macOS for Apple Calendar availability
        is_macos = platform.system() == 'Darwin'
        
        # Check for Thunderbird calendar availability
        is_thunderbird_available = False
        thunderbird_profile_paths = [
            os.path.expanduser("~/.thunderbird/*/"),
            os.path.expanduser("~/.icedove/*/"),  # Debian's fork of Thunderbird
            os.path.expanduser("~/.mozilla-thunderbird/*/"),  # Older versions
            os.path.expanduser("~/.local/share/thunderbird/*/"),
            os.path.expanduser("~/Library/Thunderbird/Profiles/*/")  # macOS
        ]
        
        for path_pattern in thunderbird_profile_paths:
            profiles = glob.glob(path_pattern)
            for profile in profiles:
                if os.path.exists(os.path.join(profile, "calendar-data")):
                    is_thunderbird_available = True
                    break
        
        # Check authentication status for different providers
        google_connected = 'google_token' in session
        microsoft_connected = 'microsoft_token' in session
        
        return render_template('index.html',
                               using_apple_calendar=is_macos,
                               using_thunderbird=is_thunderbird_available,
                               google_connected=google_connected,
                               microsoft_connected=microsoft_connected,
                               authenticated=google_connected or microsoft_connected or is_macos or is_thunderbird_available)

    return app
