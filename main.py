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
    "Ryan": "37b3f1c8-a01e-4d70-b251-294733f08371",
    "Paige": "70f05206-71ab-4b39-b238-ed1bf17b365a",
    "Maya": "2f9fdbc7-4bf2-4792-8a18-21ce3c93978f",
    "Adriana": "1d054475-3908-4f64-9158-9d3911fe9597",
    "Destiny": "0d6a3160-e7d8-4594-9508-650ec8945ba8",
    "Mason": "90295ec4-f0fe-4783-ab33-8b997ddc3ae4",
    "Sal": "0f3e6942-5576-4d9d-8437-6c52ed7ed279"
}


def get_voice_id(name="Paige") -> str:
    """Get the voice ID for the given voice name"""
    return VOICE_MAP.get(
        name,
        VOICE_MAP["Paige"])  # Default to Paige


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
    • If someone interrupts or speaks over you, wait for them to finish, then acknowledge, answer them and then continue from where you left off
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
    E) RESCHEDULE — Explicit request to reschedule (e.g., "I'd like to reschedule", "Can we change the time?", "Let's find a new time", "Can we schedule it", "I want to schedule", "can we reschedule", "I want to reschedule", "Let's reschedule it", etc.) → Go directly to RESCHEDULE flow, do **not** route through UNSURE

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
            selected_voice = VOICE_MAP.get("Paige",
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
        selected_voice = VOICE_MAP.get("Paige",
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
    """Main dashboard interface"""
    api_key = get_api_key()

    # Load clients and campaigns data for dashboard
    clients = load_clients()
    campaigns = load_campaigns()

    # Calculate metrics
    total_clients = len(clients)
    total_campaigns = len(campaigns)

    metrics = {
        "total_clients": total_clients,
        "total_campaigns": total_campaigns,
        "total_calls": 0,
        "total_duration": "0:00"
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "has_api_key": bool(api_key),
        "metrics": metrics,
        "clients": clients,
        "campaigns": campaigns
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
    """Start a campaign using stored file or new upload with retry logic"""
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

        # Process all valid calls with retry logic
        if call_requests:
            max_attempts = campaign.get('max_attempts', 3)
            retry_interval_minutes = campaign.get('retry_interval', 30)

            print(f"🚀 Starting campaign '{campaign['name']}' with retry logic - Max attempts: {max_attempts}, Retry interval: {retry_interval_minutes} min")

            # Process calls with retry logic
            final_results = await process_calls_with_retry(
                call_requests, 
                api_key, 
                max_attempts, 
                retry_interval_minutes,
                campaign['name']
            )
            results.extend(final_results)

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


async def process_calls_with_retry(call_requests, api_key, max_attempts, retry_interval_minutes, campaign_name):
    """Process calls with retry logic and send voicemail after max attempts"""
    final_results = []

    # Track retry status for each call
    retry_tracker = {}
    for i, call_request in enumerate(call_requests):
        retry_tracker[i] = {
            'attempts': 0,
            'completed': False,
            'call_request': call_request,
            'final_result': None
        }

    # Create semaphore to limit concurrent calls
    semaphore = asyncio.Semaphore(10)

    while True:
        # Find calls that need retry attempts
        pending_calls = []
        pending_indices = []

        for i, tracker in retry_tracker.items():
            if not tracker['completed'] and tracker['attempts'] < max_attempts:
                pending_calls.append(tracker['call_request'])
                pending_indices.append(i)

        if not pending_calls:
            break  # All calls completed or exhausted retries

        current_attempt = max(retry_tracker[i]['attempts'] for i in pending_indices) + 1
        print(f"🔄 Campaign '{campaign_name}' - Starting attempt {current_attempt} for {len(pending_calls)} calls")

        # Execute current batch of calls
        tasks = [
            make_single_call_async(call_request, api_key, semaphore)
            for call_request in pending_calls
        ]

        batch_results = await asyncio.gather(*tasks)

        # Process results and check call status
        for idx, result in enumerate(batch_results):
            tracker_idx = pending_indices[idx]
            call_request = pending_calls[idx]
            retry_tracker[tracker_idx]['attempts'] += 1

            # Check if call was successful and determine actual status
            call_status = 'failed'
            if result.success and result.call_id:
                try:
                    # Wait for call to complete and get status
                    await asyncio.sleep(3)

                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://api.bland.ai/v1/calls/{result.call_id}",
                            headers={"Authorization": f"Bearer {api_key}"},
                            timeout=aiohttp.ClientTimeout(total=15)
                        ) as call_response:

                            if call_response.status == 200:
                                call_data = await call_response.json()
                                transcript = call_data.get('transcript', '')
                                call_status = analyze_call_transcript(transcript)

                                # Update result with transcript and status
                                result.transcript = transcript
                                result.call_status = call_status
                            else:
                                call_status = 'busy_voicemail'

                except Exception as e:
                    print(f"❌ Error checking call status for {call_request.patient_name}: {str(e)}")
                    call_status = 'busy_voicemail'
            else:
                call_status = 'failed'

            # Check if call is completed successfully (patient answered and responded)
            if call_status in ['confirmed', 'cancelled', 'rescheduled']:
                # Call completed successfully
                retry_tracker[tracker_idx]['completed'] = True
                retry_tracker[tracker_idx]['final_result'] = result
                print(f"✅ Call to {call_request.patient_name} completed with status: {call_status}")

            elif retry_tracker[tracker_idx]['attempts'] >= max_attempts:
                # Max attempts reached, send voicemail
                retry_tracker[tracker_idx]['completed'] = True
                retry_tracker[tracker_idx]['final_result'] = result

                print(f"📞 Max attempts ({max_attempts}) reached for {call_request.patient_name}, sending voicemail...")

                # Send voicemail after all attempts exhausted
                try:
                    await send_final_voicemail(call_request, api_key)
                    print(f"📬 Final voicemail sent to {call_request.patient_name}")
                except Exception as e:
                    print(f"❌ Error sending final voicemail to {call_request.patient_name}: {str(e)}")

            else:
                # Call needs retry
                remaining_attempts = max_attempts - retry_tracker[tracker_idx]['attempts']
                print(f"⏳ Call to {call_request.patient_name} will be retried (Status: {call_status}, Remaining attempts: {remaining_attempts})")

        # If there are more attempts needed, wait for retry interval
        pending_retries = [i for i, tracker in retry_tracker.items() 
                          if not tracker['completed'] and tracker['attempts'] < max_attempts]

        if pending_retries:
            print(f"⏰ Waiting {retry_interval_minutes} minutes before next retry attempt...")
            await asyncio.sleep(retry_interval_minutes * 60)  # Convert minutes to seconds

    # Collect all final results
    for tracker in retry_tracker.values():
        if tracker['final_result']:
            final_results.append(tracker['final_result'])

    return final_results


async def send_final_voicemail(call_request: CallRequest, api_key: str):
    """Send final voicemail using the updated template after all retry attempts"""
    try:
        selected_voice = VOICE_MAP.get("Paige", "default_voice_id")

        # Updated voicemail template as per your request
        voicemail_template = f"""
        Hi Good Morning, I am calling from Hillside Medical Group. This call is for {call_request.patient_name} to remind him/her of an upcoming appointment on {call_request.appointment_date} at {call_request.appointment_time} with {call_request.provider_name} at {call_request.office_location}. Please make sure to arrive 15 minutes prior to your appointment. Also, Please make sure to email us your insurance information ASAP so that we can get it verified and avoid any delays on the day of your appointment. If you wish to cancel or reschedule your appointment, please inform us at least 24 hours in advance to avoid cancellation charge of $25.00. For more information, you can call us back on 210-742-6555 and press the prompt that says "Appointment Setters". Thank you and have a blessed day.
        """

        payload = {
            "phone_number": call_request.phone_number,
            "task": f"You are leaving a voicemail message. Speak clearly and deliver this message: {voicemail_template.strip()}",
            "voice": selected_voice,
            "request_data": {
                "patient_name": call_request.patient_name,
                "appointment_date": call_request.appointment_date,
                "appointment_time": call_request.appointment_time,
                "provider_name": call_request.provider_name,
                "office_location": call_request.office_location,
                "message_type": "final_voicemail"
            }
        }

        print(f"🔄 Sending final voicemail to {call_request.phone_number} for {call_request.patient_name}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://api.bland.ai/v1/calls",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    resp_json = await response.json()
                    print(f"✅ Final voicemail sent successfully for {call_request.patient_name}")
                    return {
                        "success": True,
                        "call_id": resp_json.get("call_id", "N/A"),
                        "status": resp_json.get("status", "N/A"),
                        "message": "Final voicemail sent successfully",
                        "patient_name": call_request.patient_name,
                        "phone_number": call_request.phone_number
                    }
                else:
                    error_msg = f"API error (Status {response.status}): {await response.text()}"
                    print(f"❌ Error sending final voicemail for {call_request.patient_name}: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "patient_name": call_request.patient_name,
                        "phone_number": call_request.phone_number
                    }

    except Exception as e:
        print(f"💥 Exception during final voicemail sending: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "patient_name": call_request.patient_name,
            "phone_number": call_request.phone_number
        }


@app.get("/voice_preview/{voice_name}")
async def voice_preview(voice_name: str):
    """Generate voice sample using Bland AI"""
    api_key = get_api_key()
    if not api_key:
        return {"success": False, "error": "API key not configured"}

    try:
        # Use the existing VOICE_MAP to get the voice ID
        voice_id = VOICE_MAP.get(voice_name)
        if not voice_id:
            return {"success": False, "error": f"Voice '{voice_name}' not found"}

        print(f"🎤 Generating voice sample for {voice_name} (ID: {voice_id})")

        # Bland AI voice sample API endpoint
        url = f"https://api.bland.ai/v1/voices/{voice_id}/sample"

        # Sample text for preview
        sample_text = "Hello! This is a voice sample from your AI assistant. I'm here to help with your calls and appointments."

        payload = {
            "text": sample_text,
            "voice_settings": {},
            "language": "en"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={
                    "authorization": api_key,
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:

                if response.status == 200:
                    # Check content type to determine how to handle the response
                    content_type = response.headers.get('content-type', '').lower()

                    if 'audio' in content_type or 'wav' in content_type or 'mp3' in content_type:
                        # Direct audio response - convert to base64 data URL
                        audio_data = await response.read()
                        import base64

                        # Determine MIME type
                        if 'wav' in content_type:
                            mime_type = 'audio/wav'
                        elif 'mp3' in content_type:
                            mime_type = 'audio/mpeg'
                        else:
                            mime_type = 'audio/wav'  # Default to wav

                        # Create data URL
                        audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                        audio_url = f"data:{mime_type};base64,{audio_base64}"

                        print(f"✅ Voice sample audio generated for {voice_name} ({len(audio_data)} bytes)")
                        return {"success": True, "preview_url": audio_url}
                    else:
                        # JSON response with URL
                        try:
                            response_data = await response.json()

                            # Bland AI might return different response formats, handle accordingly
                            if 'audio_url' in response_data:
                                audio_url = response_data['audio_url']
                            elif 'url' in response_data:
                                audio_url = response_data['url']
                            elif 'sample_url' in response_data:
                                audio_url = response_data['sample_url']
                            else:
                                print(f"✅ Voice sample generated for {voice_name}")
                                return {"success": True, "audio_data": response_data}

                            print(f"✅ Voice sample URL generated for {voice_name}: {audio_url}")
                            return {"success": True, "preview_url": audio_url}
                        except Exception as json_error:
                            print(f"❌ Failed to parse JSON response: {json_error}")
                            return {"success": False, "error": "Invalid response format from voice API"}

                elif response.status == 404:
                    return {"success": False, "error": f"Voice ID '{voice_id}' not found in Bland AI"}
                elif response.status == 401:
                    return {"success": False, "error": "Invalid API key"}
                elif response.status == 429:
                    return {"success": False, "error": "Rate limit exceeded. Please try again later."}
                else:
                    error_text = await response.text()
                    print(f"❌ Bland AI voice sample error: Status {response.status}, Response: {error_text}")
                    return {"success": False, "error": f"API error: {error_text}"}

    except asyncio.TimeoutError:
        return {"success": False, "error": "Request timeout. Please try again."}
    except Exception as e:
        print(f"💥 Exception generating voice sample: {str(e)}")
        return {"success": False, "error": f"Error generating voice sample: {str(e)}"}


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


def analyze_call_transcript(transcript: str) -> str:
    """Analyze transcript to determine call status"""
    if not transcript or transcript.strip() == "":
        return 'busy_voicemail'

    transcript_lower = transcript.lower()

    # Check for confirmation indicators first (more specific)
    confirmation_indicators = [
        "yes, i'll be there", "yes i will be there", "yes that works", "yes that's fine",
        "confirm", "yes", "see you then", "i'll be there", "sounds good",
        "that works", "perfect", "okay", "sure", "will be there",
        "looking forward", "great", "excellent", "wonderful"
    ]

    # Check for strong confirmation patterns
    strong_confirmations = ["yes", "confirm", "i'll be there", "see you then", "that works", "sounds good"]
    if any(indicator in transcript_lower for indicator in strong_confirmations):
        # Make sure it's not a cancellation disguised as confirmation
        if not any(cancel in transcript_lower for cancel in ["cancel", "can't make it", "won't be available"]):
            return 'confirmed'

    # Check for rescheduling indicators (should come before cancellation)
    reschedule_indicators = [
        "reschedule", "different time", "change the time", "move the appointment", "another time",
        "can we schedule", "find a new time", "not that time", "different day",
        "schedule for", "what about", "how about", "prefer", "better time"
    ]
    if any(indicator in transcript_lower for indicator in reschedule_indicators):
        return 'rescheduled'

    # Check for cancellation indicators
    cancellation_indicators = [
        "cancel", "can't make it", "won't be available", "not coming",
        "unable to", "won't be able", "have to cancel", "need to cancel",
        "don't need", "no longer need"
    ]
    if any(indicator in transcript_lower for indicator in cancellation_indicators):
        return 'cancelled'

    # Check for busy/voicemail indicators
    busy_voicemail_indicators = [
        "busy", "no answer", "disconnected", "line busy", "call ended immediately",
        "hung up", "voicemail", "leave a message", "after the beep",
        "not available", "please leave", "can't come to the phone", "mailbox",
        "voice message", "recording", "dial tone"
    ]
    if any(indicator in transcript_lower for indicator in busy_voicemail_indicators):
        return 'busy_voicemail'

    # If we have a meaningful transcript but can't categorize it, mark as completed
    if len(transcript.strip()) > 10:  # At least some meaningful content
        return 'confirmed'  # Default to confirmed if we have a real conversation

    return 'busy_voicemail'


def get_voicemail_prompt(patient_name: str = "[patient name]",
        appointment_date: str = "[date]",
        appointment_time: str = "[time]",
        provider_name: str = "[provider name]",
        office_location: str = "[office location]") -> str:
    """Get the voicemail message prompt"""
    return f"""
    ROLE & PERSONA
    You are an AI voice agent leaving a voicemail message from Hillside Medical Group. You are professional, clear, and concise.

    VOICEMAIL MESSAGE
    Hi Good Morning, I am calling from Hillside Medical Group. This call is for {patient_name} to remind him/her of an upcoming appointment on {appointment_date} at {appointment_time} with {provider_name} at {office_location}. Please make sure to arrive 15 minutes prior to your appointment. Also, Please make sure to email us your insurance information ASAP so that we can get it verified and avoid any delays on the day of your appointment. If you wish to cancel or reschedule your appointment, please inform us at least 24 hours in advance to avoid cancellation charge of $25.00. For more information, you can call us back on 210-742-6555. Thank you and have a blessed day.

    DELIVERY RULES
    • Speak clearly and at a moderate pace
    • Pause briefly between sentences
    • Emphasize important information like the appointment date, time, and callback number
    • End the call after delivering the complete message
    """

async def send_automatic_voicemail(call_request: CallRequest, api_key: str):
    """Send a voicemail message to a patient, used for automatic follow-ups"""
    try:
        selected_voice = VOICE_MAP.get("Paige", "default_voice_id")

        payload = {
            "phone_number": call_request.phone_number,
            "task": get_voicemail_prompt(
                patient_name=call_request.patient_name,
                appointment_date=call_request.appointment_date,
                appointment_time=call_request.appointment_time,
                provider_name=call_request.provider_name,
                office_location=call_request.office_location
            ),
            "voice": selected_voice,
            "request_data": {
                "patient_name": call_request.patient_name,
                "appointment_date": call_request.appointment_date,
                "appointment_time": call_request.appointment_time,
                "provider_name": call_request.provider_name,
                "office_location": call_request.office_location
            }
        }

        print(f"🔄 Sending automatic voicemail to {call_request.phone_number} for {call_request.patient_name}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://api.bland.ai/v1/calls",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status == 200:
                    resp_json = await response.json()
                    print(f"✅ Automatic voicemail sent successfully for {call_request.patient_name}")
                    return {
                        "success": True,
                        "call_id": resp_json.get("call_id", "N/A"),
                        "status": resp_json.get("status", "N/A"),
                        "message": "Automatic voicemail sent successfully",
                        "patient_name": call_request.patient_name,
                        "phone_number": call_request.phone_number
                    }
                else:
                    error_msg = f"API error (Status {response.status}): {await response.text()}"
                    print(f"❌ Error sending automatic voicemail for {call_request.patient_name}: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "patient_name": call_request.patient_name,
                        "phone_number": call_request.phone_number
                    }

    except Exception as e:
        print(f"💥 Exception during automatic voicemail sending: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "patient_name": call_request.patient_name,
            "phone_number": call_request.phone_number
        }


@app.post("/send_voicemail")
async def send_voicemail(call_request: CallRequest):
    """Send a voicemail message to a patient"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="BLAND_API_KEY not found in Secrets. Please add your API key.")

    try:
        selected_voice = VOICE_MAP.get("Paige", "default_voice_id")

        payload = {
            "phone_number": call_request.phone_number,
            "task": get_voicemail_prompt(
                patient_name=call_request.patient_name,
                appointment_date=call_request.appointment_date,
                appointment_time=call_request.appointment_time,
                provider_name=call_request.provider_name,
                office_location=call_request.office_location
            ),
            "voice": selected_voice,
            "request_data": {
                "patient_name": call_request.patient_name,
                "appointment_date": call_request.appointment_date,
                "appointment_time": call_request.appointment_time,
                "provider_name": call_request.provider_name,
                "office_location": call_request.office_location
            }
        }

        print(f"🔄 Sending voicemail to {call_request.phone_number} for {call_request.patient_name}")

        response = requests.post(
            "https://api.bland.ai/v1/calls",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            resp_json = response.json()
            print(f"✅ Voicemail sent successfully for {call_request.patient_name}")
            return {
                "success": True,
                "call_id": resp_json.get("call_id", "N/A"),
                "status": resp_json.get("status", "N/A"),
                "message": "Voicemail sent successfully",
                "patient_name": call_request.patient_name,
                "phone_number": call_request.phone_number
            }
        else:
            error_msg = f"API error (Status {response.status_code}): {response.text}"
            print(f"❌ Error sending voicemail for {call_request.patient_name}: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "patient_name": call_request.patient_name,
                "phone_number": call_request.phone_number
            }

    except Exception as e:
        print(f"💥 Exception during voicemail sending: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "patient_name": call_request.patient_name,
            "phone_number": call_request.phone_number
        }


@app.get("/campaign_analytics/{campaign_id}")
async def get_campaign_analytics(campaign_id: str):
    """Get campaign analytics including performance metrics and call details"""
    api_key = get_api_key()

    if not api_key:
        raise HTTPException(status_code=400,
                            detail="BLAND_API_KEY not found in Secrets.")

    try:
        # Get campaign details
        if campaign_id not in campaigns_db:
            print(f"❌ Campaign {campaign_id} not found in campaigns_db")
            return {
                "success": False,
                "message": "Campaign not found"
            }

        campaign = campaigns_db[campaign_id]
        campaign_name = campaign.get('name', 'Unknown Campaign')
        print(f"🔍 Looking for analytics for campaign: {campaign_name} (ID: {campaign_id})")

        # First, try to get results from stored campaign results
        if campaign_id in campaign_results_db:
            campaign_results = campaign_results_db[campaign_id]
            print(f"📊 Found stored results for campaign {campaign_name} with {len(campaign_results.get('results', []))} calls")
        else:
            print(f"🔍 No stored results found for campaign {campaign_name}. Available campaigns in results_db: {list(campaign_results_db.keys())}")
            
            # If no stored results, return empty analytics structure
            return {
                "success": True,
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "analytics": {
                    'total_calls': 0,
                    'total_duration': 0,
                    'formatted_duration': "0s",
                    'campaign_runs': 0,
                    'success_rate': 0,
                    'status_counts': {
                        'confirmed': 0,
                        'cancelled': 0,
                        'rescheduled': 0,
                        'busy_voicemail': 0,
                        'completed': 0,
                        'failed': 0
                    },
                    'calls': []
                }
            }

        # Get detailed call information for each call
        calls_with_details = []
        total_duration = 0
        status_counts = {
            'confirmed': 0,
            'cancelled': 0,
            'rescheduled': 0,
            'busy_voicemail': 0,
            'completed': 0,
            'failed': 0
        }

        print(f"🔍 Processing {len(campaign_results['results'])} calls for analytics")

        for result in campaign_results['results']:
            call_details = {
                'patient_name': result.get('patient_name', 'Unknown'),
                'phone_number': result.get('phone_number', 'Unknown'),
                'success': result.get('success', False),
                'error': result.get('error'),
                'call_id': result.get('call_id'),
                'transcript': None,
                'duration': 0,
                'call_status': 'failed',
                'created_at': campaign_results.get('started_at', datetime.now().isoformat())
            }

            # If call was successful and has call_id, try to get detailed info
            if result.get('success') and result.get('call_id'):
                try:
                    print(f"🔍 Fetching call details for call_id: {result.get('call_id')}")
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://api.bland.ai/v1/calls/{result['call_id']}",
                            headers={"Authorization": f"Bearer {api_key}"},
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as call_response:

                            if call_response.status == 200:
                                call_data = await call_response.json()

                                # Get transcript and other details
                                transcript = call_data.get('transcript', '')
                                call_details['transcript'] = transcript
                                call_details['created_at'] = call_data.get('created_at', call_details['created_at'])

                                # Parse duration more robustly
                                raw_duration = call_data.get('duration', 0)
                                duration_seconds = 0

                                if isinstance(raw_duration, (int, float)):
                                    duration_seconds = int(raw_duration)
                                elif isinstance(raw_duration, str) and raw_duration:
                                    try:
                                        # Handle various duration formats
                                        duration_str = raw_duration.lower().strip()
                                        if 'm' in duration_str and 's' in duration_str:
                                            # Format: "2m 30s" or "2m30s"
                                            import re
                                            match = re.search(r'(\d+)m\s*(\d+)?s?', duration_str)
                                            if match:
                                                minutes = int(match.group(1))
                                                seconds = int(match.group(2)) if match.group(2) else 0
                                                duration_seconds = minutes * 60 + seconds
                                        elif 's' in duration_str:
                                            # Format: "150s"
                                            duration_seconds = int(duration_str.replace('s', ''))
                                        elif 'm' in duration_str:
                                            # Format: "2m"
                                            duration_seconds = int(duration_str.replace('m', '')) * 60
                                        elif duration_str.isdigit():
                                            # Just a number, assume seconds
                                            duration_seconds = int(duration_str)
                                    except Exception as e:
                                        print(f"⚠️ Could not parse duration '{raw_duration}': {e}")
                                        duration_seconds = 0

                                call_details['duration'] = duration_seconds
                                total_duration += duration_seconds

                                # Analyze transcript for status using our improved function
                                call_status = analyze_call_transcript(transcript)
                                call_details['call_status'] = call_status

                                # Handle legacy 'busy' status by converting to 'busy_voicemail'
                                if call_status == 'busy':
                                    call_status = 'busy_voicemail'
                                    call_details['call_status'] = 'busy_voicemail'

                                # Make sure the status exists in our counts dictionary
                                if call_status in status_counts:
                                    status_counts[call_status] += 1
                                else:
                                    # Fallback for unexpected statuses
                                    status_counts['busy_voicemail'] += 1
                                    call_details['call_status'] = 'busy_voicemail'

                                print(f"✅ Call details retrieved for {call_details['patient_name']}: Status={call_details['call_status']}, Duration={duration_seconds}s, Transcript length={len(transcript)}")
                            else:
                                response_text = await call_response.text()
                                print(f"❌ Failed to get call details: Status {call_response.status}, Response: {response_text}")
                                call_details['call_status'] = 'failed'
                                status_counts['failed'] += 1

                except Exception as e:
                    # If we can't get call details, count as failed
                    call_details['call_status'] = 'failed'
                    status_counts['failed'] += 1
                    print(f"❌ Error getting call details for {result.get('call_id')}: {str(e)}")
            else:
                # Failed calls count as busy_voicemail (no connection made)
                call_details['call_status'] = 'busy_voicemail'
                status_counts['busy_voicemail'] += 1

            calls_with_details.append(call_details)

        # Calculate analytics
        total_calls = len(campaign_results['results'])
        successful_calls = sum(1 for call in calls_with_details if call.get('success'))
        success_rate = round((successful_calls / total_calls * 100) if total_calls > 0 else 0, 1)

        # Format total duration
        hours = total_duration // 3600
        minutes = (total_duration % 3600) // 60
        seconds = total_duration % 60
        formatted_duration = f"{hours}h {minutes}m {seconds}s"

        analytics = {
            'total_calls': total_calls,
            'total_duration': total_duration,
            'formatted_duration': formatted_duration,
            'campaign_runs': 1,  # For now, each entry represents one run
            'success_rate': success_rate,
            'status_counts': status_counts,
            'calls': calls_with_details
        }

        print(f"📊 Analytics generated: {total_calls} calls, {len([c for c in calls_with_details if c.get('transcript')])} with transcripts")

        return {
            "success": True,
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
            "analytics": analytics
        }

    except Exception as e:
        print(f"❌ Error in campaign analytics: {str(e)}")
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
                                },
                                timeout=15)

        if response.status_code == 200:
            call_data = response.json()

            # Use our improved transcript analysis function
            transcript = call_data.get("transcript", "")
            call_status = analyze_call_transcript(transcript)

            # Handle duration formatting consistently
            raw_duration = call_data.get("duration", 0)
            duration = 0

            if isinstance(raw_duration, (int, float)):
                duration = int(raw_duration)
            elif isinstance(raw_duration, str) and raw_duration:
                try:
                    duration_str = raw_duration.lower().strip()
                    if 'm' in duration_str and 's' in duration_str:
                        # Format: "2m 30s" or "2m30s"
                        import re
                        match = re.search(r'(\d+)m\s*(\d+)?s?', duration_str)
                        if match:
                            minutes = int(match.group(1))
                            seconds = int(match.group(2)) if match.group(2) else 0
                            duration = minutes * 60 + seconds
                    elif 's' in duration_str:
                        # Format: "150s"
                        duration = int(duration_str.replace('s', ''))
                    elif 'm' in duration_str:
                        # Format: "2m"
                        duration = int(duration_str.replace('m', '')) * 60
                    elif duration_str.isdigit():
                        # Just a number, assume seconds
                        duration = int(duration_str)
                except Exception as e:
                    print(f"⚠️ Could not parse duration '{raw_duration}': {e}")
                    duration = 0

            return {
                "call_id": call_id,
                "status": call_data.get("status", "unknown"),
                "call_status": call_status,
                "transcript": transcript,
                "duration": duration,
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


@app.get("/api/clients")
async def get_clients_api():
    """Get all clients data for API usage"""
    try:
        clients = list(clients_db.values())
        return {
            "success": True,
            "clients": clients
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error loading clients: {str(e)}"
        }

@app.get("/api/campaigns")
async def get_campaigns_api():
    """Get all campaigns data for API usage"""
    try:
        campaigns = []
        for campaign in campaigns_db.values():
            # Create a copy without file data for API response
            campaign_copy = campaign.copy()
            if 'file_data' in campaign_copy:
                del campaign_copy['file_data']
            campaigns.append(campaign_copy)

        return {
            "success": True,
            "campaigns": campaigns
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error loading campaigns: {str(e)}"
        }

@app.get("/docs")
async def get_docs():
    """Access FastAPI automatic documentation"""
    return {"message": "Visit /docs for interactive API documentation"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)