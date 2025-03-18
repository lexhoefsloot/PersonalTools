import os
import json
import base64
from anthropic import Anthropic
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
        
        # Initialize Claude client
        client = Anthropic(api_key=api_key)
        
        # Prepare image for Claude
        base64_image = encode_image_to_base64(screenshot_path)
        
        # Create system prompt for Claude
        system_prompt = """
        You are an assistant that analyzes screenshots of conversations to identify meeting time suggestions or requests.
        Your task is to:
        1. Determine if the conversation contains someone suggesting specific times for a meeting OR someone asking for time suggestions.
        2. Extract all mentioned time slots, dates, and durations.
        3. Format the extracted information in a consistent way.
        
        For each extracted time slot, provide:
        - Start time and date in ISO format (YYYY-MM-DD HH:MM)
        - End time and date in ISO format (if duration is mentioned)
        - Any context about the time slot (e.g., "preferred", "alternative", etc.)
        
        Return your analysis as JSON with the following structure:
        {
            "is_suggestion": true/false, (true if the screenshot shows someone suggesting times, false if asking for times)
            "time_slots": [
                {
                    "start": "YYYY-MM-DD HH:MM",
                    "end": "YYYY-MM-DD HH:MM", (if duration is mentioned)
                    "context": "string description"
                }
            ],
            "analysis": "brief analysis of what was detected in natural language"
        }
        
        If no time information is found, return an empty time_slots array.
        """
        
        # Define user message with the screenshot
        user_message = "Please analyze this screenshot of a conversation and extract any meeting time suggestions or requests."
        
        # Call Claude API
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64_image}}
                    ]
                }
            ],
            temperature=0.0
        )
        
        # Extract and parse JSON from Claude's response
        response_text = response.content[0].text
        
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
            return result
        
        except json.JSONDecodeError:
            print("Failed to parse JSON from Claude's response")
            print(f"Raw response: {response_text}")
            return {
                "is_suggestion": False,
                "time_slots": [],
                "analysis": "Failed to extract structured data from the screenshot"
            }
    
    except Exception as e:
        print(f"Error analyzing screenshot with Claude: {str(e)}")
        return None 