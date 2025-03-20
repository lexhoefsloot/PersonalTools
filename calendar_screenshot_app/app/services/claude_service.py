import os
import json
import base64
import anthropic
from PIL import Image
import io
import logging
import time
import socket
import urllib.request
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_network_connectivity():
    """Check if we can connect to the internet and the Claude API domain"""
    results = []
    
    # Check if we can resolve DNS
    try:
        socket.gethostbyname('api.anthropic.com')
        results.append({"message": "DNS resolution successful for api.anthropic.com", "type": "success"})
    except socket.gaierror:
        results.append({"message": "Failed to resolve api.anthropic.com - DNS issue", "type": "error"})
        return False, results
    
    # Try to connect to the API domain
    try:
        socket.create_connection(('api.anthropic.com', 443), timeout=5)
        results.append({"message": "Network connection successful to Claude API (port 443)", "type": "success"})
    except (socket.timeout, socket.error) as e:
        results.append({"message": f"Failed to connect to Claude API: {str(e)}", "type": "error"})
        results.append({"message": "Check firewall and network settings", "type": "info"})
        return False, results
    
    # Try a simple HTTP request to check if we can reach the service
    try:
        # Use urllib.request with a context manager to ensure proper cleanup
        req = urllib.request.Request('https://api.anthropic.com')
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.status
                results.append({"message": f"HTTP connectivity test successful (status: {status})", "type": "success"})
        except urllib.error.HTTPError as http_err:
            # HTTP errors like 404, 403 mean the server is reachable but returned an error
            # This is actually a success for connectivity testing
            status = http_err.code
            results.append({"message": f"HTTP connectivity test successful (status: {status})", "type": "success"})
            results.append({"message": "Received HTTP error code, but this confirms API is reachable", "type": "info"})
    except urllib.error.URLError as url_err:
        # URL errors indicate network issues
        results.append({"message": f"HTTP connectivity test failed: {str(url_err)}", "type": "error"})
        results.append({"message": "API may be down or blocked by network", "type": "info"})
        return False, results
    except Exception as e:
        # Unexpected errors
        results.append({"message": f"HTTP connectivity test failed with unexpected error: {str(e)}", "type": "error"})
        results.append({"message": "Check network and proxy settings", "type": "info"})
        return False, results
    
    return True, results

