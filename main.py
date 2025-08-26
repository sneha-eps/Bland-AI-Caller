import os
import sys
import requests
import csv
import io
import json
import pandas as pd
import time
import asyncio
import aiohttp
import uuid
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Depends, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import importlib
import importlib.util
import re
import hashlib
import secrets

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
campaign_logs = {}



# File paths for persistent storage
USERS_FILE = "data/users.json"
SESSIONS_FILE = "data/sessions.json"
CLIENTS_FILE = "data/clients.json"
CAMPAIGNS_FILE = "data/campaigns.json"
CAMPAIGN_RESULTS_FILE = "data/campaign_results.json"

def ensure_data_directory():
    """Ensure data directory exists"""
    os.makedirs("data", exist_ok=True)

def load_users_db():
    """Load users from file or create default users"""
    ensure_data_directory()
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Default users if file doesn't exist or is corrupted
    default_users = {
        "admin": {
            "id": "admin",
            "username": "admin",
            "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
            "role": "admin",
            "email": "admin@company.com",
            "created_at": datetime.now().isoformat()
        },
        "user": {
            "id": "user",
            "username": "user",
            "password_hash": hashlib.sha256("user123".encode()).hexdigest(),
            "role": "user",
            "email": "user@company.com",
            "created_at": datetime.now().isoformat()
        }
    }
    save_users_db(default_users)
    return default_users

def save_users_db(users_data):
    """Save users to file"""
    ensure_data_directory()
    with open(USERS_FILE, 'w') as f:
        json.dump(users_data, f, indent=2)

def load_sessions_db():
    """Load sessions from file"""
    ensure_data_directory()
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, 'r') as f:
                sessions_data = json.load(f)
                # Convert datetime strings back to datetime objects and clean expired sessions
                current_time = datetime.now()
                valid_sessions = {}
                for token, session in sessions_data.items():
                    try:
                        expires_at = datetime.fromisoformat(session['expires_at'])
                        if expires_at > current_time:
                            session['created_at'] = datetime.fromisoformat(session['created_at'])
                            session['expires_at'] = expires_at
                            valid_sessions[token] = session
                    except (KeyError, ValueError):
                        continue
                return valid_sessions
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_sessions_db(sessions_data):
    """Save sessions to file"""
    ensure_data_directory()
    # Convert datetime objects to strings for JSON serialization
    serializable_sessions = {}
    for token, session in sessions_data.items():
        serializable_sessions[token] = {
            "user_id": session["user_id"],
            "created_at": session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"],
            "expires_at": session["expires_at"].isoformat() if isinstance(session["expires_at"], datetime) else session["expires_at"]
        }

    with open(SESSIONS_FILE, 'w') as f:
        json.dump(serializable_sessions, f, indent=2)

def load_clients_db():
    """Load clients from file"""
    ensure_data_directory()
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_clients_db(clients_data):
    """Save clients to file"""
    ensure_data_directory()
    with open(CLIENTS_FILE, 'w') as f:
        json.dump(clients_data, f, indent=2)

def load_campaigns_db():
    """Load campaigns from file"""
    ensure_data_directory()
    if os.path.exists(CAMPAIGNS_FILE):
        try:
            with open(CAMPAIGNS_FILE, 'r') as f:
                campaigns_data = json.load(f)
                # Convert base64 file data back to bytes
                for campaign in campaigns_data.values():
                    if 'file_data_b64' in campaign:
                        import base64
                        campaign['file_data'] = base64.b64decode(campaign['file_data_b64'])
                        del campaign['file_data_b64']
                return campaigns_data
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_campaigns_db(campaigns_data):
    """Save campaigns to file"""
    ensure_data_directory()
    # Convert bytes to base64 for JSON serialization
    serializable_campaigns = {}
    for campaign_id, campaign in campaigns_data.items():
        campaign_copy = campaign.copy()
        if 'file_data' in campaign_copy and isinstance(campaign_copy['file_data'], bytes):
            import base64
            campaign_copy['file_data_b64'] = base64.b64encode(campaign_copy['file_data']).decode('utf-8')
            del campaign_copy['file_data']
        serializable_campaigns[campaign_id] = campaign_copy

    with open(CAMPAIGNS_FILE, 'w') as f:
        json.dump(serializable_campaigns, f, indent=2)

