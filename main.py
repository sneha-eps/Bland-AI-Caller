import os
import sys
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import importlib.util

# Try to import from the 'blandai' package
try:
    if importlib.util.find_spec("blandai") is not None:
        import blandai
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

VOICE_MAP = {
        "male_professional": "61507da3-4abd-49b6-983f-9ce659fd9e91",
        "female_professional": "70f05206-71ab-4b39-b238-ed1bf17b365a",
        "female_warm": "2f9fdbc7-4bf2-4792-8a18-21ce3c93978f",
        "female_clear": "17e8f694-d230-4b64-b040-6108088d9e6c",
        "female_friendly": "bbeabae6-ec8d-444f-92ad-c8e620d3de8d",
        "male_casual": "a3d43393-dacb-43d3-91d7-b4cb913a5908",
        "male_warm": "90295ec4-f0fe-4783-ab33-8b997ddc3ae4",
        "male_clear": "37b3f1c8-a01e-4d70-b251-294733f08371"
    }

def get_voice_id(name = "female_professional") -> str:
    """Get the voice ID for the given voice name"""
    return VOICE_MAP.get(name, VOICE_MAP["female_professional"])  # Default to female_professional

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
• If the patient says a greeting such as "hello", "hi", "hey", etc. **after** the call has already started, treat it as a normal acknowledgment and continue from the current step — do **not** restart the conversation from the opening.


CONVERSATION FLOW (STRICT ORDER)
1) OPENING
   DO NOT speak immediately when call connects. Wait for the person to answer with "hello" or similar greeting first.
   Only after they speak, say exactly: "Hi, I'm calling from [clinic name]. Am I speaking with {{patient name}}?"
   Then stop and wait.

2) IDENTITY CHECK
   • If response indicates wrong person/number: ask, "Just to confirm, may I please speak with {{patient name}}?" Wait.
     – If again wrong/unavailable: say, "My apologies for the confusion. Thank you for your time, and have a good day." End the call.
   • If identity confirmed: proceed.

3) APPOINTMENT CONFIRMATION QUESTION
   Say: "Perfect! The reason for my call is to confirm your upcoming appointment on [date] at [time] with [provider name] at our [office location]. Will you be able to make it to your appointment?"
   Then stop and wait.

⚠️ CRITICAL CANCELLATION RULE ⚠️
BEFORE doing ANYTHING else, scan the patient's response for these words: "cancel", "canceling", "cancellation", "cancelled", "cancel it", "cancel this", "cancel my appointment", "want to cancel", "can I cancel", "I'd like to cancel".

IF YOU FIND ANY OF THESE WORDS:
- STOP all other analysis
- IGNORE everything else they said
- Classify as UNSURE
- Go directly to UNSURE response: "Thanks for letting me know. Would you like to reschedule this appointment for a different time, or would you prefer to cancel it?"

ONLY if NO cancellation words exist, then classify the response:

A) CONFIRM — Explicit "yes" with no conditions or uncertainty
B) CANNOT ATTEND — Clear refusal (e.g., "I can't make it", "I won't be available")  
C) UNSURE — Conditional, tentative, or ambiguous responses
D) OFF-TOPIC — Does not address the appointment question
E) RESCHEDULE — Explicit request to reschedule

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
  – If they say reschedule → Switch to RESCHEDULE flow (ask for queries, then arrange callback).
  – If they say cancel → "Okay, I will cancel this appointment for you. Please feel free to contact us anytime you're ready to schedule a new one." Wait, then end after acknowledgment.
  – If they now give an explicit, unconditional confirmation → switch to CONFIRM flow.

• IF RESCHEDULE (when patient explicitly requests to reschedule):
  Say: "Of course! Our scheduling agent will call you shortly to find a new time that works better for you. Do you have any questions about your appointment or anything else I can help you with?"
  Wait for response.
  – If they have questions: Answer appropriately, then say "Is there anything else I can help you with?" Wait for response.
  – If no questions or after answering: Say "Perfect. Someone will be in touch soon to reschedule. Have a great day!" and end the call.

• IF OFF-TOPIC / NON-RESPONSIVE:
  Briefly address any concern if needed, then repeat the last question clearly and wait.

MANDATORY CALL TERMINATION RULES:
1. After delivering final information or completing a transaction, wait 10–15 seconds to allow for any last-minute questions.
2. If the patient asks a follow-up question during this waiting period, answer it briefly and then ask, "Is there anything else I can help you with?"
3. If the patient gives a brief acknowledgment such as "thanks", "thank you", "okay", "great", or "alright" (or any similar short closing phrase), respond politely (e.g., "You're welcome! Have a great day!") and then wait 3–4 seconds before ending the call. If they speak again during this wait, continue the conversation.
4. If no response is received after the 10–15 second waiting period, deliver a clear goodbye message and end the call.
5. If silence persists for 10 seconds or more at any point after the main business is completed, end the call automatically without requiring repeated acknowledgments.
6. Ensure that only one short waiting period is used for ending phrases. Do not stack multiple timers or prolong the closing unnecessarily.

NATURAL CALL ENDING PROCESS:
• Complete the main task (confirmation, cancellation, or reschedule arrangement).
• Wait 10-15 seconds to allow for final questions
• If questions arise: answer briefly, then ask "Is there anything else I can help you with?" and wait another 10-15 seconds.
• If brief acknowledgment: "You're welcome! Have a great day!" then wait 3-4 seconds before ending call.
• If silence after 10-15 second wait: "Alright, have a great day!" and end call.
• If no response after 3-4 second wait: end call.
• If silence after 10 seconds at any point after the main task is done: end call automatically.

REMEMBER: Maintain natural conversation flow with appropriate pauses. Let patients naturally end with acknowledgments while ensuring calls don't continue indefinitely."""

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
        # bland_client = BlandAI(api_key=api_key)

        # Make the call
        # response = bland_client.call(
        #     phone_number=call_request.phone_number,
        #     task=get_call_prompt(),
        #     voice=get_voice_id("female_professional"),
        #     request_data=call_data
        # )
        selected_voice = VOICE_MAP.get("female_professional", "default_voice_id")

        response = requests.post(
            "https://api.bland.ai/v1/call",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "phone_number": call_request.phone_number,
            "task": get_call_prompt(),
            "voice": selected_voice,
            "request_data": call_data
        })
        resp_json = response.json()
        return {
            "success": True,
            "call_id": resp_json("call_id", "N/A"),
            "status": resp_json("status", "N/A"),
            "message": resp_json("message", "N/A")
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail= str(e)
        )

@app.get("/docs")
async def get_docs():
    """Access FastAPI automatic documentation"""
    return {"message": "Visit /docs for interactive API documentation"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)