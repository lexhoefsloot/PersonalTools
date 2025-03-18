import os
import json
from flask import Blueprint, redirect, url_for, session, request, render_template
from app.services.google_calendar import get_google_auth_url, get_google_token
from app.services.microsoft_calendar import get_microsoft_auth_url, get_microsoft_token

bp = Blueprint('auth', __name__, url_prefix='/auth')

@bp.route('/google/authorize')
def google_authorize():
    """Start Google OAuth flow"""
    auth_url = get_google_auth_url()
    return redirect(auth_url)

@bp.route('/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    code = request.args.get('code')
    if not code:
        return render_template('error.html', error="Authentication failed: No code received from Google"), 400
    
    token_info = get_google_token(code)
    if not token_info:
        return render_template('error.html', error="Failed to get token from Google"), 400
    
    # Store token in session
    session['google_token'] = token_info
    
    return redirect(url_for('index'))

@bp.route('/microsoft/authorize')
def microsoft_authorize():
    """Start Microsoft OAuth flow"""
    auth_url = get_microsoft_auth_url()
    return redirect(auth_url)

@bp.route('/microsoft/callback')
def microsoft_callback():
    """Handle Microsoft OAuth callback"""
    code = request.args.get('code')
    if not code:
        return render_template('error.html', error="Authentication failed: No code received from Microsoft"), 400
    
    token_info = get_microsoft_token(code)
    if not token_info:
        return render_template('error.html', error="Failed to get token from Microsoft"), 400
    
    # Store token in session
    session['microsoft_token'] = token_info
    
    return redirect(url_for('index'))

@bp.route('/logout')
def logout():
    """Log out and clear session"""
    session.clear()
    return redirect(url_for('index')) 