def load_campaign_results_db():
    """Load campaign results from file"""
    ensure_data_directory()
    if os.path.exists(CAMPAIGN_RESULTS_FILE):
        try:
            with open(CAMPAIGN_RESULTS_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def save_campaign_results_db(results_data):
    """Save campaign results to file"""
    ensure_data_directory()
    with open(CAMPAIGN_RESULTS_FILE, 'w') as f:
        json.dump(results_data, f, indent=2)

# Initialize databases from persistent storage
users_db = load_users_db()
sessions_db = load_sessions_db()
clients_db = load_clients_db()
campaigns_db = load_campaigns_db()
campaign_results_db = load_campaign_results_db()

print(f"✅ Loaded {len(users_db)} users, {len(sessions_db)} sessions, {len(clients_db)} clients, {len(campaigns_db)} campaigns, {len(campaign_results_db)} campaign results from persistent storage")

security = HTTPBasic()

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


def get_voice_id(name) -> str:
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

    FINAL SUMMARY RULE:
    • Before the call ends, always provide a short summary of the outcome of the conversation:
        – If appointment was CONFIRMED: say "Just to confirm, your appointment on {appointment_date} at {appointment_time} with {provider_name} at {office_location} is confirmed."
        – If appointment was CANCELLED: say "Just to confirm, your appointment on {appointment_date} at {appointment_time} with {provider_name} has been cancelled."
        – If appointment will be RESCHEDULED: say "Just to confirm, your appointment will be rescheduled and our scheduling agent will call you soon to arrange a new time."
    • Deliver this summary immediately before the goodbye phrase (e.g., "Have a great day!") so the patient leaves with a clear understanding.

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
    final_summary: Optional[str] = None # Added for final summary
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

class UserCreate(BaseModel):
    username: str
    password: str
    email: str
    role: str = "user"

class UserLogin(BaseModel):
    username: str
    password: str


def hash_password(password: str) -> str:
    """Hash a password for storage"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    return hashlib.sha256(password.encode()).hexdigest() == hashed

def create_session(user_id: str) -> str:
    """Create a new session token"""
    session_token = secrets.token_urlsafe(32)
    sessions_db[session_token] = {
        "user_id": user_id,
        "created_at": datetime.now(),
        "expires_at": datetime.now() + timedelta(hours=24)
    }
    save_sessions_db(sessions_db)
    return session_token

def get_current_user(request: Request) -> Optional[Dict]:
    """Get the current user from session"""
    # Check for session cookie
    session_token = request.cookies.get("session_token")
    if not session_token or session_token not in sessions_db:
        return None

    session = sessions_db[session_token]
    if datetime.now() > session["expires_at"]:
        del sessions_db[session_token]
        return None

    user_id = session["user_id"]
    return users_db.get(user_id)

def require_auth(request: Request):
    """Require authentication"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user

def require_admin(request: Request):
    """Require admin role"""
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

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


def parse_duration(raw_duration):
    """Parse duration from various formats to seconds"""
    if isinstance(raw_duration, (int, float)):
        return int(raw_duration)
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
                    return minutes * 60 + seconds
            elif 's' in duration_str:
                # Format: "150s"
                return int(duration_str.replace('s', ''))
            elif 'm' in duration_str:
                # Format: "2m"
                return int(duration_str.replace('m', '')) * 60
            elif duration_str.isdigit():
                # Just a number, assume seconds
                return int(duration_str)
        except Exception:
            return 0
    return 0

def format_duration_display(total_duration_seconds):
    """Format duration in seconds to display format"""
    hours = total_duration_seconds // 3600
    minutes = (total_duration_seconds % 3600) // 60
    seconds = total_duration_seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


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
                            f"⏳ Rate limit hit for {call_request.patient_name}, applying 10-second backoff..."
                        )
                        await asyncio.sleep(10)  # 10-second backoff for rate limits
                        return CallResult(
                            success=False,
                            error=
                            "Rate limit exceeded - applied backoff, will retry",
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
                f"⏳ Rate limit hit for {call_request.patient_name}, applying 10-second backoff..."
            )
            time.sleep(10)  # 10-second backoff for rate limits
            return CallResult(
                success=False,
                error=f"Rate limit exceeded - applied backoff, will retry",
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

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    # Check if user is already logged in
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    """Signup page"""
    # Check if user is already logged in
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("signup.html", {"request": request})

@app.post("/api/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Handle login"""
    try:
        user = None
        for user_data in users_db.values():
            if user_data["username"] == username:
                user = user_data
                break

        if not user or not verify_password(password, user["password_hash"]):
            return {"success": False, "message": "Invalid username or password"}

        # Create session
        session_token = create_session(user["id"])

        # Create response with session cookie
        from fastapi.responses import JSONResponse
        response_data = {"success": True, "message": "Login successful", "redirect_url": "/"}
        response = JSONResponse(content=response_data)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=24 * 60 * 60  # 24 hours
        )
        return response
    except Exception as e:
        return {"success": False, "message": f"Login error: {str(e)}"}

@app.post("/api/signup")
async def signup(request: Request, user_data: UserCreate):
    """Handle signup"""
    try:
        # Check if username already exists
        for existing_user in users_db.values():
            if existing_user["username"] == user_data.username:
                return {"success": False, "message": "Username already exists"}

        # Create new user
        user_id = str(uuid.uuid4())
        new_user = {
            "id": user_id,
            "username": user_data.username,
            "password_hash": hash_password(user_data.password),
            "role": user_data.role,
            "email": user_data.email,
            "created_at": datetime.now().isoformat()
        }

        users_db[user_id] = new_user
        save_users_db(users_db)

        # Create session
        session_token = create_session(user_id)

        # Create response with session cookie
        from fastapi.responses import JSONResponse
        response_data = {"success": True, "message": "Account created successfully", "redirect_url": "/"}
        response = JSONResponse(content=response_data)
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite="lax",
            max_age=24 * 60 * 60  # 24 hours
        )
        return response
    except Exception as e:
        return {"success": False, "message": f"Signup error: {str(e)}"}

