import os
import time
import threading
import base64
import io
import json
import requests
from PIL import Image, ImageGrab
import pyperclip

# Global variable to track if the monitor thread is running
monitor_thread = None
is_monitoring = False

def start_clipboard_monitor_thread():
    """Start clipboard monitoring in a background thread"""
    global monitor_thread, is_monitoring
    
    if monitor_thread is not None and monitor_thread.is_alive():
        print("Clipboard monitor thread is already running")
        return
    
    is_monitoring = True
    monitor_thread = threading.Thread(target=monitor_clipboard, daemon=True)
    monitor_thread.start()
    print("Clipboard monitor thread started")

def stop_clipboard_monitor_thread():
    """Stop clipboard monitoring thread"""
    global is_monitoring
    is_monitoring = False
    print("Clipboard monitor thread stopping")

def monitor_clipboard():
    """Monitor clipboard for screenshots and send them for analysis"""
    global is_monitoring
    
    # Keep track of last image hash to avoid processing the same image multiple times
    last_image_hash = None
    
    while is_monitoring:
        try:
            # Try to get image from clipboard
            img = ImageGrab.grabclipboard()
            
            # Check if clipboard contains an image
            if img is not None and isinstance(img, Image.Image):
                # Generate a simple hash of the image to detect changes
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG')
                img_hash = hash(img_bytes.getvalue())
                
                # Process only if this is a new image
                if img_hash != last_image_hash:
                    last_image_hash = img_hash
                    
                    # Convert image to base64 for sending to API
                    img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
                    
                    # Send to our own API endpoint
                    try:
                        response = requests.post(
                            'http://localhost:5000/screenshot/analyze',
                            json={'screenshot_data': f"data:image/png;base64,{img_base64}"},
                            headers={'Content-Type': 'application/json'}
                        )
                        
                        # TODO: Display results in UI or notification
                        if response.status_code == 200:
                            print("Screenshot analysis completed")
                            # In a real app, this would trigger UI updates
                    
                    except requests.RequestException as e:
                        print(f"Error sending screenshot to API: {str(e)}")
            
            # Sleep before checking clipboard again
            time.sleep(1)
        
        except Exception as e:
            print(f"Error monitoring clipboard: {str(e)}")
            time.sleep(5)  # Longer sleep on error
    
    print("Clipboard monitor thread stopped") 