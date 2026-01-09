from __future__ import annotations
import os
import json
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    import gspread
    from google.oauth2.credentials import Credentials
except Exception:
    gspread = None
    Credentials = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_connection_settings = None

def _get_access_token() -> str:
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
    if not gspread:
        raise RuntimeError("Missing dependency. Run: pip install gspread google-auth")
    
    access_token = _get_access_token()
    creds = Credentials(token=access_token, scopes=SCOPES)
    return gspread.authorize(creds)

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
