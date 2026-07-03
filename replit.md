# Overview

This is a Bland AI Call Center application that automates phone calls for healthcare appointment confirmations. The system allows users to manage clients (healthcare practices), create calling campaigns, upload patient contact lists, and execute automated calls using the Bland AI service. It features a web-based dashboard for monitoring campaign performance and managing call results.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: FastAPI with Python 3.11
- **Architecture Pattern**: Monolithic web application (`backend/main.py`), MongoDB-backed persistence
- **API Design**: RESTful endpoints for CRUD operations on clients, campaigns, and call results
- **Authentication**: Session-based authentication with sessions stored in MongoDB (TTL-indexed, auto-expiring)
- **File Processing**: CSV/Excel file upload and processing for patient contact lists

## Frontend Architecture
- **Location**: `frontend/` (templates + static assets, served by the FastAPI app in `backend/`)
- **Template Engine**: Jinja2 templates for server-side rendering
- **Styling**: Custom CSS with theme support (light/dark mode)
- **UI Framework**: Custom responsive design with Font Awesome icons
- **Client-Side**: Vanilla JavaScript for interactive elements

## Data Storage
- **Primary Storage**: MongoDB (see `MONGO_URI`/`DB_NAME` in `.env`), one collection per entity:
  - `users`: User authentication data
  - `clients`: Healthcare client information
  - `campaigns`: Campaign configurations (uploaded file bytes stored natively)
  - `campaign_results`: Call results and analytics
  - `sessions`: User session management
- **Legacy backup**: `backend/data/*.json` - the original file-based storage, kept as a
  point-in-time backup from before the MongoDB migration; no longer read by the app.
  `backend/migrate_json_to_mongo.py` is the one-off script that performed the migration.
- **Clinic Data**: Excel/CSV files for clinic location mappings via `ClinicDataManager`,
  sourced from `backend/clinic_source_data/`

## Core Business Logic
- **Campaign Management**: Create, configure, and execute calling campaigns with retry logic
- **Call Orchestration**: Asynchronous call processing with rate limiting and international phone number support
- **Data Validation**: Phone number formatting, patient data validation, and clinic location mapping
- **Result Tracking**: Comprehensive call result logging with success/failure analytics

## Security Model
- **Authentication**: Username/password with SHA-256 password hashing
- **Session Management**: Secure token-based sessions with expiration
- **Role-Based Access**: Admin and user roles with different permissions
- **Data Protection**: Server-side validation and sanitization

# External Dependencies

## Third-Party Services
- **Bland AI API**: Core service for automated phone calls
  - Voice selection and customization
  - Call initiation and status tracking
  - Call transcription and summary generation

## Python Libraries
- **Web Framework**: FastAPI (0.104.1) with Uvicorn ASGI server
- **Data Processing**: Pandas for CSV/Excel manipulation and data analysis
- **HTTP Client**: aiohttp for asynchronous API calls to Bland AI
- **Template Rendering**: Jinja2 for HTML template generation
- **File Handling**: openpyxl for Excel file processing
- **Utilities**: pytz for timezone handling, requests for HTTP operations

## Infrastructure Requirements
- **Runtime**: Python 3.11+ environment
- **Storage**: File system access for JSON data persistence
- **Network**: Outbound HTTPS access to Bland AI API endpoints
- **File System**: Write permissions for data directory and uploaded files

## API Integrations
- **Bland AI REST API**: Primary integration for call management
- **Phone Number Processing**: International dialing code handling and validation
- **Clinic Location Services**: Excel-based clinic address lookup system