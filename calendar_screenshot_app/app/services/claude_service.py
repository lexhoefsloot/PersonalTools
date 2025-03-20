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
        response = urllib.request.urlopen('https://api.anthropic.com', timeout=5)
        if response.status == 404:  # Expected response for path /
            results.append({"message": "HTTP connectivity test successful", "type": "success"})
        else:
            results.append({"message": f"Unexpected HTTP response: {response.status}", "type": "warning"})
    except Exception as e:
        results.append({"message": f"HTTP connectivity test failed: {str(e)}", "type": "error"})
        results.append({"message": "API may be down or blocked by network", "type": "info"})
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
            return False, {"error": "Image file not found", "details": f"Path: {image_path}"}
            
        # Check file size
        file_size = os.path.getsize(image_path) / 1024  # KB
        if file_size < 1:  # Less than 1KB
            return False, {"error": "Image file too small", "details": f"Size: {file_size:.2f} KB"}
            
        # Try to open the image with PIL
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                format = img.format
                mode = img.mode
                
                # Very small images are likely not useful
                if width < 100 or height < 100:
                    return False, {
                        "error": "Image dimensions too small", 
                        "details": f"Size: {width}x{height} pixels"
                    }
                
                # Return success with image info
                return True, {
                    "size_kb": file_size,
                    "dimensions": f"{width}x{height}",
                    "format": format,
                    "mode": mode
                }
                
        except Exception as e:
            return False, {"error": "Failed to open image file", "details": str(e)}
            
    except Exception as e:
        return False, {"error": "Image validation failed", "details": str(e)}

