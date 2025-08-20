from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

# Assume these functions are defined elsewhere and handle data loading and API key retrieval
# For demonstration purposes, they are defined here with placeholder logic:
def load_clients():
    # Placeholder for loading clients
    return [{"id": "client1", "name": "Client A"}, {"id": "client2", "name": "Client B"}]

def load_campaigns():
    # Placeholder for loading campaigns, including potentially problematic data
    return [
        {"id": "camp1", "name": "Campaign One", "client_id": "client1", "file_data": b"binary_content_1"},
        {"id": "camp2", "name": "Campaign Two", "client_id": "client2", "csv_data": b"csv_content_2"},
        {"id": "camp3", "name": "Campaign Three", "client_id": "client1", "file_content": b"file_content_3"},
        {"id": "camp4", "name": "Campaign Four", "client_id": "client3", "raw_data": b"raw_content_4"},
        {"id": "camp5", "name": "Campaign Five", "client_id": "client1", "description": "This is a test campaign"},
    ]

def get_api_key():
    # Placeholder for getting API key
    return "dummy_api_key"

# Initialize FastAPI app
app = FastAPI()

# Mount static files (e.g., for HTML templates)
# Assuming you have a 'static' folder with an 'index.html' and a 'campaigns.html'
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Jinja2 templates
# Assuming your templates are in a 'templates' folder
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Display the main page"""
    return templates.TemplateResponse("index.html", {"request": request})

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
            if isinstance(campaign, dict):
                campaign_copy = {}
                for key, value in campaign.items():
                    # Skip any keys that might contain bytes or file data
                    if key in ['file_data', 'csv_data', 'file_content', 'raw_data']:
                        continue
                    # Skip any values that are bytes
                    if isinstance(value, bytes):
                        continue
                    campaign_copy[key] = value
                serializable_campaigns.append(campaign_copy)
            else:
                serializable_campaigns.append(campaign)

        # Render the campaigns.html template with the processed data
        return templates.TemplateResponse("campaigns.html", {
            "request": request,
            "campaigns": serializable_campaigns,
            "clients": clients,
            "has_api_key": has_api_key,
            "selected_client_id": client_id
        })
    except Exception as e:
        # Log the error for debugging
        print(f"Error in campaigns_page: {e}")
        # Return an error response to the user
        return templates.TemplateResponse("error.html", {"request": request, "error_message": str(e)}, status_code=500)

# Example of another endpoint, if needed
@app.get("/clients", response_class=JSONResponse)
async def get_clients():
    """API endpoint to get clients"""
    return load_clients()

if __name__ == "__main__":
    import uvicorn
    # To run this: save as main.py and run `uvicorn main:app --reload`
    # Ensure you have 'templates' and 'static' folders with necessary HTML files.
    # Example template files:
    # templates/index.html, templates/campaigns.html, templates/error.html
    # static/style.css (optional)
    uvicorn.run(app, host="0.0.0.0", port=5000)