def encode_image_to_base64(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()
        logger.info(f"Read image from {image_path}, size: {len(image_data)/1024:.2f} KB")
        return base64.b64encode(image_data).decode('utf-8')

def validate_image(image_path):
    """Validate that the file is a valid image and get basic info"""
    try:
        # Check if file exists
        if not os.path.exists(image_path):
            return {
                "valid": False, 
                "message": "Image file not found", 
                "details": f"Path: {image_path}"
            }
            
        # Check file size
        file_size = os.path.getsize(image_path) / 1024  # KB
        if file_size < 1:  # Less than 1KB
            return {
                "valid": False, 
                "message": "Image file too small", 
                "details": f"Size: {file_size:.2f} KB"
            }
            
        # Try to open the image with PIL
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format = img.format
                mode = img.mode
                
                # Very small images are likely not useful
                if width < 100 or height < 100:
                    return {
                        "valid": False,
                        "message": "Image dimensions too small", 
                        "details": f"Size: {width}x{height} pixels"
                    }
                
                # Return success with image info
                return {
                    "valid": True,
                    "size_kb": file_size,
                    "dimensions": f"{width}x{height}",
                    "format": format,
                    "mode": mode
                }
                
        except Exception as e:
            return {
                "valid": False, 
                "message": "Failed to open image file", 
                "details": str(e)
            }
            
    except Exception as e:
        return {
            "valid": False, 
            "message": "Image validation failed", 
            "details": str(e)
        }

def analyze_screenshot(screenshot_path):
    """Analyze screenshot using Claude API to extract time slots and meeting information"""
    start_time = time.time()
    logger.info(f"Starting screenshot analysis for: {screenshot_path}")
    debug_logs = []

    # Validate the image
    validation_result = validate_image(screenshot_path)
    if validation_result['valid'] is False:
        logger.error(f"Image validation failed: {validation_result['message']}")
        debug_logs.append({"message": f"Image validation failed: {validation_result['message']}", "type": "error"})
        return {
            "success": False,
            "message": validation_result['message'],
            "debug_logs": debug_logs
        }

    # Check network connectivity
    connectivity_success, connectivity_logs = check_network_connectivity()
    debug_logs.extend(connectivity_logs)
    
    if not connectivity_success:
        connectivity_message = connectivity_logs[-1]["message"] if connectivity_logs else "Unknown connectivity issue"
        logger.error(f"Network connectivity check failed: {connectivity_message}")
        return {
            "success": False,
            "message": f"Network connectivity issue: {connectivity_message}. Please check your internet connection.",
            "debug_logs": debug_logs
        }

    try:
        # Get API key from environment
        api_key = os.environ.get('CLAUDE_API_KEY')
        if not api_key:
            logger.error("API key not found in environment variables")
            debug_logs.append({"message": "API key not found in environment variables", "type": "error"})
            return {
                "success": False,
                "message": "Claude API key not found. Please configure your environment variables.",
                "debug_logs": debug_logs
            }
        
        # Log masked API key for debugging
        masked_key = f"{api_key[:5]}...{api_key[-2:]}"
        logger.info(f"API key found (masked: {masked_key})")
        debug_logs.append({"message": f"API key found (masked: {masked_key})", "type": "info"})
        
        # Get image dimensions and details for debugging
        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
                format_name = img.format
                mode = img.mode
                file_size = os.path.getsize(screenshot_path) / 1024  # Size in KB
                image_info = f"Image details: {width}x{height} pixels, {format_name}, {mode}, {file_size:.1f} KB"
                logger.info(image_info)
                debug_logs.append({"message": image_info, "type": "info"})
        except Exception as e:
            logger.warning(f"Could not get image details: {str(e)}")
            debug_logs.append({"message": f"Could not get image details: {str(e)}", "type": "warning"})
        
        # Initialize Anthropic client
        client = anthropic.Anthropic(api_key=api_key)
        logger.info("Anthropic client initialized")
        
        # Encode the image to base64
        b64_image = encode_image_to_base64(screenshot_path)
        logger.info("Image encoded to base64")
        
        # Log the API call attempt
        logger.info("Analyzing with Claude API...")
        debug_logs.append({"message": "Analyzing with Claude API...", "type": "info"})
        
        # Make the API call
        api_start_time = time.time()
        message = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """
This image contains a conversation or calendar screenshot. Please extract ALL date, time, and duration information for potential meeting slots.

Important instructions:
1. Return only a JSON array of time slots
2. Each slot must include date, start time, end time (if available), and timezone (if specified)
3. If multiple time slots are available, include them all as separate objects
4. If multiple dates have the same time slots, create separate entries for each date
5. If the image suggests or requests availability rather than specific times, indicate this in the response 
6. Output only valid JSON with this exact structure

Example response:
{
  "type": "time_slots",
  "slots": [
    {
      "date": "2023-11-15",
      "start_time": "10:00",
      "end_time": "11:00", 
      "timezone": "EST",
      "is_suggested": true
    },
    {
      "date": "2023-11-16",
      "start_time": "14:30",
      "end_time": "15:30",
      "timezone": "EST",
      "is_suggested": true
    }
  ]
}

For availability requests, use:
{
  "type": "availability_request",
  "message": "Requesting availability for Thursday or Friday afternoon"
}

Respond ONLY with the JSON. No explanations or conversation."
                            """
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_image
                            }
                        }
                    ]
                }
            ]
        )
        api_end_time = time.time()
        api_duration = api_end_time - api_start_time
        
        # Log API response time
        logger.info(f"Claude API response received in {api_duration:.2f} seconds")
        debug_logs.append({"message": f"Claude API response received in {api_duration:.2f} seconds", "type": "info"})
        
        # For debugging purpose, log the full response content
        logger.debug(f"Full Claude response: {message.content}")
        debug_logs.append({"message": f"Raw Claude response: {message.content}", "type": "debug"})
        
        # Parse the response
        try:
            # Extract content from the message object
            content = message.content
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].text
            else:
                text_content = str(content)
            
            # Look for JSON in the response
            json_match = re.search(r'({[\s\S]*})', text_content)
            if json_match:
                json_str = json_match.group(1)
                logger.info(f"JSON found in Claude response: {json_str}")
                debug_logs.append({"message": f"Extracted JSON: {json_str}", "type": "info"})
                result = json.loads(json_str)
            else:
                logger.warning("No JSON found in Claude response")
                debug_logs.append({"message": "No JSON found in Claude response. Raw text: " + text_content[:100] + "...", "type": "warning"})
                result = {"type": "error", "message": "Failed to parse time slots from Claude response"}
            
            # Process the result
            if result.get("type") == "time_slots" and len(result.get("slots", [])) > 0:
                slots_count = len(result.get("slots", []))
                logger.info(f"Successfully extracted {slots_count} time slots from image")
                debug_logs.append({"message": f"Successfully extracted {slots_count} time slots from image", "type": "success"})
                return {
                    "success": True,
                    "time_slots": result.get("slots", []),
                    "is_suggestion": True,
                    "debug_logs": debug_logs
                }
            elif result.get("type") == "availability_request":
                logger.info("Detected availability request rather than specific time slots")
                debug_logs.append({"message": "Detected availability request rather than specific time slots", "type": "info"})
                return {
                    "success": True,
                    "message": result.get("message", "Availability request detected"),
                    "type": "availability_request",
                    "time_slots": [],
                    "is_suggestion": False,
                    "debug_logs": debug_logs
                }
            else:
                logger.warning("Claude AI couldn't find any time slots in this image")
                debug_logs.append({"message": "Claude AI couldn't find any time slots in this image", "type": "warning"})
                return {
                    "success": False,
                    "message": "Claude AI couldn't find any time slots in this image\nTry a clearer screenshot or ensure the image contains time information",
                    "debug_logs": debug_logs
                }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Claude response: {e}")
            logger.debug(f"Response content that failed parsing: {text_content}")
            debug_logs.append({"message": f"Failed to parse JSON from Claude response: {e}", "type": "error"})
            debug_logs.append({"message": f"Raw response: {text_content[:200]}...", "type": "debug"})
            return {
                "success": False,
                "message": "Error parsing Claude API response. Please try again with a clearer image.",
                "debug_logs": debug_logs
            }
    except Exception as e:
        logger.error(f"Error during Claude API analysis: {str(e)}")
        debug_logs.append({"message": f"Error during Claude API analysis: {str(e)}", "type": "error"})
        return {
            "success": False,
            "message": f"Error analyzing screenshot: {str(e)}",
            "debug_logs": debug_logs
        }
    finally:
        total_time = time.time() - start_time
        logger.info(f"Total analysis time: {total_time:.2f} seconds")
        debug_logs.append({"message": f"Total analysis time: {total_time:.2f} seconds", "type": "info"}) 