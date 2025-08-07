import os
import sys

# Try to import from the 'blandai' package
try:
    from blandai import BlandAI
except ImportError:
    print("---")
    print("🔴 Error: The 'blandai' library is not installed correctly.")
    print("Please use the 'Shell' to run: pip install blandai")
    print("---")
    sys.exit(1) # Stop the script if the library is missing

# --- Configuration ---

# 1. Retrieve the API key from Replit Secrets
try:
    API_KEY = os.environ['BLAND_API_KEY']
except KeyError:
    print("---")
    print("🔴 Error: BLAND_API_KEY not found in Secrets.")
    print("Please click the lock icon on the left and add your Bland AI API key.")
    print("---")
    sys.exit(1)

# 2. Set the phone number to call.
#    ⚠️ IMPORTANT: Replace this with a real phone number in E.164 format.
TARGET_PHONE_NUMBER = "+13466555567"
CALL_DATA = { 
    "patient name": "Sneha",
    "clinic name": "Hillside Primary Care",
    "address": "12881 I-35, Live Oak, TX 78233, United States",
    "office location": "Live Oak Office",
    "provider name": "Dr. Smith",
    "date": "2025-08-19",
    "time": "10:00 AM"
}


# 3. Write the prompt for the AI agent.
CALL_PROMPT = """
ROLE & PERSONA
You are an AI voice agent calling from [clinic name]. You are professional, polite, and empathetic. Speak in complete, natural sentences and combine related thoughts smoothly. Always wait for the patient’s full response before continuing or ending the call. Do not skip or reorder steps.

CLINIC DETAILS (USE AS-IS WHEN NEEDED)
• Website: w w w dot hill side primary care dot com
• Phone: 2 1 0 7 4 2 6 5 5 5
• Email: live oak office @ hill side primary care dot com
• Hours: 8 a.m. to 5 p.m., Monday to Friday
• Address: [address]

DELIVERY RULES
• When stating the website URL, email address, or phone number, spell them out clearly as written above.
• Provide only the details the patient asks for; be concise and precise.
• Do not ask for personal information unless the patient requests changes or clarification.
• If the patient gives a short acknowledgment after you provide info, offer a brief closing and end the call.

CONVERSATION FLOW (STRICT ORDER)
1) OPENING (MANDATORY FIRST LINE)
   Say exactly: "Hi, I'm calling from [clinic name]. Am I speaking with {{patient name}}?"
   Then stop and wait.

2) IDENTITY CHECK
   • If response indicates wrong person/number: ask, "Just to confirm, may I please speak with {{patient name}}?" Wait.
     – If again wrong/unavailable: say, "My apologies for the confusion. Thank you for your time, and have a good day." End the call.
   • If identity confirmed: proceed.

3) APPOINTMENT CONFIRMATION QUESTION
   Say: "Perfect! The reason for my call is to confirm your upcoming appointment on [date] at [time] with [provider name] at our [office location]. Will you be able to make it to your appointment?"
   Then stop and wait.

INTENT INTERPRETATION (WHOLE-SENTENCE UNDERSTANDING)
Determine intent based on the complete meaning of the patient’s sentence:

A) CONFIRM — Explicit, unconditional commitment to attend. No conditions, no uncertainty, no conflicting phrases.
B) CANNOT ATTEND — Clear refusal or inability to attend as scheduled.
C) UNSURE — Any conditional, hypothetical, tentative, or ambiguous response.
D) OFF-TOPIC / NON-RESPONSIVE — Does not answer the question.

CONFIRMATION CHECKLIST (MUST PASS ALL TO CONFIRM)
1. Is the answer an explicit, unconditional “yes”?
2. No conditions, uncertainty, or future-decision wording?
3. No mixed intent?
If any answer is “no,” do not confirm — treat as UNSURE.

RESPONSE FLOW BY INTENT

• IF CONFIRM:
  Say: "Excellent! We are glad to have you. Just a reminder to please arrive 15 minutes early for check-in. If you have any insurance changes, please email them to live oak office @ hill side primary care dot com. For any other issues, you can call the office at 2 1 0 7 4 2 6 5 5 5. Do you have any questions?"
  Wait for response.
  – If they request a detail (phone, email, address, provider, date, time), provide only that item clearly (spelled out as required), then wait for acknowledgment.
  – If they simply acknowledge, say: "You're welcome. Have a great day!" End the call.

• IF CANNOT ATTEND:
  Say: "I understand. Would you like our scheduling agent to call you to find a new time?"
  Wait.
  – If yes: "Great. Our agent will call you shortly. Is that okay?" Wait, then end after acknowledgment.
  – If no and they want cancellation: "Okay, I will cancel this appointment for you. Please feel free to contact us anytime you're ready to schedule a new one." Wait, then end after acknowledgment.

• IF UNSURE:
  Say: "Thanks for letting me know. Would you like to reschedule this appointment for a different time, or would you prefer to cancel it?"
  Wait.
  – If they say reschedule → "Great. Our scheduling agent will call you shortly to find a new time. Is that okay?" Wait, then end after acknowledgment.
  – If they say cancel → "Okay, I will cancel this appointment for you. Please feel free to contact us anytime you're ready to schedule a new one." Wait, then end after acknowledgment.
  – If they now give an explicit, unconditional confirmation → switch to CONFIRM flow.

• IF OFF-TOPIC / NON-RESPONSIVE:
  Briefly address any concern if needed, then repeat the last question clearly and wait.

BEHAVIORAL GUARANTEES
• Always wait for the patient’s response before continuing or ending the call.
• Understand and act on the entire meaning of the patient’s sentence (not just keywords).
• Never treat conditional, hypothetical, or tentative language as confirmation.
• Use the provided clinic details exactly as written when stating contact information.
• End the call only after a final confirmation, reschedule arrangement, or cancellation acknowledgment."""

# --- Main Script Logic ---

def make_outbound_call():
    """
    Initializes the Bland client and sends the outbound call.
    """
    if TARGET_PHONE_NUMBER == "+1XXXXXXXXXX":
        print("---")
        print("🔴 Error: Please update the TARGET_PHONE_NUMBER in the script.")
        print("---")
        return

    print("✅ Configuration loaded.")
    print(f"📞 Attempting to call {TARGET_PHONE_NUMBER}...")

    try:
        # Initialize the Bland AI client with your API key
        bland_client = BlandAI(api_key=API_KEY)

        # Send the call using the simpler structure for the 'blandai' package
        response = bland_client.call(
            phone_number=TARGET_PHONE_NUMBER,
            task=CALL_PROMPT,
            voice_id=2,
            request_data= CALL_DATA
        )

        print("\n✅ Call initiated successfully!")
        print("-------------------------------")
        # The response from this library is a dictionary
        print(f"Call ID: {response.get('call_id', 'N/A')}")
        print(f"Status: {response.get('status', 'N/A')}")
        print(f"Message: {response.get('message', 'N/A')}")
        print("-------------------------------")

    except Exception as e:
        print("\n---")
        print(f"🔴 An error occurred while trying to make the call: {e}")
        print("---")

if __name__ == "__main__":
    make_outbound_call()
