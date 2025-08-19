import os
import sys
import requests
import csv
import io
import pandas as pd
import time
import asyncio
import aiohttp
import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import importlib
import importlib.util
import re

# Check if 'blandai' package is available (optional since we're using requests directly)
try:
    if importlib.util.find_spec("blandai") is not None:
        print("✅ blandai library is available")
    else:
        print(
            "⚠️ blandai library not found, but continuing with direct API calls"
        )
except ImportError:
    print(
        "⚠️ blandai library check failed, but continuing with direct API calls"
    )

app = FastAPI(title="Bland AI Call Center",
              description="Make automated calls using Bland AI")
templates = Jinja2Templates(directory="templates")

# In-memory storage (in production, use a database)
clients_db = {}
campaigns_db = {}
campaign_results_db = {}

# Add number formatting filter
def number_format(value):
    """Format numbers with commas"""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

# Add the filter to Jinja2 environment
templates.env.filters['number_format'] = number_format

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


def get_voice_id(name="female_professional") -> str:
    """Get the voice ID for the given voice name"""
    return VOICE_MAP.get(
        name,
        VOICE_MAP["female_professional"])  # Default to female_professional


def get_call_prompt(office_location: str = "",
        patient_name: str = "[patient name]",
        appointment_date: str = "[date]",
        appointment_time: str = "[time]",
        provider_name: str = "[provider name]"):
    """Return the call prompt"""
    return f"""
    ROLE & PERSONA
    You are an AI voice agent calling from [clinic name]. You are professional, polite, and empathetic. Speak in complete, natural sentences and combine related thoughts smoothly. Always wait for the patient's full response before continuing or ending the call. Do not skip or reorder steps.

    CLINIC DETAILS (USE AS-IS WHEN NEEDED)
    • Website: w w w dot hill side primary care dot com
    • Phone: 2 1 0 7 4 2 6 5 5 5
    • Email: live oak office @ hill side primary care dot com
    • Hours: 8 a.m. to 5 p.m., Monday to Friday
    • Address: {office_location if office_location else '[address]'}

    DELIVERY RULES
    • Speak naturally like a real person having a conversation - don't sound like you're reading a script
    • When giving contact info, say it normally - don't over-pronounce each letter/digit
    • Convert 24-hour time to natural 12-hour format: "15:00" becomes "3 PM", "09:30" becomes "9:30 AM", etc.
    • Say times naturally like a person would: "3 PM" not "fifteen hundred", "9:30 AM" not "oh nine thirty"
    • Be helpful and friendly, but keep it casual and conversational
    • If someone says "hi" or "hello" during the call, just acknowledge it warmly and keep going
    • Sound genuinely interested in helping, not mechanical

    CONVERSATION STYLE
    • Talk like you're having a friendly phone conversation with someone you know
    • Use natural pauses and rhythm - don't rush through information
    • Sound warm and approachable, not formal or scripted
    • Keep your tone consistent throughout - friendly but professional

    CRITICAL MID-CALL GREETING RULE:
    If the patient says "hi", "hello", "hey", or any greeting AFTER the call has started, this means they are just being polite or acknowledging something you said. You should:
    1. Give a brief, warm acknowledgment like "Oh hi!" or "Hello there!"
    2. IMMEDIATELY continue from the exact point where you were in the conversation
    3. DO NOT restart the conversation from the beginning
    4. DO NOT ask "how may I help you?" or similar service phrases
    5. DO NOT treat it as a new conversation starter

    CONVERSATION FLOW (STRICT ORDER)
    1) OPENING
    Respond to their initial greeting with: "Hi, I'm calling from [clinic name]. Am I speaking with {patient_name}?"

    REMEMBER: Any greeting after this opening should be treated as a polite acknowledgment, not a conversation restart.

    2) IDENTITY CHECK
    • If response indicates wrong person/number: ask, "Just to confirm, may I please speak with {patient_name}?" Wait.
    – If again wrong/unavailable: say, "My apologies for the confusion. Thank you for your time, and have a good day." End the call.
    • If identity confirmed: proceed.

    3) APPOINTMENT CONFIRMATION QUESTION
    Say: "Perfect! The reason for my call is to confirm your upcoming appointment on {appointment_date} at {appointment_time} with {provider_name} at our clinic located at {office_location}. Will you be able to make it to your appointment?"
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
    E) RESCHEDULE — Explicit request to reschedule (e.g., "I'd like to reschedule", "Can we change the time?", "Let's find a new time", "Can we schedule it", "I want to schedule", "can we reschedule", "I want to reschedule", etc.)

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
    • If silence after 10-15 second wait: "Alright, have a great day!" and end the call.
    • If no response after 3-4 second wait: end call.
    • If silence after 10 seconds at any point after the main task is done: end call automatically.

    REMEMBER: Maintain natural conversation flow with appropriate pauses. Let patients naturally end with acknowledgments while ensuring calls don't continue indefinitely."""


