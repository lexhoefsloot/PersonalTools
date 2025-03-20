import os
import json
import base64
import anthropic
from PIL import Image
import io
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        
        # Get API key from environment variables
        api_key = os.environ.get('CLAUDE_API_KEY')
        if not api_key:
            logger.error("Claude API key not found in environment variables")
            raise ValueError("Claude API key not found in environment variables")
        else:
            logger.info("Claude API key found")
        
        # Initialize Claude client exactly as shown in documentation
        client = anthropic.Anthropic(
            api_key=api_key,
        )
        logger.info("Claude client initialized")
        
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
        
        # Extract response text as shown in documentation
        response_text = message.content[0].text
        
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