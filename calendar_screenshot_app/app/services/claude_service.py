import os
import json
import base64
import anthropic
from PIL import Image
import io

def encode_image_to_base64(image_path):
    """Encode image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_screenshot(screenshot_path):
    """Analyze screenshot with Claude API to extract meeting time information"""
    try:
        # Get API key from environment variables
        api_key = os.environ.get('CLAUDE_API_KEY')
        if not api_key:
            raise ValueError("Claude API key not found in environment variables")
        
        # Initialize Claude client exactly as shown in documentation
        client = anthropic.Anthropic(
            api_key=api_key,
        )
        
        # Prepare image for Claude
        base64_image = encode_image_to_base64(screenshot_path)
        
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
        
        # Define user message with the screenshot
        user_message = "Please analyze this conversation screenshot and extract any meeting time information. Identify whether someone is suggesting times or requesting times, and extract all time slots mentioned with their contextual information."
        
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
        
        # Extract response text as shown in documentation
        response_text = message.content[0].text
        
        # Try to extract JSON from the response
        try:
            # Look for JSON block in the response
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()
            
            result = json.loads(json_str)
            
            # Add basic validation
            if "is_suggestion" not in result:
                result["is_suggestion"] = False
            if "time_slots" not in result:
                result["time_slots"] = []
            if "analysis" not in result:
                result["analysis"] = "Analysis not provided"
            
            print(f"Successfully analyzed screenshot with Claude: {result['analysis']}")
            return result
        
        except json.JSONDecodeError:
            print("Failed to parse JSON from Claude's response")
            print(f"Raw response: {response_text}")
            return {
                "is_suggestion": False,
                "time_slots": [],
                "confidence": 0.0,
                "analysis": "Failed to extract structured data from the screenshot"
            }
    
    except Exception as e:
        print(f"Error analyzing screenshot with Claude: {str(e)}")
        return {
            "is_suggestion": False,
            "time_slots": [],
            "confidence": 0.0,
            "analysis": f"Error processing screenshot: {str(e)}"
        } 