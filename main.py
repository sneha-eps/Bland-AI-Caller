
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
import pandas as pd
import json
import asyncio
import aiohttp
import io
from datetime import datetime
import csv
import openpyxl

app = FastAPI()

# Mount static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="templates")

# In-memory storage (in production, use a database)
clients_db = {}
campaigns_db = {}
campaign_results_db = {}

# Add number formatting filter
def number_format(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

templates.env.filters['number_format'] = number_format

def get_api_key():
    return os.getenv("BLAND_API_KEY")

class Client(BaseModel):
    name: str
    description: Optional[str] = None

class Campaign(BaseModel):
    name: str
    client_id: str
    max_attempts: int = 3
    retry_interval: int = 30
    country_code: str = "+1"

class CallResult(BaseModel):
    patient_name: str
    phone_number: str
    status: str
    duration: int = 0
    transcript: str = ""
    call_id: Optional[str] = None
    created_at: Optional[str] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    provider_name: Optional[str] = None
    office_location: Optional[str] = None

async def make_call_with_bland_ai(phone_number: str, patient_name: str, appointment_details: dict):
    """Make a call using Bland AI API"""
    api_key = get_api_key()
    if not api_key:
        return {"success": False, "error": "API key not configured"}
    
    # Create the script with appointment details
    script = f"""
    Hi, good morning! I'm calling from Hillside Medical Group. 
    This call is for {patient_name} to remind you of an upcoming appointment on {appointment_details.get('appointment_date', '[DATE]')} at {appointment_details.get('appointment_time', '[TIME]')} with {appointment_details.get('provider_name', '[PROVIDER]')} at {appointment_details.get('office_location', '[LOCATION]')}.
    
    Please confirm if you'll be able to attend this appointment, or if you need to reschedule or cancel.
    
    Please make sure to arrive 15 minutes prior to your appointment. Also, please make sure to email us your insurance information ASAP so that we can get it verified and avoid any delays on the day of your appointment.
    
    If you wish to cancel or reschedule your appointment, please inform us at least 24 hours in advance to avoid a cancellation charge of $25.00.
    
    For more information, you can call us back on 210-742-6555. Thank you and have a blessed day.
    """
    
    url = "https://api.bland.ai/v1/calls"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "phone_number": phone_number,
        "task": script,
        "voice": "maya",
        "language": "en-US",
        "max_duration": 300,
        "answered_by_enabled": True,
        "wait_for_greeting": True,
        "record": True,
        "amd": True
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    call_id = result.get("call_id")
                    
                    # Wait a moment then get call details
                    await asyncio.sleep(2)
                    
                    # Get call details
                    details_url = f"https://api.bland.ai/v1/calls/{call_id}"
                    async with session.get(details_url, headers=headers) as details_response:
                        if details_response.status == 200:
                            call_details = await details_response.json()
                            
                            # Analyze transcript for status
                            transcript = call_details.get("transcript", "")
                            duration = call_details.get("call_length", 0)
                            
                            status = analyze_call_status(transcript)
                            
                            return {
                                "success": True,
                                "call_id": call_id,
                                "status": status,
                                "duration": duration,
                                "transcript": transcript,
                                "patient_name": patient_name,
                                "phone_number": phone_number
                            }
                        else:
                            return {
                                "success": False,
                                "error": f"Failed to get call details: {details_response.status}",
                                "patient_name": patient_name,
                                "phone_number": phone_number
                            }
                else:
                    error_text = await response.text()
                    return {
                        "success": False,
                        "error": f"Call failed: {response.status} - {error_text}",
                        "patient_name": patient_name,
                        "phone_number": phone_number
                    }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception during call: {str(e)}",
            "patient_name": patient_name,
            "phone_number": phone_number
        }

