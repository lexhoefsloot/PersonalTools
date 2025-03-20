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
from datetime import datetime, timedelta
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_network_connectivity():
    """
    Check if we can connect to the Anthropic API.
    
    Returns:
        dict: Result containing:
            - success (bool): Whether the connectivity check was successful
            - message (str): Information about the successful connection
            - error (str): Error message in case of failure
    """
    try:
        # First check for general internet connectivity
        urllib.request.urlopen("https://www.google.com", timeout=5)
        
        # Then check for Anthropic API connectivity (just DNS resolution, not actual auth)
        # We don't need to check the full API endpoint, just the domain
        response = requests.head("https://api.anthropic.com", timeout=5)
        
        # HTTP codes like 404 and 403 are actually good responses here
        # They mean we can reach the server, even if we don't have permission
        if response.status_code in [200, 403, 404]:
            return {
                "success": True,
                "message": f"Successfully connected to Anthropic API (status: {response.status_code})",
                "error": None
            }
        else:
            return {
                "success": False,
                "message": None,
                "error": f"Received unexpected status code from Anthropic API: {response.status_code}"
            }
            
    except urllib.error.URLError as e:
        return {
            "success": False,
            "message": None,
            "error": f"General internet connectivity issue: {str(e)}"
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": None,
            "error": f"Cannot connect to Anthropic API: {str(e)}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": None,
            "error": f"Unexpected error during connectivity check: {str(e)}"
        }