class CallRequest(BaseModel):
    phone_number: str
    patient_name: str
    provider_name: str
    appointment_date: str
    appointment_time: str
    office_location: str


class CallResult(BaseModel):
    success: bool
    call_id: Optional[str] = None
    status: Optional[str] = None
    call_status: Optional[
        str] = None  # confirmed, rescheduled, cancelled, voicemail, busy
    transcript: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    patient_name: str
    phone_number: str


class Client(BaseModel):
    id: Optional[str] = None
    name: str
    phone_number: str
    email: str
    website_url: str
    language: str
    call_type: str
    voice: str


class Campaign(BaseModel):
    id: Optional[str] = None
    name: str
    client_id: str
    max_attempts: int
    retry_interval: int
    country_code: str
    file_name: Optional[str] = None
    file_data: Optional[bytes] = None


def format_phone_number(phone_number, country_code) -> str:
    """Format phone number with the selected country code"""
    if phone_number is None:
        phone_number = ''
    if country_code is None:
        country_code = '+1'

    # Convert to string and remove all non-digit characters
    phone_str = str(phone_number) if phone_number is not None else ''
    cleaned = re.sub(r'[^\d]', '', phone_str.strip())

    # Add the selected country code
    return f"{country_code}{cleaned}"


async def make_single_call_async(call_request: CallRequest, api_key: str,
                                 semaphore: asyncio.Semaphore) -> CallResult:
    """Make a single call asynchronously with concurrency control"""
    async with semaphore:  # Limit concurrent calls to 10
        call_data = {
            "patient name": call_request.patient_name,
            "provider name": call_request.provider_name,
            "date": call_request.appointment_date,
            "time": call_request.appointment_time
        }

        try:
            selected_voice = VOICE_MAP.get("female_professional",
                                           "default_voice_id")

            payload = {
                "phone_number": call_request.phone_number,
                "task": get_call_prompt(
                    office_location=call_request.office_location,
                    patient_name=call_request.patient_name,
                    appointment_date=call_request.appointment_date,
                    appointment_time=call_request.appointment_time,
                    provider_name=call_request.provider_name
                ),
                "voice": selected_voice,
                "request_data": call_data
            }

            print(
                f"🔄 Initiating call to {call_request.phone_number} for {call_request.patient_name}"
            )
            print(f"📞 API Payload keys: {list(payload.keys())}"
                  )  # Don't log full payload for security

            async with aiohttp.ClientSession() as session:
                async with session.post(
                        "https://api.bland.ai/v1/calls",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60)) as response:

                    response_text = await response.text()
                    print(f"📊 API Response Status: {response.status}")
                    print(f"📄 API Response: {response_text}")

                    if response.status == 200:
                        resp_json = await response.json()
                        print(
                            f"✅ Call initiated successfully for {call_request.patient_name}"
                        )
                        return CallResult(
                            success=True,
                            call_id=resp_json.get("call_id", "N/A"),
                            status=resp_json.get("status", "N/A"),
                            message=resp_json.get("message",
                                                  "Call successfully queued."),
                            patient_name=call_request.patient_name,
                            phone_number=call_request.phone_number)
                    elif response.status == 429:
                        print(
                            f"⏳ Rate limit hit for {call_request.patient_name}"
                        )
                        return CallResult(
                            success=False,
                            error=
                            "Rate limit exceeded - please try again later",
                            patient_name=call_request.patient_name,
                            phone_number=call_request.phone_number)
                    else:
                        error_msg = f"API error (Status {response.status})"
                        try:
                            error_json = await response.json()
                            if 'message' in error_json:
                                error_msg += f": {error_json['message']}"
                            elif 'detail' in error_json:
                                error_msg += f": {error_json['detail']}"
                            else:
                                error_msg += f": {response_text}"
                        except:
                            error_msg += f": {response_text}"

                        print(
                            f"❌ API Error for {call_request.patient_name}: {error_msg}"
                        )
                        return CallResult(
                            success=False,
                            error=error_msg,
                            patient_name=call_request.patient_name,
                            phone_number=call_request.phone_number)
        except Exception as e:
            print(f"💥 Exception during call initiation: {str(e)}")
            return CallResult(success=False,
                              error=str(e),
                              patient_name=call_request.patient_name,
                              phone_number=call_request.phone_number)