def analyze_call_status(transcript):
    """Analyze transcript to determine call status"""
    if not transcript:
        return "busy_voicemail"
    
    transcript_lower = transcript.lower()
    
    # Check for confirmation keywords
    if any(word in transcript_lower for word in ["yes", "confirm", "will be there", "see you", "attend"]):
        return "confirmed"
    
    # Check for cancellation keywords
    if any(word in transcript_lower for word in ["cancel", "cannot make", "can't make", "won't be there"]):
        return "cancelled"
    
    # Check for rescheduling keywords
    if any(word in transcript_lower for word in ["reschedule", "different time", "another day", "change appointment"]):
        return "rescheduled"
    
    # If transcript exists but no clear intent, mark as contacted but unclear
    return "busy_voicemail"

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Display the main dashboard"""
    has_api_key = bool(get_api_key())
    
    # Calculate dashboard stats
    total_clients = len(clients_db)
    total_campaigns = len(campaigns_db)
    total_calls = sum(len(results.get("results", [])) for results in campaign_results_db.values())
    
    # Calculate success rate
    all_calls = []
    for results in campaign_results_db.values():
        all_calls.extend(results.get("results", []))
    
    successful_calls = len([call for call in all_calls if call.get("status") == "confirmed"])
    success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "has_api_key": has_api_key,
        "metrics": {
            "total_clients": total_clients,
            "total_campaigns": total_campaigns,
            "total_calls": total_calls,
            "success_rate": round(success_rate, 1)
        }
    })

@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Display the CSV upload page"""
    has_api_key = bool(get_api_key())
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "has_api_key": has_api_key
    })

@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    """Display clients page"""
    has_api_key = bool(get_api_key())
    clients_list = list(clients_db.values())
    
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients_list,
        "has_api_key": has_api_key
    })

@app.post("/add_client")
async def add_client(name: str = Form(...), description: str = Form("")):
    """Add a new client"""
    client_id = str(uuid.uuid4())
    client = {
        "id": client_id,
        "name": name,
        "description": description
    }
    clients_db[client_id] = client
    return {"success": True, "client": client}

@app.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, client_id: Optional[str] = None):
    """Display campaigns page"""
    has_api_key = bool(get_api_key())
    clients_list = list(clients_db.values())
    campaigns_list = list(campaigns_db.values())
    
    # Filter campaigns by client if specified
    if client_id:
        campaigns_list = [c for c in campaigns_list if c.get('client_id') == client_id]
        # Get client name for filtered view
        filtered_client_name = None
        for client in clients_list:
            if client['id'] == client_id:
                filtered_client_name = client['name']
                break
    else:
        filtered_client_name = None
    
    return templates.TemplateResponse("campaigns.html", {
        "request": request,
        "campaigns": campaigns_list,
        "clients": clients_list,
        "has_api_key": has_api_key,
        "selected_client_id": client_id,
        "filtered_client_name": filtered_client_name
    })

@app.post("/add_campaign")
async def add_campaign(
    name: str = Form(...),
    client_id: str = Form(...),
    max_attempts: int = Form(3),
    retry_interval: int = Form(30),
    country_code: str = Form("+1"),
    file: UploadFile = File(...)
):
    """Add a new campaign"""
    campaign_id = str(uuid.uuid4())
    
    # Process the uploaded file
    try:
        file_content = await file.read()
        
        # Parse CSV or Excel file
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.StringIO(file_content.decode('utf-8')))
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format")
        
        # Convert DataFrame to list of dictionaries
        contacts = df.to_dict('records')
        
        campaign = {
            "id": campaign_id,
            "name": name,
            "client_id": client_id,
            "max_attempts": max_attempts,
            "retry_interval": retry_interval,
            "country_code": country_code,
            "contacts": contacts,
            "created_at": datetime.now().isoformat()
        }
        
        campaigns_db[campaign_id] = campaign
        return {"success": True, "campaign": campaign}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@app.post("/start_campaign/{campaign_id}")
