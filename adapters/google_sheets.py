from __future__ import annotations
import os
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import gspread
    from google.oauth2.credentials import Credentials
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
except Exception:
    gspread = None
    Credentials = None
    ServiceAccountCredentials = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_connection_settings = None
_client_cache = None

def _get_access_token() -> str:
    """Get access token from Replit connectors (for Replit deployment)"""
    global _connection_settings
    
    if _connection_settings:
        expires_at = _connection_settings.get("settings", {}).get("expires_at")
        if expires_at:
            try:
                exp_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp_time.timestamp() > datetime.now().timestamp():
                    return _connection_settings["settings"]["access_token"]
            except:
                pass
    
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")
    
    if repl_identity:
        x_replit_token = f"repl {repl_identity}"
    elif web_repl_renewal:
        x_replit_token = f"depl {web_repl_renewal}"
    else:
        raise RuntimeError("X_REPLIT_TOKEN not found for repl/depl")
    
    import urllib.request
    
    url = f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=google-sheet"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X_REPLIT_TOKEN": x_replit_token
    })
    
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
    
    items = data.get("items", [])
    if not items:
        raise RuntimeError("Google Sheets not connected. Please set up the connection first.")
    
    _connection_settings = items[0]
    settings = _connection_settings.get("settings", {})
    access_token = settings.get("access_token") or settings.get("oauth", {}).get("credentials", {}).get("access_token")
    
    if not access_token:
        raise RuntimeError("Google Sheets not connected properly. Please reconnect.")
    
    return access_token

def _get_client():
    """Get gspread client - supports both Service Account JSON and Replit connectors"""
    global _client_cache
    
    if not gspread:
        raise RuntimeError("Missing dependency. Run: pip install gspread google-auth")
    
    # Check if we have Service Account JSON in settings (for production deployment)
    try:
        from pathlib import Path
        config_dir = Path(__file__).parent.parent / "config"
        local_settings_path = config_dir / "local_settings.json"
        
        if local_settings_path.exists():
            settings = json.loads(local_settings_path.read_text(encoding="utf-8"))
            service_account_json_str = settings.get("google", {}).get("service_account_json", "").strip()
            
            if service_account_json_str:
                try:
                    # Parse the JSON string
                    service_account_info = json.loads(service_account_json_str)
                    # Create credentials from service account
                    if ServiceAccountCredentials:
                        creds = ServiceAccountCredentials.from_service_account_info(
                            service_account_info, scopes=SCOPES
                        )
                        _client_cache = gspread.authorize(creds)
                        return _client_cache
                except json.JSONDecodeError:
                    # Not valid JSON, try as file path
                    if os.path.exists(service_account_json_str):
                        if ServiceAccountCredentials:
                            creds = ServiceAccountCredentials.from_service_account_file(
                                service_account_json_str, scopes=SCOPES
                            )
                            _client_cache = gspread.authorize(creds)
                            return _client_cache
    except Exception:
        pass  # Fall through to Replit connector method
    
    # Fallback to Replit connectors (for Replit deployment)
    access_token = _get_access_token()
    if Credentials:
        creds = Credentials(token=access_token, scopes=SCOPES)
        _client_cache = gspread.authorize(creds)
        return _client_cache
    
    raise RuntimeError("Could not initialize Google Sheets client")

def read_sheet(spreadsheet_id: str, tab: str) -> List[List[Any]]:
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(tab)
    return ws.get_all_values()

def read_cell(spreadsheet_id: str, tab: str, row: int, col: int) -> str:
    """Read a single cell value"""
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(tab)
    return ws.cell(row, col).value or ""

def write_cell(spreadsheet_id: str, tab: str, row: int, col: int, value: Any, max_retries: int = 3) -> tuple:
    """Write to cell ONLY if it's empty. Returns (status, message).
    status: 'written', 'skipped', 'failed'
    Retries up to max_retries times if write fails.
    """
    import time
    
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(tab)
    
    # IRON RULE: Check if cell is empty BEFORE writing
    current_value = ws.cell(row, col).value
    if current_value and str(current_value).strip():
        # Cell already has value - DO NOT overwrite!
        return ("skipped", f"תא כבר מלא: {current_value}")
    
    # Try to write with retries
    for attempt in range(1, max_retries + 1):
        try:
            # Write to cell
            ws.update_cell(row, col, value)
            
            # VERIFY the write succeeded
            time.sleep(0.3 * attempt)  # Longer delay on retries
            verify_value = ws.cell(row, col).value
            
            if str(verify_value).strip() == str(value).strip():
                if attempt > 1:
                    return ("written", f"נכתב ואומת בהצלחה (ניסיון {attempt})")
                return ("written", "נכתב ואומת בהצלחה")
            
            # Write didn't stick - retry
            if attempt < max_retries:
                time.sleep(0.5 * attempt)  # Wait before retry
                continue
                
        except Exception as e:
            if attempt < max_retries:
                time.sleep(0.5 * attempt)
                continue
            return ("failed", f"שגיאה: {str(e)}")
    
    return ("failed", f"נכשל אחרי {max_retries} ניסיונות! ציפינו: {value}, קיבלנו: {verify_value}")