def make_single_call(call_request: CallRequest, api_key: str) -> CallResult:
    """Make a single call and return the result"""
    call_data = {
        "patient name": call_request.patient_name,
        "provider name": call_request.provider_name,
        "date": call_request.appointment_date,
        "time": call_request.appointment_time
    }

    try:
        selected_voice = VOICE_MAP.get("female_professional",
                                       "default_voice_id")

        payload = {
            "phone_number": call_request.phone_number,
            "task": get_call_prompt(
                office_location=call_request.office_location,
                patient_name=call_request.patient_name,
                appointment_date=call_request.appointment_date,
                appointment_time=call_request.appointment_time,
                provider_name=call_request.provider_name
            ),
            "voice": selected_voice,
            "request_data": call_data
        }

        print(
            f"🔄 Initiating call to {call_request.phone_number} for {call_request.patient_name}"
        )
        print(f"📞 API Payload keys: {list(payload.keys())}"
              )  # Don't log full payload for security

        response = requests.post(
            "https://api.bland.ai/v1/calls",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60  # Increased timeout
        )

        print(f"📊 API Response Status: {response.status_code}")
        print(f"📄 API Response: {response.text}")

        if response.status_code == 200:
            resp_json = response.json()
            print(
                f"✅ Call initiated successfully for {call_request.patient_name}"
            )
            return CallResult(success=True,
                              call_id=resp_json.get("call_id", "N/A"),
                              status=resp_json.get("status", "N/A"),
                              message=resp_json.get(
                                  "message", "Call initiated successfully"),
                              patient_name=call_request.patient_name,
                              phone_number=call_request.phone_number)
        elif response.status_code == 429:
            print(
                f"⏳ Rate limit hit for {call_request.patient_name}, waiting 5 seconds..."
            )
            time.sleep(5)
            return CallResult(
                success=False,
                error=f"Rate limit exceeded - please try again later",
                patient_name=call_request.patient_name,
                phone_number=call_request.phone_number)
        else:
            error_msg = f"API error (Status {response.status_code})"
            try:
                error_json = response.json()
                if 'message' in error_json:
                    error_msg += f": {error_json['message']}"
                elif 'detail' in error_json:
                    error_msg += f": {error_json['detail']}"
                else:
                    error_msg += f": {response.text}"
            except:
                error_msg += f": {response.text}"

            print(f"❌ API Error for {call_request.patient_name}: {error_msg}")
            return CallResult(success=False,
                              error=error_msg,
                              patient_name=call_request.patient_name,
                              phone_number=call_request.phone_number)
    except Exception as e:
        print(f"💥 Exception during call initiation: {str(e)}")
        return CallResult(success=False,
                          error=str(e),
                          patient_name=call_request.patient_name,
                          phone_number=call_request.phone_number)