async def start_campaign(campaign_id: str):
    """Start a campaign and make calls"""
    if campaign_id not in campaigns_db:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="BLAND_API_KEY not found in Secrets.")
    
    campaign = campaigns_db[campaign_id]
    contacts = campaign.get("contacts", [])
    
    if not contacts:
        raise HTTPException(status_code=400, detail="No contacts found in campaign")
    
    # Make calls for each contact
    results = []
    successful_calls = 0
    failed_calls = 0
    
    for contact in contacts:
        # Extract contact information
        patient_name = str(contact.get("patient_name", contact.get("name", "Unknown")))
        phone_number = str(contact.get("phone_number", contact.get("phone", "")))
        
        if not phone_number:
            failed_calls += 1
            results.append({
                "patient_name": patient_name,
                "phone_number": "N/A",
                "status": "failed",
                "duration": 0,
                "transcript": "No phone number provided",
                "created_at": datetime.now().isoformat()
            })
            continue
        
        # Prepare appointment details
        appointment_details = {
            "appointment_date": contact.get("appointment_date", "[DATE]"),
            "appointment_time": contact.get("appointment_time", "[TIME]"),
            "provider_name": contact.get("provider_name", "[PROVIDER]"),
            "office_location": contact.get("office_location", "[LOCATION]")
        }
        
        # Make the call
        call_result = await make_call_with_bland_ai(phone_number, patient_name, appointment_details)
        
        if call_result["success"]:
            successful_calls += 1
            result_data = {
                "patient_name": patient_name,
                "phone_number": phone_number,
                "status": call_result["status"],
                "duration": call_result.get("duration", 0),
                "transcript": call_result.get("transcript", ""),
                "call_id": call_result.get("call_id"),
                "created_at": datetime.now().isoformat()
            }
        else:
            failed_calls += 1
            result_data = {
                "patient_name": patient_name,
                "phone_number": phone_number,
                "status": "failed",
                "duration": 0,
                "transcript": call_result.get("error", "Call failed"),
                "created_at": datetime.now().isoformat()
            }
        
        results.append(result_data)
        
        # Add a small delay between calls
        await asyncio.sleep(1)
    
    # Store campaign results
    campaign_results = {
        "campaign_id": campaign_id,
        "started_at": datetime.now().isoformat(),
        "total_contacts": len(contacts),
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "results": results
    }
    
    # Store in the global results database
    campaign_results_db[campaign_id] = campaign_results
    
    return {
        "success": True,
        "total_calls": len(contacts),
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "message": f"Campaign completed. {successful_calls} successful calls, {failed_calls} failed calls."
    }

@app.get("/campaign_analytics/{campaign_id}")
async def get_campaign_analytics(campaign_id: str):
    """Get analytics for a specific campaign"""
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="BLAND_API_KEY not found in Secrets.")
    
    try:
        # Get campaign results from in-memory storage
        if campaign_id in campaign_results_db:
            campaign_results = campaign_results_db[campaign_id]
            
            # Get detailed call information for each call
            calls_with_details = []
            total_duration = 0
            status_counts = {
                "confirmed": 0,
                "cancelled": 0,
                "rescheduled": 0,
                "busy_voicemail": 0
            }
            
            for call in campaign_results["results"]:
                call_data = {
                    "patient_name": call["patient_name"],
                    "phone_number": call["phone_number"],
                    "call_status": call["status"],
                    "duration": call.get("duration", 0),
                    "transcript": call.get("transcript", ""),
                    "created_at": call.get("created_at", "")
                }
                
                calls_with_details.append(call_data)
                total_duration += call.get("duration", 0)
                
                # Count statuses
                status = call["status"]
                if status in status_counts:
                    status_counts[status] += 1
                else:
                    status_counts["busy_voicemail"] += 1
            
            # Calculate analytics
            total_calls = len(calls_with_details)
            successful_calls = status_counts["confirmed"]
            success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
            
            analytics = {
                "total_calls": total_calls,
                "total_duration": total_duration,
                "campaign_runs": 1,
                "success_rate": round(success_rate, 1),
                "status_counts": status_counts,
                "calls": calls_with_details
            }
            
            return {
                "success": True,
                "analytics": analytics,
                "campaign_name": campaigns_db.get(campaign_id, {}).get("name", "Unknown Campaign")
            }
        else:
            return {
                "success": False,
                "message": "No analytics data available for this campaign"
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching analytics: {str(e)}")

@app.post("/send_voicemail")
async def send_voicemail(request: Request):
    """Send a voicemail using Bland AI"""
    api_key = get_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="BLAND_API_KEY not found in Secrets.")
    
    try:
        data = await request.json()
        
        # Create voicemail script
        script = f"""
        Hi Good Morning, I am calling from Hillside Medical Group. This call is for {data['patient_name']} to remind him/her of an upcoming appointment on {data['appointment_date']} at {data['appointment_time']} with {data['provider_name']} at {data['office_location']}. 
        
        Please make sure to arrive 15 minutes prior to your appointment. Also, Please make sure to email us your insurance information ASAP so that we can get it verified and avoid any delays on the day of your appointment. 
        
        If you wish to cancel or reschedule your appointment, please inform us at least 24 hours in advance to avoid cancellation charge of $25.00. For more information, you can call us back on 210-742-6555.
        
        Thank you and have a blessed day.
        """
        
        url = "https://api.bland.ai/v1/calls"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "phone_number": data['phone_number'],
            "task": script,
            "voice": "maya",
            "language": "en-US",
            "max_duration": 120,
            "answered_by_enabled": True,
            "voicemail_message": script
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "call_id": result.get("call_id")}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"Failed to send voicemail: {error_text}"}
                    
    except Exception as e:
        return {"success": False, "error": f"Error sending voicemail: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
