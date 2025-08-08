
import os
import sys
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

# Try to import from the 'blandai' package
try:
    from blandai import BlandAI
except ImportError:
    print("---")
    print("🔴 Error: The 'blandai' library is not installed correctly.")
    print("Please use the 'Shell' to run: pip install blandai")
    print("---")
    sys.exit(1)

app = FastAPI(title="Bland AI Call Center", description="Make automated calls using Bland AI")
templates = Jinja2Templates(directory="templates")

# --- Configuration ---

def get_api_key():
    """Retrieve the API key from Replit Secrets"""
    try:
        return os.environ['BLAND_API_KEY']
    except KeyError:
        return None

def get_voice_id(voice_name: str = "female_professional") -> int:
    """Map friendly voice names to Bland AI voice IDs"""
    voice_mapping = {
        "male_professional": 0,
        "female_professional": 11,
        "female_warm": 4,
        "female_clear": 6,
        "female_friendly": 8,
        "male_casual": 1,
        "male_warm": 2,
        "male_clear": 3
    }
    return voice_mapping.get(voice_name, 11)  # Default to female_professional

def get_call_prompt():
    """Return the call prompt"""
    return """
ROLE & PERSONA
You are an AI voice agent calling from [clinic name]. You are professional, polite, and empathetic. Speak in complete, natural sentences and combine related thoughts smoothly. Always wait for the patient's full response before continuing or ending the call. Do not skip or reorder steps.

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
Determine intent based on the complete meaning of the patient's sentence:

A) CONFIRM — Explicit, unconditional commitment to attend. No conditions, no uncertainty, no conflicting phrases.
B) CANNOT ATTEND — Clear refusal or inability to attend as scheduled.
C) UNSURE — Any conditional, hypothetical, tentative, or ambiguous response.
D) OFF-TOPIC / NON-RESPONSIVE — Does not answer the question.
E) RESCHEDULE — Explicit request to reschedule.

CONFIRMATION CHECKLIST (MUST PASS ALL TO CONFIRM)
1. Is the answer an explicit, unconditional "yes"?
2. No conditions, uncertainty, or future-decision wording?
3. No mixed intent?
If any answer is "no," do not confirm — treat as UNSURE.
If the user asks for a reschedule, treat as RESCHEDULE.

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
  – If they say reschedule → "Perfect! Our scheduling agent will call you shortly to find a new time that works better for you. Is that okay?" Wait for acknowledgment, then say "Great. Someone will be in touch soon. Have a great day!" and end the call.
  – If they say cancel → "Okay, I will cancel this appointment for you. Please feel free to contact us anytime you're ready to schedule a new one." Wait, then end after acknowledgment.
  – If they now give an explicit, unconditional confirmation → switch to CONFIRM flow.

• IF RESCHEDULE (when patient explicitly requests to reschedule):
  Say: "Of course! Our scheduling agent will call you shortly to find a new time that works better for you. Is that okay?" 
  Wait for acknowledgment, then say "Perfect. Someone will be in touch soon. Have a great day!" and end the call.

• IF OFF-TOPIC / NON-RESPONSIVE:
  Briefly address any concern if needed, then repeat the last question clearly and wait.

BEHAVIORAL GUARANTEES
• Always wait for the patient's response before continuing or ending the call.
• Understand and act on the entire meaning of the patient's sentence (not just keywords).
• Never treat conditional, hypothetical, or tentative language as confirmation.
• Use the provided clinic details exactly as written when stating contact information.
• End the call only after a final confirmation, reschedule arrangement, or cancellation acknowledgment.
• If there is no response from the patient for 3-4 seconds after asking a question, politely say "I didn't hear a response. Thank you for your time, and have a good day" and end the call.
• If the patient gives a very brief acknowledgment (like "okay", "thanks", "got it") after receiving information, respond with "You're welcome. Have a great day!" and immediately end the call."""

class CallRequest(BaseModel):
    phone_number: str
    patient_name: str
    clinic_name: str
    address: Optional[str] = ""
    office_location: Optional[str] = ""
    provider_name: str
    appointment_date: str
    appointment_time: str

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page with the calling interface"""
    api_key = get_api_key()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "has_api_key": bool(api_key)
    })

@app.post("/make_call")
async def make_call(call_request: CallRequest):
    """Handle the call request from the frontend"""
    api_key = get_api_key()
    
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="BLAND_API_KEY not found in Secrets. Please add your API key."
        )
    
    # Validate required fields
    if not all([
        call_request.phone_number,
        call_request.patient_name,
        call_request.clinic_name,
        call_request.provider_name,
        call_request.appointment_date,
        call_request.appointment_time
    ]):
        raise HTTPException(
            status_code=400,
            detail="Please fill in all required fields."
        )
    
    # Prepare call data
    call_data = {
        "patient name": call_request.patient_name,
        "clinic name": call_request.clinic_name,
        "address": call_request.address,
        "office location": call_request.office_location,
        "provider name": call_request.provider_name,
        "date": call_request.appointment_date,
        "time": call_request.appointment_time
    }
    
    try:
        # Initialize the Bland AI client
        bland_client = BlandAI(api_key=api_key)
        
        # Make the call
        response = bland_client.call(
            phone_number=call_request.phone_number,
            task=get_call_prompt(),
            voice_id="aec18940-3d5a-4454-acd2-66f685e83b67",
            request_data=call_data
        )
        
        return {
            "success": True,
            "call_id": response.get("call_id", "N/A"),
            "status": response.get("status", "N/A"),
            "message": response.get("message", "N/A")
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while making the call: {str(e)}"
        )

@app.get("/docs")
async def get_docs():
    """Access FastAPI automatic documentation"""
    return {"message": "Visit /docs for interactive API documentation"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