@app.post("/make-call")
async def make_call(call_request: CallRequest, country_code: str = "+1"):
    """Make a single call"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=
            "BLAND_API_KEY not found in Secrets. Please add your API key.")

    try:
        # Format phone number with country code
        formatted_phone = format_phone_number(call_request.phone_number,
                                              country_code)
        print(
            f"📞 Original: {call_request.phone_number} -> Formatted: {formatted_phone} (Country Code: {country_code})"
        )

        # Update the call request with formatted phone number
        call_request.phone_number = formatted_phone

        # Make the call
        result = make_single_call(call_request, api_key)

        return {
            "success": result.success,
            "call_id": result.call_id,
            "status": result.status,
            "message": result.message,
            "error": result.error,
            "patient_name": result.patient_name,
            "phone_number": result.phone_number
        }

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Error making call: {str(e)}")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard showing key metrics"""
    api_key = get_api_key()
    # Get actual counts from in-memory storage
    metrics = {
        "total_clients": len(clients_db),
        "total_campaigns": len(campaigns_db),
        "total_calls": 0,  # This would be calculated from actual call data
        "total_duration": "0h 0m"  # This would be calculated from actual call data
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "has_api_key": bool(api_key),
        "metrics": metrics
    })

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """CSV upload interface"""
    api_key = get_api_key()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "has_api_key": bool(api_key)
    })


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    """Clients management page"""
    api_key = get_api_key()
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "has_api_key": bool(api_key),
        "clients": list(clients_db.values())
    })

# Helper functions to load data (mimicking database interaction)
def load_clients():
    return list(clients_db.values())

def load_campaigns():
    return list(campaigns_db.values())


@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, client_id: Optional[str] = None, client_name: Optional[str] = None):
    """Display campaigns page"""
    try:
        clients = load_clients()
        campaigns = load_campaigns()
        has_api_key = bool(get_api_key())

        # Filter campaigns by client if client_id is provided
        filtered_campaigns = campaigns
        if client_id:
            filtered_campaigns = [c for c in campaigns if c.get('client_id') == client_id]

        # Remove file data from campaigns to make them JSON serializable
        serializable_campaigns = []
        for campaign in filtered_campaigns:
            campaign_copy = campaign.copy() if isinstance(campaign, dict) else campaign
            # Remove any file-related data that might be bytes
            if isinstance(campaign_copy, dict):
                if 'file_data' in campaign_copy:
                    del campaign_copy['file_data']
                if 'csv_data' in campaign_copy:
                    del campaign_copy['csv_data']
            serializable_campaigns.append(campaign_copy)

        return templates.TemplateResponse("campaigns.html", {
            "request": request,
            "clients": clients,
            "campaigns": serializable_campaigns,
            "has_api_key": has_api_key,
            "filtered_client_id": client_id,
            "filtered_client_name": client_name
        })
    except Exception as e:
        print(f"Error in campaigns_page: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading campaigns page: {str(e)}")


@app.post("/add_client")
async def add_client(client: Client):
    """Add a new client"""
    client_id = str(uuid.uuid4())
    client.id = client_id
    clients_db[client_id] = client.dict()
    return {"success": True, "client_id": client_id, "message": "Client added successfully"}


@app.post("/add_campaign")
async def add_campaign(
    name: str = Form(...),
    client_id: str = Form(...),
    max_attempts: int = Form(...),
    retry_interval: int = Form(...),
    country_code: str = Form(...),
    file: UploadFile = File(...)
):
    """Add a new campaign with file"""
    try:
        # Validate required fields
        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Campaign name is required.")

        if not client_id or client_id not in clients_db:
            raise HTTPException(status_code=400, detail="Valid client is required.")

        # Validate file type
        if not file.filename or not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
            raise HTTPException(status_code=400, detail="Please upload a CSV or XLSX file.")

        # Validate file size (max 10MB)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File size too large. Maximum 10MB allowed.")

        # Validate numeric fields
        if max_attempts < 1 or max_attempts > 10:
            raise HTTPException(status_code=400, detail="Max attempts must be between 1 and 10.")

        if retry_interval < 5 or retry_interval > 1440:
            raise HTTPException(status_code=400, detail="Retry interval must be between 5 and 1440 minutes.")

        campaign_id = str(uuid.uuid4())
        campaign_data = {
            "id": campaign_id,
            "name": name.strip(),
            "client_id": client_id,
            "max_attempts": max_attempts,
            "retry_interval": retry_interval,
            "country_code": country_code,
            "file_name": file.filename,
            "file_data": file_content
        }

        campaigns_db[campaign_id] = campaign_data
        print(f"✅ Campaign '{name}' created successfully with ID: {campaign_id}")
        return {"success": True, "campaign_id": campaign_id, "message": "Campaign created successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating campaign: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating campaign: {str(e)}")