def encode_image_to_base64(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()
        logger.info(f"Read image from {image_path}, size: {len(image_data)/1024:.2f} KB")
        return base64.b64encode(image_data).decode('utf-8')

def validate_image(image_data):
    """
    Validate that the image data is suitable for analysis.
    
    Args:
        image_data (bytes): The image data to validate.
        
    Returns:
        dict: Validation result with keys:
            - valid (bool): Whether the image is valid
            - format (str): Image format if valid
            - size (int): Size in bytes if valid
            - reason (str): Reason for validation failure if not valid
    """
    try:
        # Try to open the image from bytes
        image = Image.open(io.BytesIO(image_data))
        
        # Check if the image was opened correctly
        image.verify()
        
        # Get image format and size
        image = Image.open(io.BytesIO(image_data))
        image_format = image.format
        width, height = image.size
        size_bytes = len(image_data)
        
        # Check for empty images or unreasonably small/large images
        if width < 50 or height < 50:
            return {
                "valid": False,
                "reason": f"Image too small: {width}x{height} pixels"
            }
            
        if size_bytes < 1000:
            return {
                "valid": False,
                "reason": f"Image file too small: {size_bytes} bytes"
            }
            
        if size_bytes > 10 * 1024 * 1024:  # 10 MB
            return {
                "valid": False,
                "reason": f"Image file too large: {size_bytes} bytes (max 10MB)"
            }
            
        # All checks passed
        return {
            "valid": True,
            "format": image_format,
            "size": size_bytes,
            "dimensions": f"{width}x{height}"
        }
        
    except Exception as e:
        return {
            "valid": False,
            "reason": f"Invalid image: {str(e)}"
        }

def analyze_screenshot(image_data, debug_logs=None):
    """
    Analyze a calendar screenshot using the Claude API.
    
    Args:
        image_data (bytes): The image data to analyze.
        debug_logs (list, optional): List to append debug logs to.
        
    Returns:
        dict: The analysis results.
    """
    if debug_logs is None:
        debug_logs = []
    
    debug_logs.append({
        "message": f"Starting screenshot analysis",
        "type": "info"
    })
    
    try:
        # Check if image data is valid
        validation_result = validate_image(image_data)
        if not validation_result["valid"]:
            debug_logs.append({
                "message": f"Image validation failed: {validation_result['reason']}",
                "type": "error"
            })
            return {
                "success": False,
                "error": f"Invalid image: {validation_result['reason']}",
                "debug_logs": debug_logs
            }
        
        debug_logs.append({
            "message": f"Image validated successfully. Format: {validation_result['format']}, Size: {validation_result['size']} bytes",
            "type": "info"
        })
        
        # Check network connectivity
        connectivity = check_network_connectivity()
        if not connectivity["success"]:
            debug_logs.append({
                "message": f"Network connectivity check failed: {connectivity['error']}",
                "type": "error"
            })
            return {
                "success": False,
                "error": f"Network error: {connectivity['error']}",
                "debug_logs": debug_logs
            }
        
        debug_logs.append({
            "message": f"Network connectivity confirmed: {connectivity['message']}",
            "type": "info"
        })
        
        # Get API key
        api_key = os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            debug_logs.append({
                "message": "Claude API key not found in environment variables",
                "type": "error"
            })
            return {
                "success": False,
                "error": "API key not configured",
                "debug_logs": debug_logs
            }
        
        # Validate API key format
        if not api_key.startswith("sk-"):
            debug_logs.append({
                "message": "Invalid API key format (should start with 'sk-')",
                "type": "error"
            })
            return {
                "success": False,
                "error": "Invalid API key format",
                "debug_logs": debug_logs
            }
        
        debug_logs.append({
            "message": "API key validated (format check only)",
            "type": "info"
        })
        
        debug_logs.append({
            "message": "Creating Anthropic client",
            "type": "info"
        })
        
        client = anthropic.Anthropic(
            api_key=api_key
        )
        
        # Encode image to base64
        image_base64 = base64.b64encode(image_data).decode("utf-8")
        
        debug_logs.append({
            "message": f"Image encoded to base64 (length: {len(image_base64)} chars)",
            "type": "info"
        })
        
        # Define system prompt
        system_prompt = """You are a helpful calendar assistant that analyzes calendar screenshots. 
        Your task is to carefully extract time slots from calendar screenshots, checking if they are available or if they conflict with existing events.
        Identify if the screenshot is showing a time suggestion or a time request from the user.
        For suggestions, note whether the time slots are available or unavailable.
        For requests, provide all relevant time slots mentioned.
        
        Respond with a JSON object that includes:
        1. analysis - Brief text summarization of what the screenshot shows
        2. is_suggestion - Boolean indicating if it's a suggestion (true) or request (false)
        3. time_slots - Array of objects, each with:
           - start_time: ISO datetime
           - end_time: ISO datetime
           - available: Boolean indicating if the slot is available
           - context: Any relevant context about this time slot
           - conflicts: Array of conflicting events if unavailable
        
        Format dates in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Be accurate with all times."""
        
        # Define the prompt text
        prompt_text = "Please analyze this calendar screenshot and extract all available and unavailable time slots. Focus on identifying whether this is a suggested time or a request for available times."
        
        # Create message content
        message_content = [
            {
                "type": "text",
                "text": prompt_text
            },
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_base64
                }
            }
        ]
        
        # Log the API request details (truncating the base64 image for brevity)
        debug_request = {
            "model": "claude-3-5-sonnet-20240620",
            "max_tokens": 4000,
            "prompt": prompt_text,
            "image_data": image_base64[:100] + "..." + image_base64[-100:] # Truncated for logs
        }
        
        # Print the request details to the console
        print("===== CLAUDE API REQUEST =====")
        print(f"MODEL: claude-3-5-sonnet-20240620")
        print(f"MAX TOKENS: 4000")
        print(f"PROMPT: {prompt_text}")
        print(f"SYSTEM PROMPT: {system_prompt[:100]}...")
        print(f"IMAGE: Base64 data of {len(image_base64)} chars")
        print("==============================")
        
        debug_logs.append({
            "message": "Sending request to Claude API",
            "type": "info"
        })
        
        # Log start time
        start_time = time.time()
        
        # Call Claude API
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=4000,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": message_content
                    }
                ]
            )
            
            # Calculate response time
            response_time = time.time() - start_time
            
            # Print the full response details
            print("===== CLAUDE API RESPONSE =====")
            print(f"RESPONSE TIME: {response_time:.2f} seconds")
            print(f"CONTENT TYPE: {type(response.content)}")
            print(f"FULL CONTENT: {response.content}")
            print(f"STOP REASON: {response.stop_reason}")
            print(f"STOP SEQUENCE: {response.stop_sequence}")
            print(f"MODEL: {response.model}")
            print(f"USAGE: {response.usage}")
            print("===============================")
            
            debug_logs.append({
                "message": f"Received response from Claude API (took {response_time:.2f}s)",
                "type": "info"
            })
            
            # Save raw response for debugging
            debug_logs.append({
                "message": f"Raw Claude response: {response.content}",
                "type": "debug"
            })
            
            # Extract the text content from response
            content = response.content[0].text
            
            debug_logs.append({
                "message": "Parsing JSON response",
                "type": "info"
            })
            
            # Try to parse JSON from the content
            try:
                # Find JSON in the response
                json_match = re.search(r'```json(.*?)```', content, re.DOTALL)
                
                if json_match:
                    json_content = json_match.group(1).strip()
                    result = json.loads(json_content)
                    debug_logs.append({
                        "message": "JSON successfully parsed from Claude response",
                        "type": "info"
                    })
                else:
                    # If no JSON block found, try to parse the entire content
                    content = content.strip()
                    if content.startswith('{') and content.endswith('}'):
                        result = json.loads(content)
                        debug_logs.append({
                            "message": "JSON successfully parsed from direct content",
                            "type": "info"
                        })
                    else:
                        # No parseable JSON
                        debug_logs.append({
                            "message": "No JSON found in Claude response",
                            "type": "error"
                        })
                        debug_logs.append({
                            "message": f"Response content: {content[:200]}...",
                            "type": "debug"
                        })
                        return {
                            "success": False,
                            "error": "Failed to parse analysis results",
                            "analysis": "The AI was unable to analyze the calendar screenshot correctly.",
                            "debug_logs": debug_logs
                        }
                
                # Process time slots if present
                if "time_slots" in result:
                    for slot in result["time_slots"]:
                        # Convert ISO strings to datetime objects
                        try:
                            slot["start_time"] = datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
                            slot["end_time"] = datetime.fromisoformat(slot["end_time"].replace("Z", "+00:00"))
                        except ValueError as e:
                            debug_logs.append({
                                "message": f"Error parsing datetime: {str(e)}",
                                "type": "error"
                            })
                            # Set default values if parsing fails
                            slot["start_time"] = datetime.now()
                            slot["end_time"] = datetime.now() + timedelta(hours=1)
                        
                        # Ensure conflicts is always a list
                        if "conflicts" not in slot:
                            slot["conflicts"] = []
                
                # Return the parsed result with debug logs
                result["success"] = True
                result["debug_logs"] = debug_logs
                return result
                
            except json.JSONDecodeError as e:
                debug_logs.append({
                    "message": f"JSON decode error: {str(e)}",
                    "type": "error"
                })
                debug_logs.append({
                    "message": f"Response content: {content[:200]}...",
                    "type": "debug"
                })
                return {
                    "success": False,
                    "error": "Failed to parse analysis results",
                    "analysis": "The AI response was not in the expected format.",
                    "debug_logs": debug_logs
                }
                
        except anthropic.APIError as e:
            error_message = str(e)
            debug_logs.append({
                "message": f"Claude API error: {error_message}",
                "type": "error"
            })
            return {
                "success": False,
                "error": f"API error: {error_message}",
                "debug_logs": debug_logs
            }
            
        except Exception as e:
            error_message = str(e)
            debug_logs.append({
                "message": f"Unexpected error during API call: {error_message}",
                "type": "error"
            })
            return {
                "success": False,
                "error": f"Error: {error_message}",
                "debug_logs": debug_logs
            }
            
    except Exception as e:
        error_message = str(e)
        debug_logs.append({
            "message": f"Unexpected error in analyze_screenshot: {error_message}",
            "type": "error"
        })
        return {
            "success": False,
            "error": f"Error: {error_message}",
            "debug_logs": debug_logs
        } 