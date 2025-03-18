import os
from flask import Flask, render_template, session, redirect, url_for, flash
from dotenv import load_dotenv
from app.routes import auth_routes, calendar_routes, screenshot_routes
from app.services.clipboard_monitor import start_clipboard_monitor_thread
import platform

# Load environment variables
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-key-for-testing')
    
    # Register blueprints
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(calendar_routes.bp)
    app.register_blueprint(screenshot_routes.bp)
    
    @app.route('/')
    def index():
        # Check if using macOS for Apple Calendar
        using_apple_calendar = platform.system() == 'Darwin'
        
        # Check if user has selected calendars
        has_selected_calendars = 'selected_calendars' in session and len(session['selected_calendars']) > 0
        
        # If no calendars selected and running on macOS, redirect to calendar selection
        if not has_selected_calendars and using_apple_calendar:
            flash('Please select which calendars to use for availability checking', 'info')
            return redirect(url_for('calendar.list_calendars'))
        
        # If not on macOS and not authenticated with any service
        if not using_apple_calendar and 'google_token' not in session and 'microsoft_token' not in session:
            return render_template('index.html', 
                                  authenticated=False,
                                  using_apple_calendar=False)
        
        return render_template('dashboard.html', 
                              google_connected='google_token' in session,
                              microsoft_connected='microsoft_token' in session,
                              apple_connected=using_apple_calendar)
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('error.html', error=str(e)), 404
    
    @app.errorhandler(500)
    def server_error(e):
        return render_template('error.html', error=str(e)), 500
    
    return app

def main():
    app = create_app()
    
    # Start clipboard monitoring in a background thread
    start_clipboard_monitor_thread()
    
    # Print a friendly message about using Apple Calendar
    if platform.system() == 'Darwin':
        print("\n🍎 Apple Calendar integration is enabled. You can use your existing calendars.")
    else:
        print("\n⚠️ Apple Calendar integration is unavailable. You need to connect to Google or Microsoft Calendar.")
    
    app.run(debug=os.environ.get('FLASK_ENV') == 'development', 
            host='0.0.0.0', 
            port=int(os.environ.get('PORT', 5000)))

if __name__ == '__main__':
    main() 