@app.put("/update_campaign/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    name: str = Form(...),
    client_id: str = Form(...),
    max_attempts: int = Form(...),
    retry_interval: int = Form(...),
    country_code: str = Form(...),
    file: UploadFile = File(None)
):
    """Update an existing campaign"""
    if campaign_id not in campaigns_db:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign = campaigns_db[campaign_id]

    # Update basic fields
    campaign.update({
        "name": name,
        "client_id": client_id,
        "max_attempts": max_attempts,
        "retry_interval": retry_interval,
        "country_code": country_code
    })

    # Update file if provided
    if file and file.filename:
        if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
            raise HTTPException(status_code=400, detail="Please upload a CSV or XLSX file.")

        file_content = await file.read()
        campaign["file_name"] = file.filename
        campaign["file_data"] = file_content

    campaigns_db[campaign_id] = campaign
    return {"success": True, "message": "Campaign updated successfully"}

@app.post("/start_campaign/{campaign_id}")
async def start_campaign(campaign_id: str, file: UploadFile = File(None)):
    """Start a campaign using stored file or new upload"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="BLAND_API_KEY not found in Secrets. Please add your API key.")

    # Get campaign details
    if campaign_id not in campaigns_db:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign = campaigns_db[campaign_id]

    # Get client details
    client_id = campaign['client_id']
    if client_id not in clients_db:
        raise HTTPException(status_code=404, detail="Client not found")

    client = clients_db[client_id]

    try:
        # Use stored file or new upload
        if file and file.filename:
            # New file uploaded
            if not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
                raise HTTPException(status_code=400, detail="Please upload a CSV or XLSX file.")
            content = await file.read()
            filename = file.filename
        else:
            # Use stored file
            if not campaign.get('file_data') or not campaign.get('file_name'):
                raise HTTPException(status_code=400, detail="No file found for this campaign. Please upload a file.")
            content = campaign['file_data']
            filename = campaign['file_name']

        if filename.endswith('.xlsx'):
            # Read Excel file
            df = pd.read_excel(io.BytesIO(content))
            rows = df.to_dict('records')
        else:
            # Read CSV file
            csv_string = content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_string))
            rows = list(csv_reader)

        results = []
        row_count = 0

        # Prepare all call requests
        call_requests = []
        for row in rows:
            row_count += 1
            # Validate required fields
            required_fields = [
                'phone_number', 'patient_name', 'date', 'time', 'provider_name', 'office_location'
            ]
            missing_fields = [
                field for field in required_fields
                if not str(row.get(field, '')).strip()
            ]

            if missing_fields:
                results.append(
                    CallResult(
                        success=False,
                        error=f"Missing required fields: {', '.join(missing_fields)}",
                        patient_name=row.get('patient_name', 'Unknown'),
                        phone_number=row.get('phone_number', 'Unknown')))
                continue

            # Format phone number with campaign's country code
            phone_number_raw = row.get('phone_number', '')
            phone_number_str = str(phone_number_raw).strip() if phone_number_raw is not None else ''
            campaign_country_code = campaign.get('country_code', '+1') or '+1'
            formatted_phone = format_phone_number(phone_number_str, campaign_country_code)
            print(f"📞 Campaign {campaign['name']}: {phone_number_str} -> Formatted: {formatted_phone} (Country Code: {campaign_country_code})")

            # Create call request - safely handle None values
            def safe_str(value):
                return str(value).strip() if value is not None else ''

            call_request = CallRequest(
                phone_number=formatted_phone,
                patient_name=safe_str(row.get('patient_name', '')),
                provider_name=safe_str(row.get('provider_name', '')),
                appointment_date=safe_str(row.get('date', '')),
                appointment_time=safe_str(row.get('time', '')),
                office_location=safe_str(row.get('office_location', '')))
            call_requests.append(call_request)

        # Process all valid calls concurrently (max 10 at a time)
        if call_requests:
            print(f"🚀 Starting campaign '{campaign['name']}' - Processing {len(call_requests)} calls concurrently (max 10 simultaneous)")

            # Create semaphore to limit concurrent calls to 10
            semaphore = asyncio.Semaphore(10)

            # Create tasks for all calls
            tasks = [
                make_single_call_async(call_request, api_key, semaphore)
                for call_request in call_requests
            ]

            # Run all tasks concurrently
            concurrent_results = await asyncio.gather(*tasks)
            results.extend(concurrent_results)

        # Calculate summary
        successful_calls = sum(1 for r in results if r.success)
        failed_calls = len(results) - successful_calls

        # Store campaign results (in production, use a database)
        campaign_results = {
            "campaign_id": campaign_id,
            "campaign_name": campaign['name'],
            "client_name": client['name'],
            "total_calls": len(results),
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "started_at": datetime.now().isoformat(),
            "results": [result.dict() for result in results]
        }

        # Store in the global results database
        campaign_results_db[campaign_id] = campaign_results

        return {
            "success": True,
            "campaign_id": campaign_id,
            "campaign_name": campaign['name'],
            "total_calls": len(results),
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "results": [result.dict() for result in results]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting campaign: {str(e)}")


@app.get("/voice_preview/{voice_id}")
async def voice_preview(voice_id: str):
    """Get voice preview audio URL"""
    try:
        # In a real implementation, you would have actual preview audio URLs
        preview_urls = {
            "61507da3-4abd-49b6-983f-9ce659fd9e91": "https://example.com/preview/male_professional.mp3",
            "70f05206-71ab-4b39-b238-ed1bf17b365a": "https://example.com/preview/female_professional.mp3",
            "2f9fdbc7-4bf2-4792-8a18-21ce3c93978f": "https://example.com/preview/female_warm.mp3",
            "17e8f694-d230-4b64-b040-6108088d9e6c": "https://example.com/preview/female_clear.mp3",
            "bbeabae6-ec8d-444f-92ad-c8e620d3de8d": "https://example.com/preview/female_friendly.mp3",
            "a3d43393-dacb-43d3-91d7-b4cb913a5908": "https://example.com/preview/male_casual.mp3",
            "90295ec4-f0fe-4783-ab33-8b997ddc3ae4": "https://example.com/preview/male_warm.mp3",
            "37b3f1c8-a01e-4d70-b251-294733f08371": "https://example.com/preview/male_clear.mp3"
        }
        return {"success": True, "preview_url": preview_urls.get(voice_id, "")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting voice preview: {str(e)}")


@app.post("/process_csv")
async def process_csv(file: UploadFile = File(...),
                      country_code: str = Form("+1")):
    """Process CSV or XLSX file and make calls for all rows"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=
            "BLAND_API_KEY not found in Secrets. Please add your API key.")

    # Check if file is CSV or XLSX
    if not file.filename or not (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
        raise HTTPException(status_code=400,
                            detail="Please upload a CSV or XLSX file.")

    try:
        # Read file content based on format
        content = await file.read()

        if file.filename.endswith('.xlsx'):
            # Read Excel file
            df = pd.read_excel(io.BytesIO(content))
            rows = df.to_dict('records')
        else:
            # Read CSV file
            csv_string = content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_string))
            rows = list(csv_reader)

        results = []
        row_count = 0

        # Prepare all call requests
        call_requests = []
        for row in rows:
            row_count += 1
            # Validate required fields
            required_fields = [
                'phone_number', 'patient_name', 'date', 'time', 'provider_name', 'office_location'
            ]
            missing_fields = [
                field for field in required_fields
                if not str(row.get(field, '')).strip()
            ]

            if missing_fields:
                results.append(
                    CallResult(
                        success=False,
                        error=
                        f"Missing required fields: {', '.join(missing_fields)}",
                        patient_name=row.get('patient_name', 'Unknown'),
                        phone_number=row.get('phone_number', 'Unknown')))
                continue

            # Format phone number with selected country code
            phone_number_raw = row.get('phone_number', '')
            phone_number_str = str(phone_number_raw).strip() if phone_number_raw is not None else ''
            safe_country_code = country_code or '+1'
            formatted_phone = format_phone_number(phone_number_str, safe_country_code)
            print(
                f"📞 CSV Row: {phone_number_str} -> Formatted: {formatted_phone} (Country Code: {safe_country_code})"
            )

            # Create call request - safely handle None values
            def safe_str(value):
                return str(value).strip() if value is not None else ''

            call_request = CallRequest(
                phone_number=formatted_phone,
                patient_name=safe_str(row.get('patient_name', '')),
                provider_name=safe_str(row.get('provider_name', '')),
                appointment_date=safe_str(row.get('date', '')),
                appointment_time=safe_str(row.get('time', '')),
                office_location=safe_str(row.get('office_location', '')))
            call_requests.append(call_request)

        # Process all valid calls concurrently (max 10 at a time)
        if call_requests:
            print(
                f"🚀 Processing {len(call_requests)} calls concurrently (max 10 simultaneous)"
            )

            # Create semaphore to limit concurrent calls to 10
            semaphore = asyncio.Semaphore(10)

            # Create tasks for all calls
            tasks = [
                make_single_call_async(call_request, api_key, semaphore)
                for call_request in call_requests
            ]

            # Run all tasks concurrently
            concurrent_results = await asyncio.gather(*tasks)
            results.extend(concurrent_results)

        # Calculate summary
        successful_calls = sum(1 for r in results if r.success)
        failed_calls = len(results) - successful_calls

        return {
            "success": True,
            "total_calls": len(results),
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "results": [result.dict() for result in results]
        }

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Error processing CSV: {str(e)}")


