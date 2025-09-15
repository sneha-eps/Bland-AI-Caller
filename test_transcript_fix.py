#!/usr/bin/env python3
"""
Test script to verify the AI call analysis fix for the transcript bug.
This tests the actual transcript from the user's screenshots.
"""

# Import the function from main.py
import sys
sys.path.append('.')
from main import analyze_call_transcript

def test_akshay_transcript():
    """Test the actual transcript from the user's screenshots"""
    
    # The actual transcript from the screenshots
    transcript = """user: Hello.
assistant: Hi, I'm calling from Passion Health Primary Care. Am I speaking with Akshay?
user: Yeah, who is this?
assistant: I'm calling from Passion Health Primary Care, and I'd like to confirm your upcoming appointment. Just to confirm, may I please speak with Akshay?
user: Yeah, yeah, Akshay.
assistant: Perfect, the reason for my call is to confirm your upcoming appointment on October eighth, two thousand and twenty-five at one thirty PM with Dr. Guerra at our Passion Health Kaufman clinic. Will you be able to make it to your appointment?
user: Yep. That other suggestion is valid.
assistant: Excellent, we are glad to have you. Just a reminder to please arrive fifteen minutes early for check-in. If you have any insurance -
user: Cool. Thank you.
assistant: You're welcome. If you have any insurance changes, please email them to passion health physicians at gmail dot com. For any other issues, you can call the office at four six nine,-
user: Okay. That's it. Thank you. Bye bye.
assistant: Just to confirm, your appointment on October eighth, two thousand and twenty-five at one thirty PM with Dr. Guerra at Passion Health Kaufman is confirmed. You're welcome, have a great day, bye"""

    print("Testing transcript analysis...")
    print("="*50)
    
    result = analyze_call_transcript(transcript)
    
    print(f"Analysis result: {result}")
    print("="*50)
    
    if result == 'confirmed':
        print("✅ SUCCESS: Transcript correctly identified as CONFIRMED")
        print("The patient asked 'who is this?' but then confirmed their appointment.")
    elif result == 'wrong_number':
        print("❌ FAILED: Still incorrectly identifying as WRONG NUMBER")
        print("The 'who is this?' pattern may still be causing issues.")
    else:
        print(f"⚠️  UNEXPECTED: Got result '{result}' instead of 'confirmed'")
    
    return result

if __name__ == "__main__":
    test_akshay_transcript()