@app.post("/api/logout")
async def logout(request: Request):
    """Handle logout"""
    session_token = request.cookies.get("session_token")
    if session_token and session_token in sessions_db:
        del sessions_db[session_token]
        save_sessions_db(sessions_db)

    # Create response that clears the session cookie
    from fastapi.responses import JSONResponse
    response = JSONResponse(content={"success": True, "message": "Logged out successfully"})
    response.delete_cookie(key="session_token", httponly=True, samesite="lax")
    return response

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard interface"""
    # Check authentication
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    api_key = get_api_key()

    # Load clients and campaigns data for dashboard
    clients = load_clients()
    campaigns = load_campaigns()

    # Calculate metrics from actual campaign results
    total_clients = len(clients)
    total_campaigns = len(campaigns)
    total_calls = 0
    total_duration_seconds = 0

    # Aggregate data from all campaign results (including CSV uploads)
    for campaign_id, campaign_results in campaign_results_db.items():
        if 'results' in campaign_results:
            total_calls += len(campaign_results['results'])

            # Calculate duration from individual call results if available
            for result in campaign_results['results']:
                if result.get('success'):
                    total_duration_seconds += 60  # Estimate 1 minute per successful call

    # Format total duration
    formatted_duration = format_duration_display(total_duration_seconds)

    metrics = {
        "total_clients": total_clients,
        "total_campaigns": total_campaigns,
        "total_calls": total_calls,
        "total_duration": formatted_duration
    }

    print(f"📊 Dashboard metrics calculated: {metrics}")
    print(f"📊 Available campaign results: {list(campaign_results_db.keys())}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "has_api_key": bool(api_key),
        "metrics": metrics,
        "clients": clients,
        "campaigns": campaigns,
        "current_user": user
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
    user = require_auth(request)
    api_key = get_api_key()
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "has_api_key": bool(api_key),
        "clients": list(clients_db.values()),
        "current_user": user
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
        user = require_auth(request)
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
            "filtered_client_name": client_name,
            "current_user": user
        })
    except Exception as e:
        print(f"Error in campaigns_page: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading campaigns page: {str(e)}")


@app.post("/add_client")
async def add_client(request: Request, client: Client):
    """Add a new client (admin only)"""
    user = require_admin(request)
    client_id = str(uuid.uuid4())
    client.id = client_id
    clients_db[client_id] = client.dict()
    save_clients_db(clients_db)
    return {"success": True, "client_id": client_id, "message": "Client added successfully"}

@app.get("/api/users")
async def get_users(request: Request):
    """Get all users (admin only)"""
    user = require_admin(request)
    users_list = []
    for user_data in users_db.values():
        user_copy = user_data.copy()
        del user_copy["password_hash"]  # Don't return password hashes
        users_list.append(user_copy)
    return {"success": True, "users": users_list}


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
        save_campaigns_db(campaigns_db)
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
    save_campaigns_db(campaigns_db)
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

        # Process all valid calls with retry logic and batch delays
        if call_requests:
            max_attempts = campaign.get('max_attempts', 3)
            retry_interval_minutes = campaign.get('retry_interval', 30)

            print(f"🚀 Starting campaign '{campaign['name']}' with retry logic - Max attempts: {max_attempts}, Retry interval: {retry_interval_minutes} min")
            print(f"📊 Total calls to process: {len(call_requests)} (with international rate limit protection)")
            print(f"🌍 International rate limit protection: 2 concurrent calls, 30s batch delays, extended retry intervals")

            # Process calls with retry logic and batch delays
            final_results = await process_calls_with_retry_and_batching(
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
        save_campaign_results_db(campaign_results_db)
        print(f"✅ Stored campaign results for {campaign_id}. Total campaigns with results: {len(campaign_results_db)}")
        print(f"✅ Campaign results keys: {list(campaign_results_db.keys())}")
        print(f"✅ This campaign results: Total={len(results)}, Success={successful_calls}, Failed={failed_calls}")

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


async def process_calls_with_retry_and_batching(call_requests, api_key, max_attempts, retry_interval_minutes, campaign_name):
    """Process calls with index-based traversal and flag-based retry system"""
    print(f"🚀 Starting index-based traversal with flag-based retry system for campaign '{campaign_name}'")
    print(f"📊 Total contacts in sheet: {len(call_requests)} (Index 0 to {len(call_requests)-1})")

    # Create call tracker with index-based traversal - ALL NUMBERS START WITH success=False
    call_tracker = []
    for sheet_index, call_request in enumerate(call_requests):
        call_tracker.append({
            'sheet_index': sheet_index,  # Track original position in sheet (0 to end)
            'id': sheet_index,  # Use sheet index as ID
            'call_request': call_request,
            'success': False,  # Flag: False = needs retry/processing, True = completed successfully
            'attempts': 0,
            'max_attempts': max_attempts,
            'final_result': None,
            'call_status': 'pending',  # Initialize with pending status
            'patient_name': call_request.patient_name,
            'phone_number': call_request.phone_number,
            'processing_status': 'queued'  # queued -> processing -> completed/failed
        })
        print(f"📋 [Index {sheet_index:03d}] Initialized {call_request.patient_name} ({call_request.phone_number}) - Flag: False (needs processing)")

    print(f"📊 Sheet traversal setup complete: Index 0 → {len(call_requests)-1} with flag-based processing")

    # Status tracking
    status_counts = {
        'confirmed': 0,
        'cancelled': 0,
        'rescheduled': 0,
        'busy_voicemail': 0,
        'not_available': 0,
        'wrong_number': 0,
        'failed': 0
    }

    # Semaphore for concurrency control
    semaphore = asyncio.Semaphore(2)  # Reduced concurrency for international rate limits

    attempt_round = 0

    while True:
        attempt_round += 1

        # Get all calls that need retry (success = False and haven't exceeded max attempts)
        calls_to_retry = [
            call for call in call_tracker
            if not call['success'] and call['attempts'] < call['max_attempts']
        ]

        if not calls_to_retry:
            print(f"🎯 Flag-based retry complete! No more calls need retry.")
            break

        print(f"\n🔄 RETRY ROUND {attempt_round}: Processing {len(calls_to_retry)} calls with success=False")

        # Process calls in batches of 5 with index-based traversal for international rate limits
        batch_size = 5

        # Sort calls by sheet index to maintain traversal order
        calls_to_retry_sorted = sorted(calls_to_retry, key=lambda x: x['sheet_index'])

        for i in range(0, len(calls_to_retry_sorted), batch_size):
            batch = calls_to_retry_sorted[i:i + batch_size]
            batch_start_idx = batch[0]['sheet_index']
            batch_end_idx = batch[-1]['sheet_index']

            print(f"🔄 Processing batch {i//batch_size + 1} of {(len(calls_to_retry_sorted) + batch_size - 1)//batch_size}")
            print(f"   📍 Sheet traversal: Index [{batch_start_idx:03d}] to [{batch_end_idx:03d}] ({len(batch)} calls)")

            # Mark calls as processing
            for call_data in batch:
                call_data['processing_status'] = 'processing'

            retry_tasks = []
            for call_data in batch:
                retry_tasks.append(process_single_call_with_flag_indexed(call_data, api_key, semaphore))

            # Execute batch
            await asyncio.gather(*retry_tasks)

            # Mark completed calls
            for call_data in batch:
                if call_data['success']:
                    call_data['processing_status'] = 'completed'
                else:
                    call_data['processing_status'] = 'retry_needed'

            # Add 30-second delay between batches (except for last batch)
            if i + batch_size < len(calls_to_retry_sorted):
                print(f"⏰ Waiting 30 seconds before next batch for international rate limit protection...")
                await asyncio.sleep(30)

        # Update status counts after this round
        for call_data in call_tracker:
            if call_data['success'] and call_data['call_status']:
                status = call_data['call_status']
                if status in status_counts:
                    # Only count once per successful call
                    if status not in call_data.get('counted_statuses', set()):
                        status_counts[status] += 1
                        call_data.setdefault('counted_statuses', set()).add(status)

        # Check completion status and show flag breakdown
        successful_calls = sum(1 for call in call_tracker if call['success'])
        total_calls = len(call_tracker)
        flag_true_calls = [c for c in call_tracker if c['success']]
        flag_false_calls = [c for c in call_tracker if not c['success']]

        print(f"📊 Round {attempt_round} complete: {successful_calls}/{total_calls} calls successful")
        print(f"🏁 Flag=True (Completed): {len(flag_true_calls)} calls")
        print(f"⏳ Flag=False (Need retry): {len(flag_false_calls)} calls")

        # Show status breakdown for Flag=True calls
        if flag_true_calls:
            status_breakdown = {}
            for call in flag_true_calls:
                status = call.get('call_status', 'unknown')
                status_breakdown[status] = status_breakdown.get(status, 0) + 1
            print(f"   ✅ Completed statuses: {dict(status_breakdown)}")

        # Show remaining retries
        remaining_retries = [c for c in call_tracker if not c['success'] and c['attempts'] < c['max_attempts']]
        print(f"🔄 Calls still needing retry: {len(remaining_retries)} calls")

        # If there are more calls to retry, wait for retry interval + 2 extra minutes for international protection
        remaining_retries = [c for c in call_tracker if not c['success'] and c['attempts'] < c['max_attempts']]
        if remaining_retries:
            extended_interval = retry_interval_minutes + 2  # Add 2 extra minutes for international rate limits
            print(f"⏰ Waiting {extended_interval} minutes before next retry round (includes 2-min international protection)...")
            await asyncio.sleep(extended_interval * 60)

    # Handle calls that exhausted all attempts (send voicemail and change flag)
    exhausted_calls = [call for call in call_tracker if not call['success'] and call['attempts'] >= call['max_attempts']]
    if exhausted_calls:
        print(f"📬 Processing {len(exhausted_calls)} calls that exhausted retry attempts...")
        for call_data in exhausted_calls:
            try:
                await send_final_voicemail(call_data['call_request'], api_key)
                print(f"📬 Voicemail sent to {call_data['patient_name']}")
                # Change flag to True - voicemail sent, no more processing needed
                old_flag = call_data['success']
                call_data['success'] = True
                call_data['call_status'] = 'busy_voicemail'
                print(f"🔄 FLAG CHANGED: {call_data['patient_name']} - Flag: {old_flag} → True (voicemail sent)")
                call_data['final_result'] = CallResult(
                    success=True,
                    call_status='busy_voicemail',
                    patient_name=call_data['patient_name'],
                    phone_number=call_data['phone_number'],
                    message="Voicemail sent after max attempts"
                )
                status_counts['busy_voicemail'] += 1
            except Exception as e:
                print(f"❌ Failed to send voicemail to {call_data['patient_name']}: {str(e)}")
                # Even if voicemail fails, change flag to True - we've exhausted all attempts
                old_flag = call_data['success']
                call_data['success'] = True  # No more processing needed
                call_data['call_status'] = 'failed'
                call_data['final_result'] = CallResult(
                    success=False,
                    error=f"Failed after {call_data['attempts']} attempts",
                    patient_name=call_data['patient_name'],
                    phone_number=call_data['phone_number']
                )
                status_counts['failed'] += 1
                print(f"🔄 FLAG CHANGED: {call_data['patient_name']} - Flag: {old_flag} → True (max attempts reached)")

    # Generate final results
    final_results = []
    for call_data in call_tracker:
        if call_data['final_result']:
            final_results.append(call_data['final_result'])
        else:
            # Create a default result for calls without final_result
            final_results.append(CallResult(
                success=call_data['success'],
                call_status=call_data.get('call_status', 'unknown'),
                patient_name=call_data['patient_name'],
                phone_number=call_data['phone_number'],
                message="Processed by flag-based retry system"
            ))

    # Generate traversal summary with index statistics
    completed_indexes = [c['sheet_index'] for c in call_tracker if c['success']]
    failed_indexes = [c['sheet_index'] for c in call_tracker if not c['success']]

    print(f"\n🎯 Index-based traversal completed for '{campaign_name}'!")
    print(f"   📊 Sheet Coverage: Index 0 → {len(call_tracker)-1} (Total: {len(call_tracker)} contacts)")
    print(f"   ✅ Completed Indexes: {len(completed_indexes)} contacts")
    print(f"   ❌ Failed Indexes: {len(failed_indexes)} contacts")
    print(f"   📞 Total calls: {len(final_results)}")
    print(f"   ✅ Confirmed: {status_counts['confirmed']}")
    print(f"   ❌ Cancelled: {status_counts['cancelled']}")
    print(f"   🔄 Rescheduled: {status_counts['rescheduled']}")
    print(f"   📧 Busy/Voicemail: {status_counts['busy_voicemail']}")
    print(f"   🚫 Not Available: {status_counts['not_available']}")
    print(f"   📱 Wrong Number: {status_counts['wrong_number']}")
    print(f"   💥 Failed: {status_counts['failed']}")

    # Show index ranges for debugging
    if completed_indexes:
        print(f"   📍 Completed range: {min(completed_indexes)} - {max(completed_indexes)}")
    if failed_indexes:
        print(f"   📍 Failed range: {min(failed_indexes)} - {max(failed_indexes)}")

    return final_results


async def process_single_call_with_flag_indexed(call_data, api_key, semaphore):
    """Process a single call with index tracking and update its flag based on success"""
    call_request = call_data['call_request']
    call_data['attempts'] += 1
    sheet_index = call_data['sheet_index']

    print(f"📞 [Index {sheet_index:03d}] Attempt {call_data['attempts']}/{call_data['max_attempts']} for {call_data['patient_name']} ({call_data['phone_number']})")

    try:
        # Make the call
        result = await make_single_call_async(call_request, api_key, semaphore)

        if result.success and result.call_id:
            # Call was initiated successfully, now check the actual outcome
            await asyncio.sleep(3)  # Wait for call to process

            # Get call details to determine final status
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.bland.ai/v1/calls/{result.call_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:

                    if response.status == 200:
                        call_data_api = await response.json()
                        transcript = call_data_api.get('transcript', '')

                        if transcript and transcript.strip():
                            call_status = analyze_call_transcript(transcript)
                            final_summary = extract_final_summary(transcript)
                            print(f"📋 [Index {sheet_index:03d}] Transcript Analysis: {call_data['patient_name']}")
                            print(f"   📝 Status from transcript: {call_status}")
                            print(f"   📄 Final summary: {final_summary[:100]}{'...' if len(final_summary) > 100 else ''}")
                        else:
                            call_status = 'busy_voicemail'
                            final_summary = "No transcript available - likely voicemail or no answer"
                            print(f"📋 [Index {sheet_index:03d}] No transcript: {call_data['patient_name']} - Status: {call_status}")

                        # Update result with analysis
                        result.transcript = transcript
                        result.call_status = call_status
                        result.final_summary = final_summary

                        # Determine if this is a successful completion and change flag accordingly
                        if call_status in ['confirmed', 'cancelled', 'rescheduled', 'not_available', 'wrong_number']:
                            # These are definitive responses - change flag to True (no more retries needed)
                            old_flag = call_data['success']
                            call_data['success'] = True
                            call_data['call_status'] = call_status
                            call_data['final_result'] = result
                            print(f"🔄 [Index {sheet_index:03d}] FLAG CHANGED: {call_data['patient_name']} - Flag: {old_flag} → True - Status: {call_status}")
                            print(f"✅ [Index {sheet_index:03d}] COMPLETED: {call_data['patient_name']} - No more retries needed")
                        else:
                            # busy_voicemail or failed - keep flag as False for retry
                            call_data['success'] = False
                            call_data['call_status'] = call_status
                            print(f"🔄 [Index {sheet_index:03d}] FLAG UNCHANGED: {call_data['patient_name']} - Flag remains: False - Status: {call_status}")
                            print(f"⏳ [Index {sheet_index:03d}] RETRY NEEDED: {call_data['patient_name']} - Will retry in next round")

                    else:
                        # API error - keep success=False for retry
                        call_data['success'] = False
                        call_data['call_status'] = 'failed'
                        print(f"⏳ RETRY NEEDED (Flag=False): {call_data['patient_name']} - API Error")

        else:
            # Call initiation failed - keep flag as False for retry
            old_flag = call_data['success']
            call_data['success'] = False
            call_data['call_status'] = 'failed'
            call_data['final_result'] = result
            print(f"🔄 [Index {sheet_index:03d}] FLAG UNCHANGED: {call_data['patient_name']} - Flag remains: {old_flag} → False")
            print(f"⏳ [Index {sheet_index:03d}] RETRY NEEDED: {call_data['patient_name']} - Call initiation failed: {result.error}")

    except Exception as e:
        # Exception occurred - keep flag as False for retry
        old_flag = call_data['success']
        call_data['success'] = False
        call_data['call_status'] = 'failed'
        call_data['final_result'] = CallResult(
            success=False,
            error=str(e),
            patient_name=call_data['patient_name'],
            phone_number=call_data['phone_number']
        )
        print(f"🔄 [Index {sheet_index:03d}] FLAG UNCHANGED: {call_data['patient_name']} - Flag remains: {old_flag} → False")
        print(f"⏳ [Index {sheet_index:03d}] RETRY NEEDED: {call_data['patient_name']} - Exception: {str(e)}")

    # Extended delay for international rate limit protection
    await asyncio.sleep(3)

# Keep the original function for backward compatibility (in case it's used elsewhere)
async def process_calls_with_retry(call_requests, api_key, max_attempts, retry_interval_minutes, campaign_name):
    """Legacy function - now redirects to new batching function"""
    return await process_calls_with_retry_and_batching(call_requests, api_key, max_attempts, retry_interval_minutes, campaign_name)


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
            "voice_settings": {
                "speaking_rate" : 0.10
            },
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

        # Prepare call requests with validation
        validation_failures = []
        call_requests = []

        print(f"📋 Validating ALL {len(rows)} rows from CSV/Excel file")

        for row_index, row in enumerate(rows):
            actual_row_number = row_index + 1  # 1-based numbering for user display

            # Validate required fields
            required_fields = ['phone_number', 'patient_name', 'date', 'time', 'provider_name', 'office_location']
            missing_fields = []

            for field in required_fields:
                field_value = row.get(field)
                if field_value is None or str(field_value).strip() == '' or str(field_value).strip().lower() in ['nan', 'null']:
                    missing_fields.append(field)

            if missing_fields:
                # Create validation failure result
                validation_result = CallResult(
                    success=False,
                    error=f"Row {actual_row_number}: Missing required fields: {', '.join(missing_fields)}",
                    patient_name=str(row.get('patient_name', f'Row{actual_row_number}')),
                    phone_number=str(row.get('phone_number', 'Unknown'))
                )
                validation_failures.append(validation_result)
                print(f"❌ Row {actual_row_number} FAILED validation: {missing_fields}")
                continue

            # Valid row - prepare for calling
            phone_number_raw = row.get('phone_number', '')
            phone_number_str = str(phone_number_raw).strip()
            safe_country_code = country_code or '+1'
            formatted_phone = format_phone_number(phone_number_str, safe_country_code)

            # Create call request
            def safe_str(value):
                if value is None:
                    return ''
                value_str = str(value).strip()
                return value_str if value_str.lower() not in ['nan', 'null'] else ''

            call_request = CallRequest(
                phone_number=formatted_phone,
                patient_name=safe_str(row.get('patient_name', '')),
                provider_name=safe_str(row.get('provider_name', '')),
                appointment_date=safe_str(row.get('date', '')),
                appointment_time=safe_str(row.get('time', '')),
                office_location=safe_str(row.get('office_location', ''))
            )

            call_requests.append(call_request)
            print(f"✅ Row {actual_row_number} VALID - {call_request.patient_name} at {formatted_phone}")

        print(f"📊 Validation complete: {len(validation_failures)} failures, {len(call_requests)} valid calls")

        # Process valid calls using flag-based retry system (simplified for CSV)
        call_results = []
        if call_requests:
            print(f"📞 Processing {len(call_requests)} calls using flag-based system...")

            # For CSV uploads, we'll do a single attempt per call (no retry)
            semaphore = asyncio.Semaphore(2)  # Reduced concurrency for international rate limits

            for call_request in call_requests:
                try:
                    result = await make_single_call_async(call_request, api_key, semaphore)
                    call_results.append(result)

                    print(f"📞 Call to {call_request.patient_name}: {'SUCCESS' if result.success else 'FAILED'}")
                    if not result.success:
                        print(f"   Error: {result.error}")

                    # Increased delay to prevent international rate limiting
                    await asyncio.sleep(3)

                except Exception as e:
                    error_result = CallResult(
                        success=False,
                        error=str(e),
                        patient_name=call_request.patient_name,
                        phone_number=call_request.phone_number
                    )
                    call_results.append(error_result)
                    print(f"❌ Exception calling {call_request.patient_name}: {str(e)}")

        # Combine all results
        results = validation_failures + call_results

        print(f"\n📊 FINAL CSV PROCESSING SUMMARY:")
        print(f"   Total rows processed: {len(rows)}")
        print(f"   Validation failures: {len(validation_failures)}")
        print(f"   Valid calls processed: {len(call_requests)}")
        print(f"   Total results: {len(results)}")
        print(f"   ✅ All rows accounted for: {len(rows) == len(results)}")

        # Calculate summary
        successful_calls = sum(1 for r in results if r.success)
        failed_calls = len(results) - successful_calls

        # Store results in a format similar to campaigns so dashboard can display them
        csv_session_id = f"csv_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        csv_results = {
            "campaign_id": csv_session_id,
            "campaign_name": f"CSV Upload - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "client_name": "Direct Upload",
            "total_calls": len(results),
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "started_at": datetime.now().isoformat(),
            "results": [result.dict() for result in results]
        }

        # Store in the global results database so dashboard can show these calls
        campaign_results_db[csv_session_id] = csv_results
        save_campaign_results_db(campaign_results_db)
        print(f"✅ Stored CSV upload results with ID {csv_session_id}. Total stored campaigns: {len(campaign_results_db)}")

        return {
            "success": True,
            "total_calls": len(results),
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "results": [result.dict() for result in results],
            "session_id": csv_session_id
        }

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Error processing CSV: {str(e)}")


def extract_final_summary(transcript: str) -> str:
    """
    Extract a final summary from the call transcript.
    This function analyzes the transcript and returns a brief summary of the call outcome.
    """
    if not transcript or transcript.strip() == "":
        return "No summary available - no transcript"

    transcript_lower = transcript.lower().strip()

    # If transcript is very short, return it as is
    if len(transcript.strip()) < 50:
        return transcript.strip()

    # Look for key outcome phrases in the transcript
    if any(phrase in transcript_lower for phrase in ["appointment confirmed", "confirmed", "see you then", "will be there"]):
        return "Patient confirmed appointment"
    elif any(phrase in transcript_lower for phrase in ["cancel", "cancelled", "can't make it", "won't make it"]):
        return "Patient cancelled appointment"
    elif any(phrase in transcript_lower for phrase in ["reschedule", "different time", "change the time", "move the appointment"]):
        return "Patient requested to reschedule"
    elif any(phrase in transcript_lower for phrase in ["voicemail", "leave a message", "beep", "not available"]):
        return "Reached voicemail or patient not available"
    elif any(phrase in transcript_lower for phrase in ["wrong number", "no one by that name", "you have the wrong"]):
        return "Wrong number or patient not found"
    else:
        # Return first 150 characters as a general summary
        summary = transcript.strip()[:150]
        if len(transcript.strip()) > 150:
            summary += "..."
        return summary


def analyze_call_transcript(transcript: str) -> str:
    """
    Analyze transcript to determine final call status based on patient's ultimate decision.
    This function analyzes the entire conversation to understand the patient's final response.
    """
    if not transcript or transcript.strip() == "":
        return 'busy_voicemail'

    transcript_lower = transcript.lower().strip()

    # Check for wrong number scenarios first (highest priority)
    wrong_number_patterns = [
        "wrong number", "you have the wrong number", "this is the wrong number",
        "no one by that name", "nobody by that name", "don't know", "never heard of",
        "no such person", "no one here by that name", "nobody here by that name",
        "you must have the wrong", "this isn't", "that's not me", "i'm not",
        "who is this", "who are you looking for", "there's no", "nobody named",
        "no one named", "you must have the wrong", "i think you have the wrong"
    ]

    for pattern in wrong_number_patterns:
        if pattern in transcript_lower:
            return 'wrong_number'

    # Check for not available scenarios (second priority)
    not_available_patterns = [
        "not here right now", "isn't here", "is not here", "not available",
        "not home", "isn't home", "is not home", "out right now",
        "can't come to the phone", "cannot come to the phone", "busy right now",
        "in a meeting", "at work", "not in", "stepped out", "away from",
        "will be back", "call back later", "try calling later", "not around",
        "unavailable", "sleeping", "napping", "can you call back",
        "not a good time", "isn't a good time", "bad time"
    ]

    for pattern in not_available_patterns:
        if pattern in transcript_lower:
            return 'not_available'

    # Split transcript into sentences for better analysis
    sentences = [s.strip() for s in transcript_lower.replace('.', '|').replace('!', '|').replace('?', '|').split('|') if s.strip()]

    # Track decisions throughout the conversation (later decisions override earlier ones)
    decisions = []

    # Define more comprehensive keyword patterns
    confirmation_patterns = [
        # Direct confirmations
        "yes, i'll be there", "yes i will be there", "yes that works", "yes that's fine",
        "yes i can make it", "yes i will make it", "yes that's good", "yes sounds good",
        "i'll be there", "i will be there", "i can make it", "i will make it",
        "see you then", "see you there", "sounds good", "that works", "that's fine",
        "perfect", "great", "excellent", "wonderful", "good", "okay", "sure",
        "confirmed", "confirm", "looking forward", "will be there", "plan to be there",
        # Contextual confirmations
        "yes to confirm", "yes for confirmation", "confirming", "i confirm"
    ]

    reschedule_patterns = [
        # Direct reschedule requests
        "reschedule", "reschedule it", "reschedule this", "reschedule the appointment",
        "change the time", "change the date", "move the appointment", "different time",
        "different date", "different day", "another time", "another date", "another day",
        "can we schedule", "can we reschedule", "find a new time", "find another time",
        "not that time", "not that date", "not that day", "better time", "better date",
        "prefer", "would prefer", "i prefer", "schedule for", "what about", "how about",
        "can we do", "is there", "available", "free", "open", "works better"
    ]

    cancellation_patterns = [
        # Direct cancellations
        "cancel", "cancel it", "cancel this", "cancel the appointment", "cancel my appointment",
        "want to cancel", "need to cancel", "have to cancel", "going to cancel",
        "i'm canceling", "i'm cancelling", "canceling", "cancelling",
        # Inability to attend
        "can't make it", "cannot make it", "won't make it", "will not make it",
        "can't come", "cannot come", "won't come", "will not come",
        "can't be there", "cannot be there", "won't be there", "will not be there",
        "unable to", "not coming", "don't need", "do not need", "no longer need"
    ]

    # Analyze each sentence for decision indicators
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()

        # Check for confirmations
        for pattern in confirmation_patterns:
            if pattern in sentence:
                # Make sure it's not negated
                if not any(neg in sentence for neg in ["don't", "do not", "won't", "will not", "can't", "cannot", "no", "not"]):
                    decisions.append(('confirmed', i))
                break

        # Check for rescheduling
        for pattern in reschedule_patterns:
            if pattern in sentence:
                decisions.append(('rescheduled', i))
                break

        # Check for cancellation
        for pattern in cancellation_patterns:
            if pattern in sentence:
                decisions.append(('cancelled', i))
                break

    # If we have decisions, return the last one (final decision)
    if decisions:
        final_decision = sorted(decisions, key=lambda x: x[1])[-1][0]
        return final_decision

    # If no clear decision patterns found, analyze context more broadly

    # Check for voicemail/busy indicators
    voicemail_indicators = [
        "voicemail", "voice mail", "leave a message", "after the beep", "beep",
        "mailbox", "voice message", "recording", "automated", "please leave",
        "can't come to the phone", "not available", "busy", "no answer",
        "disconnected", "line busy", "hung up", "dial tone", "no response"
    ]

    if any(indicator in transcript_lower for indicator in voicemail_indicators):
        return 'busy_voicemail'

    # Check if conversation seems like a real interaction
    interaction_indicators = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "speaking", "this is", "who is", "what", "when", "where", "how",
        "thank you", "thanks", "sorry", "excuse me", "pardon"
    ]

    has_interaction = any(indicator in transcript_lower for indicator in interaction_indicators)

    # If we have a real conversation but no clear decision, analyze sentiment
    if has_interaction and len(transcript.strip()) > 20:
        # Look for positive vs negative sentiment in the overall response
        positive_words = ["yes", "okay", "sure", "fine", "good", "great", "perfect", "alright"]
        negative_words = ["no", "can't", "won't", "unable", "busy", "sorry", "problem"]

        positive_count = sum(1 for word in positive_words if word in transcript_lower)
        negative_count = sum(1 for word in negative_words if word in transcript_lower)

        if positive_count > negative_count:
            return 'confirmed'
        elif negative_count > positive_count:
            return 'busy_voicemail'

    # Default to busy_voicemail if we can't determine the status
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
        return {
            "success": False,
            "message": "BLAND_API_KEY not found in Secrets."
        }

    try:
        print(f"🔍 Campaign analytics requested for ID: {campaign_id}")
        print(f"📊 Available campaigns in campaigns_db: {list(campaigns_db.keys())}")
        print(f"📊 Available campaigns in results_db: {list(campaign_results_db.keys())}")

        # Get campaign details
        if campaign_id not in campaigns_db:
            print(f"❌ Campaign {campaign_id} not found in campaigns_db")
            print(f"📊 Available campaigns: {list(campaigns_db.keys())}")
            return {
                "success": False,
                "message": f"Campaign not found. Available campaigns: {len(campaigns_db)}"
            }

        campaign = campaigns_db[campaign_id]
        campaign_name = campaign.get('name', 'Unknown Campaign')
        print(f"🔍 Looking for analytics for campaign: {campaign_name} (ID: {campaign_id})")

        # Debug: Print all available campaign result IDs
        print(f"🔍 All campaign result IDs: {list(campaign_results_db.keys())}")
        print(f"🔍 Campaign ID being searched: {campaign_id}")
        print(f"🔍 Campaign ID type: {type(campaign_id)}")

        # Check if any stored results have mismatched ID types
        for stored_id in campaign_results_db.keys():
            print(f"🔍 Stored ID: {stored_id} (type: {type(stored_id)})")

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

        # Get detailed call information for each call with batch processing
        calls_with_details = []
        total_duration = 0
        status_counts = {
            'confirmed': 0,
            'cancelled': 0,
            'rescheduled': 0,
            'busy_voicemail': 0,
            'not_available': 0,
            'wrong_number': 0,
            'failed': 0
        }

        print(f"🔍 Processing {len(campaign_results['results'])} calls for analytics")

        # Process calls in batches to avoid overwhelming the API
        batch_size = 5
        results_list = campaign_results['results']

        for i in range(0, len(results_list), batch_size):
            batch = results_list[i:i + batch_size]
            batch_calls = []

            # Process each call in the batch
            for result in batch:
                call_details = {
                    'patient_name': result.get('patient_name', 'Unknown'),
                    'phone_number': result.get('phone_number', 'Unknown'),
                    'success': result.get('success', False),
                    'error': result.get('error'),
                    'call_id': result.get('call_id'),
                    'transcript': None,
                    'final_summary': None, # Added for final summary
                    'duration': 0,
                    'call_status': 'failed',
                    'created_at': campaign_results.get('started_at', datetime.now().isoformat()),
                    'analysis_notes': ''
                }

                # If call was successful and has call_id, try to get detailed info
                if result.get('success') and result.get('call_id'):
                    try:
                        print(f"🔍 Fetching call details for call_id: {result.get('call_id')}")

                        async with aiohttp.ClientSession() as session:
                            async with session.get(
                                f"https://api.bland.ai/v1/calls/{result['call_id']}",
                                headers={"Authorization": f"Bearer {api_key}"},
                                timeout=aiohttp.ClientTimeout(total=45)
                            ) as call_response:

                                if call_response.status == 200:
                                    call_data = await call_response.json()

                                    # Get transcript and other details
                                    transcript = call_data.get('transcript', '')
                                    call_length = call_data.get('call_length', call_data.get('duration', 0))

                                    # Parse duration more robustly - try multiple fields
                                    raw_duration = call_length or call_data.get('duration', 0) or call_data.get('call_duration', 0)
                                    duration_seconds = parse_duration(raw_duration)

                                    call_details['duration'] = duration_seconds
                                    total_duration += duration_seconds

                                    # Analyze transcript for status using our enhanced function
                                    if transcript and transcript.strip():
                                        call_status = analyze_call_transcript(transcript)
                                        final_summary = extract_final_summary(transcript)
                                        call_details['analysis_notes'] = f"Analyzed {len(transcript)} characters of transcript"
                                        call_details['final_summary'] = final_summary
                                    else:
                                        call_status = 'busy_voicemail'
                                        final_summary = ""
                                        call_details['analysis_notes'] = "No transcript available - likely voicemail or no answer"
                                        call_details['final_summary'] = ""

                                    # Update result with transcript and status
                                    result.transcript = transcript
                                    result.call_status = call_status
                                    result.final_summary = final_summary

                                    # Store call status in call details
                                    call_details['call_status'] = call_status
                                    call_details['transcript'] = transcript
                                    call_details['final_summary'] = final_summary

                                    # Count the status
                                    if call_status in status_counts:
                                        status_counts[call_status] += 1
                                    else:
                                        # Fallback for unexpected statuses
                                        status_counts['busy_voicemail'] += 1
                                        call_details['call_status'] = 'busy_voicemail'

                                    print(f"✅ Call details retrieved for {call_details['patient_name']}: Status={call_details['call_status']}, Duration={duration_seconds}s, Transcript length={len(transcript)}")

                                elif call_response.status == 404:
                                    print(f"⚠️ Call {result.get('call_id')} not found in Bland AI")
                                    call_details['call_status'] = 'busy_voicemail'
                                    call_details['analysis_notes'] = "Call not found in API"
                                    status_counts['busy_voicemail'] += 1
                                elif call_response.status == 429:
                                    print(f"⏳ Rate limit hit, waiting and retrying...")
                                    await asyncio.sleep(2)
                                    # Retry once
                                    async with session.get(
                                        f"https://api.bland.ai/v1/calls/{result['call_id']}",
                                        headers={"Authorization": f"Bearer {api_key}"},
                                        timeout=aiohttp.ClientTimeout(total=45)
                                    ) as retry_response:
                                        if retry_response.status == 200:
                                            call_data = await retry_response.json()
                                            transcript = call_data.get('transcript', '')
                                            call_details['transcript'] = transcript
                                            if transcript:
                                                call_status = analyze_call_transcript(transcript)
                                                call_details['call_status'] = call_status
                                                if call_status in status_counts:
                                                    status_counts[call_status] += 1
                                                else:
                                                    status_counts['busy_voicemail'] += 1
                                            else:
                                                call_details['call_status'] = 'busy_voicemail'
                                                status_counts['busy_voicemail'] += 1
                                        else:
                                            call_details['call_status'] = 'busy_voicemail'
                                            status_counts['busy_voicemail'] += 1
                                else:
                                    response_text = await call_response.text()
                                    print(f"❌ API error for call {result.get('call_id')}: Status {call_response.status}")
                                    call_details['call_status'] = 'busy_voicemail'
                                    call_details['analysis_notes'] = f"API error: {call_response.status}"
                                    status_counts['busy_voicemail'] += 1

                    except asyncio.TimeoutError:
                        print(f"⏱️ Timeout getting call details for {result.get('call_id')}")
                        call_details['call_status'] = 'busy_voicemail'
                        call_details['analysis_notes'] = "API timeout"
                        status_counts['busy_voicemail'] += 1
                    except Exception as e:
                        print(f"❌ Exception getting call details for {result.get('call_id')}: {str(e)}")
                        call_details['call_status'] = 'busy_voicemail'
                        call_details['analysis_notes'] = f"Error: {str(e)}"
                        status_counts['busy_voicemail'] += 1
                else:
                    # Failed calls or calls without call_id count as busy_voicemail
                    call_details['call_status'] = 'busy_voicemail'
                    call_details['analysis_notes'] = "Call failed or no call_id"
                    status_counts['busy_voicemail'] += 1

                batch_calls.append(call_details)

            # Add batch to main list
            calls_with_details.extend(batch_calls)

            # Increased delay between batches for international rate limiting
            if i + batch_size < len(results_list):
                await asyncio.sleep(5)

        # Calculate analytics
        total_calls = len(campaign_results['results'])
        successful_calls = sum(1 for call in calls_with_details if call.get('success'))
        success_rate = round((successful_calls / total_calls * 100) if total_calls > 0 else 0, 1)

        # Format total duration
        formatted_duration = format_duration_display(total_duration)

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
        return {
            "success": False,
            "message": f"Error fetching campaign analytics: {str(e)}"
        }


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
            final_summary = extract_final_summary(transcript) # Extract final summary

            # Handle duration formatting consistently
            raw_duration = call_data.get("duration", 0)
            duration = parse_duration(raw_duration)

            return {
                "call_id": call_id,
                "status": call_data.get("status", "unknown"),
                "call_status": call_status,
                "final_summary": final_summary, # Include final summary
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

@app.get("/debug/campaign_results")
async def debug_campaign_results():
    """Debug endpoint to check stored campaign results"""
    try:
        debug_info = {
            "total_campaigns_with_results": len(campaign_results_db),
            "campaign_ids": list(campaign_results_db.keys()),
            "campaign_details": {}
        }

        for campaign_id, results in campaign_results_db.items():
            debug_info["campaign_details"][campaign_id] = {
                "campaign_name": results.get("campaign_name", "Unknown"),
                "client_name": results.get("client_name", "Unknown"),
                "total_calls": results.get("total_calls", 0),
                "successful_calls": results.get("successful_calls", 0),
                "started_at": results.get("started_at", "Unknown"),
                "results_count": len(results.get("results", [])),
                "is_csv_upload": campaign_id.startswith("csv_upload_")
            }

        return {
            "success": True,
            "debug_info": debug_info
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/dashboard_metrics")
async def get_dashboard_metrics():
    """Get updated dashboard metrics"""
    try:
        # Calculate metrics from actual campaign results
        clients = load_clients()
        campaigns = load_campaigns()

        total_clients = len(clients)
        total_campaigns = len(campaigns)
        total_calls = 0
        total_duration_seconds = 0

        # Aggregate data from all campaign results
        for campaign_id, campaign_results in campaign_results_db.items():
            if 'results' in campaign_results:
                total_calls += len(campaign_results['results'])

                # Calculate duration from individual call results if available
                for result in campaign_results['results']:
                    if result.get('success'):
                        total_duration_seconds += 60  # Estimate 1 minute per successful call

        # Format total duration
        formatted_duration = format_duration_display(total_duration_seconds)

        return {
            "success": True,
            "metrics": {
                "total_clients": total_clients,
                "total_campaigns": total_campaigns,
                "total_calls": total_calls,
                "total_duration": formatted_duration
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error calculating metrics: {str(e)}"
        }

@app.get("/view_results/{campaign_id}")
async def view_campaign_results(campaign_id: str):
    """Simple endpoint to view campaign results for debugging"""
    try:
        if campaign_id not in campaign_results_db:
            return {
                "success": False,
                "message": f"No results found for campaign {campaign_id}",
                "available_campaigns": list(campaign_results_db.keys())
            }

        results = campaign_results_db[campaign_id]
        return {
            "success": True,
            "campaign_id": campaign_id,
            "campaign_name": results.get("campaign_name", "Unknown"),
            "total_calls": results.get("total_calls", 0),
            "successful_calls": results.get("successful_calls", 0),
            "failed_calls": results.get("failed_calls", 0),
            "started_at": results.get("started_at", "Unknown"),
            "results_summary": [
                {
                    "patient_name": r.get("patient_name", "Unknown"),
                    "success": r.get("success", False),
                    "error": r.get("error", None),
                    "call_id": r.get("call_id", None)
                }
                for r in results.get("results", [])
            ]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/bland_webhook")
async def bland_webhook(request: Request):
            """Webhook to receive Bland AI call updates"""
            try:
                data = await request.json()
                event_type = data.get("type")
                call_id = data.get("call_id")
                campaign_id = data.get("campaign_id")
                bland_status = data.get("status", "").lower()

                # Get transcript from any possible field
                transcript = (
                    data.get("transcript")
                    or data.get("call", {}).get("transcript")
                    or data.get("event", {}).get("transcript")
                )

                # Finalize only when call is completed
                if event_type == "call.completed":
                    final_summary = extract_final_summary(transcript) if transcript else ""
                    appointment_status = (
                        analyze_call_transcript(transcript) if transcript else "Unknown"
                    )

                    # If no transcript, fallback to bland status
                    if not transcript:
                        if bland_status in ["busy", "voicemail"]:
                            appointment_status = "Busy/Voicemail"

                    # Ensure campaign log exists
                    if campaign_id not in campaign_logs:
                        campaign_logs[campaign_id] = []

                    # Append new call record instead of overwriting
                    campaign_logs[campaign_id].append({
                        "call_id": call_id,
                        "status": appointment_status,
                        "summary": final_summary,
                        "transcript": transcript,
                        "duration": data.get("duration", 0),
                        "timestamp": datetime.utcnow().isoformat()
                    })

                    print(f"📞 Call completed | {appointment_status} | ID: {call_id}")

                return {"success": True}

            except Exception as e:
                print(f"💥 Webhook error: {str(e)}")
                return {"success": False, "error": str(e)}


@app.get("/docs")
async def get_docs():
    """Access FastAPI automatic documentation"""
    return {"message": "Visit /docs for interactive API documentation"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)