@app.get("/campaign_analytics/{campaign_id}")
async def get_campaign_analytics(campaign_id: str):
    """Get campaign analytics including performance metrics and call details"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(status_code=400,
                            detail="BLAND_API_KEY not found in Secrets.")

    try:
        # Get campaign results from in-memory storage (in production, use a database)
        if campaign_id in campaign_results_db:
            campaign_results = campaign_results_db[campaign_id]

            # Get detailed call information for each call
            calls_with_details = []
            total_duration = 0
            status_counts = {
                'confirmed': 0,
                'cancelled': 0,
                'rescheduled': 0,
                'busy': 0,
                'voicemail': 0,
                'completed': 0,
                'failed': 0
            }

            for result in campaign_results['results']:
                call_details = {
                    'patient_name': result['patient_name'],
                    'phone_number': result['phone_number'],
                    'success': result['success'],
                    'error': result.get('error'),
                    'call_id': result.get('call_id'),
                    'transcript': None,
                    'duration': 0,
                    'created_at': campaign_results['started_at']
                }

                # If call was successful and has call_id, try to get detailed info
                if result['success'] and result.get('call_id'):
                    try:
                        call_response = requests.get(
                            f"https://api.bland.ai/v1/calls/{result['call_id']}",
                            headers={"Authorization": f"Bearer {api_key}"},
                            timeout=10
                        )

                        if call_response.status_code == 200:
                            call_data = call_response.json()
                            call_details['transcript'] = call_data.get('transcript', '')
                            call_details['duration'] = call_data.get('duration', 0)
                            call_details['created_at'] = call_data.get('created_at', campaign_results['started_at'])

                            # Add to total duration
                            total_duration += call_details['duration']

                            # Analyze transcript for status and set call_details status
                            transcript = call_details['transcript'].lower() if call_details['transcript'] else ''
                            if any(word in transcript for word in ["confirm", "yes", "see you then", "i'll be there"]):
                                call_details['call_status'] = 'confirmed'
                                status_counts['confirmed'] += 1
                            elif any(word in transcript for word in ["reschedule", "different time", "change"]):
                                call_details['call_status'] = 'rescheduled'
                                status_counts['rescheduled'] += 1
                            elif any(word in transcript for word in ["cancel", "can't make it", "won't be available"]):
                                call_details['call_status'] = 'cancelled'
                                status_counts['cancelled'] += 1
                            elif "voicemail" in transcript or "leave a message" in transcript:
                                call_details['call_status'] = 'voicemail'
                                status_counts['voicemail'] += 1
                            elif any(word in transcript for word in ["busy", "hang up", "ended call"]):
                                call_details['call_status'] = 'busy'
                                status_counts['busy'] += 1
                            else:
                                call_details['call_status'] = 'completed'
                                status_counts['completed'] += 1
                        else:
                            call_details['call_status'] = 'failed'
                            status_counts['failed'] += 1
                    except Exception as e:
                        # If we can't get call details, count as failed
                        call_details['call_status'] = 'failed'
                        status_counts['failed'] += 1
                        print(f"Error getting call details for {result.get('call_id')}: {str(e)}")
                else:
                    # Failed calls count as failed
                    call_details['call_status'] = 'failed'
                    status_counts['failed'] += 1

                calls_with_details.append(call_details)

            # Calculate analytics
            total_calls = len(campaign_results['results'])
            successful_calls = sum(1 for call in calls_with_details if call['success'])
            success_rate = round((successful_calls / total_calls * 100) if total_calls > 0 else 0, 1)

            analytics = {
                'total_calls': total_calls,
                'total_duration': total_duration,
                'campaign_runs': 1,  # For now, each entry represents one run
                'success_rate': success_rate,
                'status_counts': status_counts,
                'calls': calls_with_details
            }

            return {
                "success": True,
                "campaign_id": campaign_id,
                "campaign_name": campaign_results['campaign_name'],
                "analytics": analytics
            }
        else:
            return {
                "success": False,
                "message": "No analytics data available for this campaign"
            }

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Error fetching campaign analytics: {str(e)}")


@app.get("/call_details/{call_id}")
async def get_call_details(call_id: str):
    """Get detailed call information including transcript"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(status_code=400,
                            detail="BLAND_API_KEY not found in Secrets.")

    try:
        response = requests.get(f"https://api.bland.ai/v1/calls/{call_id}",
                                headers={
                                    "Authorization": f"Bearer {api_key}",
                                })

        if response.status_code == 200:
            call_data = response.json()

            # Determine call status based on transcript analysis
            transcript = call_data.get("transcript", "")
            call_status = "unknown"

            if transcript:
                transcript_lower = transcript.lower()
                if any(word in transcript_lower for word in
                       ["confirm", "yes", "see you then", "i'll be there"]):
                    call_status = "confirmed"
                elif any(word in transcript_lower for word in
                         ["reschedule", "different time", "change"]):
                    call_status = "rescheduled"
                elif any(word in transcript_lower for word in
                         ["cancel", "can't make it", "won't be available"]):
                    call_status = "cancelled"
                elif "voicemail" in transcript_lower or "leave a message" in transcript_lower:
                    call_status = "voicemail"
                elif any(word in transcript_lower
                         for word in ["busy", "hang up", "ended call"]):
                    call_status = "busy"

            return {
                "call_id": call_id,
                "status": call_data.get("status", "unknown"),
                "call_status": call_status,
                "transcript": transcript,
                "duration": call_data.get("duration", 0),
                "created_at": call_data.get("created_at", ""),
                "phone_number": call_data.get("phone_number", ""),
            }
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to get call details: {response.text}")
    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Error fetching call details: {str(e)}")


@app.get("/docs")
async def get_docs():
    """Access FastAPI automatic documentation"""
    return {"message": "Visit /docs for interactive API documentation"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)