def analyze_screenshot(screenshot_path):
    """Analyze screenshot with Claude API to extract meeting time information"""
    try:
        logger.info(f"Starting Claude API analysis for screenshot: {screenshot_path}")
        start_time = time.time()
        
        # Validate image first
        is_valid, image_info = validate_image(screenshot_path)
        if not is_valid:
            logger.error(f"Invalid image: {image_info['error']} - {image_info['details']}")
            return {
                "error": f"Invalid image: {image_info['error']}",
                "analysis": f"Could not analyze the image: {image_info['details']}",
                "time_slots": [],
                "debug_logs": [
                    {"message": f"Invalid image: {image_info['error']}", "type": "error"},
                    {"message": f"Details: {image_info['details']}", "type": "error"},
                    {"message": "Please ensure you're uploading a valid screenshot with visible text", "type": "info"}
                ]
            }
            
        logger.info(f"Image validated: {image_info.get('dimensions', 'unknown size')}, {image_info.get('format', 'unknown format')}")
        
        # Check network connectivity
        connectivity_ok, connectivity_logs = check_network_connectivity()
        if not connectivity_ok:
            logger.error("Network connectivity issues detected")
            return {
                "error": "Network connectivity issues",
                "analysis": "Could not connect to Claude API due to network issues",
                "time_slots": [],
                "debug_logs": connectivity_logs + [
                    {"message": "API request aborted due to connectivity issues", "type": "error"},
                    {"message": "Check your internet connection and try again", "type": "info"}
                ]
            }
        
        # Get API key from environment variables
        api_key = os.environ.get('CLAUDE_API_KEY')
        if not api_key:
            logger.error("Claude API key not found in environment variables")
            return {
                "error": "API key not configured",
                "analysis": "The Claude API key is missing from environment variables.",
                "time_slots": [],
                "debug_logs": [
                    {"message": "Claude API key not found in environment variables", "type": "error"},
                    {"message": "Check that the CLAUDE_API_KEY environment variable is set correctly", "type": "info"},
                    {"message": "API key should be a secret string from your Anthropic account", "type": "info"}
                ]
            }
        else:
            # Validate API key format (basic check)
            if not api_key.startswith(('sk-', 'anthropic-')):
                logger.error("Claude API key has invalid format")
                return {
                    "error": "API key format invalid",
                    "analysis": "The Claude API key doesn't have the expected format.",
                    "time_slots": [],
                    "debug_logs": [
                        {"message": "Claude API key has invalid format", "type": "error"},
                        {"message": "API key should start with 'sk-' or 'anthropic-'", "type": "info"},
                        {"message": "Check that you're using the correct API key from Anthropic", "type": "info"}
                    ]
                }
            
            logger.info("Claude API key found")
        
        # Initialize Claude client
        try:
            client = anthropic.Anthropic(
                api_key=api_key,
            )
            logger.info("Claude client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Claude client: {str(e)}")
            return {
                "error": "Failed to initialize Claude client",
                "analysis": f"Error: {str(e)}",
                "time_slots": [],
                "debug_logs": [
                    {"message": f"Failed to initialize Claude client: {str(e)}", "type": "error"},
                    {"message": "Check your API key and internet connection", "type": "info"}
                ]
            }
        
        # Prepare image for Claude
        logger.info("Encoding image to base64...")
        base64_image = encode_image_to_base64(screenshot_path)
        logger.info(f"Image encoded, base64 length: {len(base64_image)} characters")
        
        # Create enhanced system prompt for Claude
        system_prompt = """
        You are a calendar assistant that analyzes screenshots of conversations to identify meeting time suggestions or requests.
        
        TASK:
        1. Determine whether the screenshot shows:
           a) Someone SUGGESTING specific times for a meeting, or
           b) Someone REQUESTING time suggestions from the recipient
        
        2. Extract ALL mentioned time slots with high precision, including:
           - Specific times (e.g., "3pm", "15:00", "morning")
           - Dates (e.g., "next Monday", "March 15th", "tomorrow")
           - Durations (e.g., "30 minutes", "1 hour")
           - Time ranges (e.g., "between 2-4pm", "anytime Wednesday")
        
        3. For each time slot, capture contextual information:
           - Is this a preferred/priority time?
           - Is this an alternative suggestion?
           - Any constraints mentioned (e.g., "if that works for you", "I'm flexible")
        
        4. Infer the most likely date if none is explicitly mentioned, based on context.
           - Use the current date as reference if needed
           - Look for day references without dates (e.g., "Monday" likely means the next upcoming Monday)
        
        OUTPUT FORMAT:
        Return a JSON object with the following structure:
        {
            "is_suggestion": true/false, (true if suggesting times, false if requesting times)
            "time_slots": [
                {
                    "start": "YYYY-MM-DD HH:MM", (ISO format with 24-hour time)
                    "end": "YYYY-MM-DD HH:MM", (ISO format, include if duration/end time is mentioned)
                    "duration_minutes": 30, (if duration is mentioned, converted to minutes)
                    "priority": 1, (1=highest priority, 2=alternative, 3=backup, etc.)
                    "context": "string with any relevant context about this time slot"
                }
            ],
            "confidence": 0.9, (0.0-1.0 scale of how confident you are in your analysis)
            "analysis": "Brief natural language explanation of what you detected and any ambiguities"
        }
        
        If no time information is found, return an empty time_slots array with an appropriate analysis.
        """
        logger.info("System prompt prepared")
        
        # Define user message with the screenshot
        user_message = "Please analyze this conversation screenshot and extract any meeting time information. Identify whether someone is suggesting times or requesting times, and extract all time slots mentioned with their contextual information."
        
        # Log API request details
        logger.info(f"Sending request to Claude API (model: claude-3-sonnet-20240229)")
        logger.info(f"User message: {user_message}")
        api_call_start = time.time()
        
        # Create message with the exact format from documentation
        try:
            message = client.messages.create(
                model="claude-3-sonnet-20240229",  # Using an available model
                max_tokens=1500,
                system=system_prompt,
                messages=[
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": user_message},
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64_image}}
                        ]
                    }
                ]
            )
            
            # Log API response time and basic info
            api_call_duration = time.time() - api_call_start
            logger.info(f"Claude API response received in {api_call_duration:.2f} seconds")
            
        except anthropic.APIError as e:
            # Handle API errors from Claude
            api_call_duration = time.time() - api_call_start
            logger.error(f"Claude API error: {str(e)}")
            error_details = f"Status: {getattr(e, 'status_code', 'unknown')}, Type: {type(e).__name__}"
            
            # Determine more specific error based on error type
            error_message = "Claude API request failed"
            suggestion = "Check your API key and account status"
            
            if hasattr(e, 'status_code'):
                if e.status_code == 401:
                    error_message = "Authentication failed (401)"
                    suggestion = "Your API key is invalid or expired"
                elif e.status_code == 403:
                    error_message = "Permission denied (403)"
                    suggestion = "Your account doesn't have permission to use this model"
                elif e.status_code == 429:
                    error_message = "Rate limit exceeded (429)"
                    suggestion = "You've exceeded your API quota or rate limits"
                elif e.status_code >= 500:
                    error_message = f"Claude API server error ({e.status_code})"
                    suggestion = "This is a problem with Claude's servers, try again later"
            
            return {
                "error": error_message,
                "analysis": f"API Error: {str(e)}",
                "time_slots": [],
                "debug_logs": [
                    {"message": error_message, "type": "error"},
                    {"message": f"Details: {error_details}", "type": "error"},
                    {"message": f"Response time: {api_call_duration:.2f} seconds", "type": "info"},
                    {"message": suggestion, "type": "info"},
                    {"message": "Visit https://status.anthropic.com to check API status", "type": "info"}
                ]
            }
            
        except Exception as e:
            # Handle other exceptions during API call
            api_call_duration = time.time() - api_call_start
            logger.error(f"Exception during Claude API call: {str(e)}", exc_info=True)
            return {
                "error": "Failed to communicate with Claude API",
                "analysis": f"Error: {str(e)}",
                "time_slots": [],
                "debug_logs": [
                    {"message": f"Failed to communicate with Claude API: {str(e)}", "type": "error"},
                    {"message": f"Error type: {type(e).__name__}", "type": "error"},
                    {"message": f"Response time: {api_call_duration:.2f} seconds", "type": "info"},
                    {"message": "Check your internet connection and firewall settings", "type": "info"}
                ]
            }
        
        # Extract response text as shown in documentation
        try:
            response_text = message.content[0].text
        except (IndexError, AttributeError) as e:
            logger.error(f"Error accessing API response content: {str(e)}")
            return {
                "error": "Invalid API response format",
                "analysis": "Claude API returned an unexpected response format",
                "time_slots": [],
                "debug_logs": [
                    {"message": f"Error accessing API response content: {str(e)}", "type": "error"},
                    {"message": f"Response structure may have changed: {str(message)[:200]}", "type": "info"},
                    {"message": "Check for Anthropic API updates or changes", "type": "info"}
                ]
            }
        
        # Log the first part of the response
        response_preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
        logger.info(f"Claude API response preview: {response_preview}")
        
        # Try to extract JSON from the response
        try:
            # Look for JSON block in the response
            if "```json" in response_text:
                logger.info("Found JSON block with markers in response")
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                logger.info("Found generic code block in response")
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                logger.info("No code block markers, treating entire response as JSON")
                json_str = response_text.strip()
            
            logger.info(f"Attempting to parse JSON response of length {len(json_str)}")
            result = json.loads(json_str)
            
            # Log the parsed result
            time_slots_count = len(result.get("time_slots", []))
            logger.info(f"Successfully parsed JSON response with {time_slots_count} time slots")
            logger.info(f"is_suggestion: {result.get('is_suggestion')}")
            logger.info(f"confidence: {result.get('confidence')}")
            logger.info(f"Analysis: {result.get('analysis', '')[:100]}...")
            
            # Log total time taken
            total_duration = time.time() - start_time
            logger.info(f"Total screenshot analysis completed in {total_duration:.2f} seconds")
            
            # Add debug logs to result for troubleshooting
            if 'debug_logs' not in result:
                result['debug_logs'] = []
                
            # Add image info to the result for reference
            result['debug_logs'].extend([
                {"message": f"Claude API analysis completed in {total_duration:.2f} seconds", "type": "info"},
                {"message": f"Detected {time_slots_count} time slots with {result.get('confidence', 0):.2f} confidence", "type": "info"},
                {"message": f"Image details: {image_info.get('dimensions', 'unknown')}, {image_info.get('format', 'unknown')}, {image_info.get('size_kb', 0):.1f} KB", "type": "info"}
            ])
            
            # Add warning if no time slots were detected
            if time_slots_count == 0:
                logger.warning("Claude detected no time slots in the image")
                
                # Add more detailed explanation based on Claude's analysis
                explanation = result.get('analysis', 'No details provided')
                
                result['debug_logs'].extend([
                    {"message": "Claude AI couldn't detect any time slots in this image", "type": "warning"},
                    {"message": f"Claude's analysis: {explanation}", "type": "info"},
                    {"message": "Check if the image contains visible time information", "type": "info"},
                    {"message": "Try a screenshot that clearly shows dates, times, or calendar information", "type": "info"},
                    {"message": f"Image size: {os.path.getsize(screenshot_path)/1024:.1f} KB", "type": "info"}
                ])
            
            return result
        
        except json.JSONDecodeError as e:
            # Log JSON parsing error
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Raw response that couldn't be parsed: {response_text}")
            return {
                "error": "Failed to parse Claude API response",
                "analysis": "The API response could not be parsed as valid JSON.",
                "debug_logs": [
                    {"message": f"JSON decode error: {e}", "type": "error"},
                    {"message": "Claude returned a response that couldn't be parsed as valid JSON", "type": "error"},
                    {"message": f"Response preview: {response_text[:200]}...", "type": "info"}
                ]
            }
            
    except Exception as e:
        # Log any other errors
        logger.error(f"Error in analyze_screenshot: {str(e)}", exc_info=True)
        return {
            "error": f"Error analyzing screenshot: {str(e)}",
            "analysis": "An error occurred while analyzing the screenshot with Claude API.",
            "debug_logs": [
                {"message": f"Error in Claude analysis: {str(e)}", "type": "error"},
                {"message": "Check server logs for more detailed information", "type": "info"}
            ]
        } 