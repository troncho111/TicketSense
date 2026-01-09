from __future__ import annotations
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import queue
import threading

log_queue = queue.Queue()
stop_requested = False
is_running = False
last_results = None
resume_from_index = 0  # Track where to resume

# Persistent state and log files
STATE_DIR = Path(__file__).parent / "state"
STATE_DIR.mkdir(exist_ok=True)
PROGRESS_FILE = STATE_DIR / "progress.json"
LOG_FILE = Path(__file__).parent / "logs" / "allocation.log"
LOG_FILE.parent.mkdir(exist_ok=True)

def save_progress(last_index: int, total: int, order_number: str = ""):
    """Save current progress to file"""
    import hashlib
    state = {
        "last_index": last_index,
        "total": total,
        "last_order": order_number,
        "timestamp": datetime.now().isoformat()
    }
    PROGRESS_FILE.write_text(json.dumps(state, ensure_ascii=False))

def load_progress() -> dict:
    """Load saved progress"""
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text())
        except:
            pass
    return {"last_index": 0, "total": 0, "last_order": ""}

def clear_progress():
    """Clear saved progress"""
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()

def write_log_to_file(message: str, level: str = "info"):
    """Write log entry to persistent file"""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level.upper()}] {message}\n")

from engine.allocator import Order, Ticket, choose_tickets_for_order
from adapters.google_sheets import read_sheet, write_cell

APP_DIR = Path(__file__).parent
CONFIG_DIR = APP_DIR / "config"
LOCAL_SETTINGS = CONFIG_DIR / "local_settings.json"
LOCAL_SETTINGS_TEMPLATE = CONFIG_DIR / "local_settings.template.json"
RULES_PATH = CONFIG_DIR / "seating_rules.json"
I18N_PATH = CONFIG_DIR / "i18n.json"
MAPPING_DIR = CONFIG_DIR / "category_mapping"
HIERARCHY_PATH = CONFIG_DIR / "category_hierarchy.json"

_hierarchy_cache = None

def get_category_hierarchy():
    global _hierarchy_cache
    if _hierarchy_cache is None:
        _hierarchy_cache = load_json(HIERARCHY_PATH)
    return _hierarchy_cache

def get_category_level(category: str) -> int:
    """Get the priority level of a category (1=best, 11=worst). Returns 99 if not found."""
    hierarchy = get_category_hierarchy()
    cat_upper = category.upper().strip()
    
    for item in hierarchy["priority_order"]:
        if cat_upper == item["name"].upper():
            return item["level"]
    
    for alias, canonical in hierarchy["category_aliases"].items():
        if cat_upper == alias.upper() or category.strip() == alias:
            for item in hierarchy["priority_order"]:
                if canonical.upper() == item["name"].upper():
                    return item["level"]
    
    return 99

def get_upgrade_categories(category: str) -> List[str]:
    """Get list of categories that are upgrades (better) than the given category."""
    hierarchy = get_category_hierarchy()
    current_level = get_category_level(category)
    
    upgrades = []
    for item in hierarchy["priority_order"]:
        if item["level"] < current_level:
            upgrades.append(item["name"])
    
    return upgrades

def is_shortside_category(category: str) -> bool:
    """Check if category is a shortside (behind goal) category."""
    cat_upper = category.upper().strip()
    shortside_keywords = ["SHORT SIDE", "CATEGORY 3", "CATEGORY 4", "CAT 3", "CAT 4", "FONDO", "CATEGORÍA 3", "CATEGORÍA 4"]
    for kw in shortside_keywords:
        if kw in cat_upper:
            return True
    return False

def is_lateral_upgrade_blocked(original_category: str, upgrade_category: str) -> bool:
    """Check if upgrading from original to upgrade is blocked (shortside -> lateral)."""
    if is_shortside_category(original_category):
        if "LATERAL" in upgrade_category.upper():
            return True
    return False

def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_local_settings():
    if not LOCAL_SETTINGS.exists():
        save_json(LOCAL_SETTINGS, load_json(LOCAL_SETTINGS_TEMPLATE))

def t(i18n: Dict, lang: str, key: str) -> str:
    return i18n.get(lang, i18n["he"]).get(key, key)

def emit_log(message: str, level: str = "info"):
    """Send log message to all connected SSE clients AND persistent file"""
    log_queue.put(json.dumps({"message": message, "level": level}))
    write_log_to_file(message, level)

def normalize_source(src: str) -> str:
    s = (src or "").strip().lower()
    # map known variants
    if "livefootball" in s:
        return "livefootballtickets"
    if "footballticketnet" in s:
        return "footballticketnet"
    if "sportsevents" in s:
        return "sportsevents365"
    if "tixstock" in s:
        return "tixstock"
    if "golden" in s:
        return "goldenseat"
    return s

import re
def extract_block_from_category(category: str) -> Optional[str]:
    """Check if category ends with a block number (e.g., 'CATEGORIA 1 PREMIUM 304')"""
    match = re.search(r'\b(\d{3})\s*$', category.strip())
    if match:
        return match.group(1)
    return None

def normalize_category(category: str) -> str:
    """Normalize category string for flexible matching"""
    s = category.lower().strip()
    # Remove parentheses content like (CAT3)
    s = re.sub(r'\([^)]*\)', '', s)
    # Replace CATEGORÍA/CATEGORIA with category
    s = re.sub(r'categor[íi]a', 'category', s)
    # Normalize spaces
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove "- fondo" suffix
    s = re.sub(r'\s*-\s*fondo\s*\d*', '', s)
    return s

def match_category(category: str, mapping_key: str) -> bool:
    """Check if category matches mapping key (flexible matching)"""
    cat_norm = normalize_category(category)
    key_norm = normalize_category(mapping_key)
    
    # Exact match
    if cat_norm == key_norm:
        return True
    
    # Check if key is contained in category or vice versa
    if key_norm in cat_norm or cat_norm in key_norm:
        return True
    
    # Special mappings for common patterns
    cat_mappings = {
        'category 1': ['cat1', 'cat 1'],
        'category 2': ['cat2', 'cat 2'],
        'category 3': ['cat3', 'cat 3'],
        'category 4': ['cat4', 'cat 4'],
        'category 1 premium': ['cat1 premium', 'cat 1 premium'],
        'category 2 lateral': ['cat2 lateral', 'cat 2 lateral'],
    }
    
    for full, shorts in cat_mappings.items():
        if cat_norm == full or cat_norm in shorts:
            if key_norm == full or key_norm in shorts:
                return True
    
    return False

def parse_orders(values: List[List[str]]) -> List[Order]:
    # expects header row
    header = values[0]
    idx = {h.strip(): i for i,h in enumerate(header)}
    def get(row, name, default=""):
        return row[idx.get(name, -1)] if idx.get(name, -1) >= 0 and idx.get(name, -1) < len(row) else default

    orders = []
    for r in values[1:]:
        order_number = get(r, "Order number").strip()
        if not order_number:
            continue
        source = normalize_source(get(r, "source").strip())
        event_name = get(r, "event name").strip()
        category = get(r, "Category / Section").strip()
        qty_raw = get(r, "Qty").strip()
        try:
            qty = int(float(qty_raw))
        except Exception:
            qty = 1
        seating = get(r, "Seating Arrangements").strip() or "Up To 2 Together"
        orders.append(Order(order_number, source, event_name, category, qty, seating))
    return orders

def parse_tickets(values: List[List[str]]) -> List[Ticket]:
    header = values[0]
    idx = {h.strip(): i for i,h in enumerate(header)}
    def get(row, name, default=""):
        return row[idx.get(name, -1)] if idx.get(name, -1) >= 0 and idx.get(name, -1) < len(row) else default

    tickets = []
    for i, r in enumerate(values[1:], start=2):  # 2-based row number in sheet
        game = get(r, "game").strip()
        block = get(r, "block").strip()
        row = get(r, "row").strip()
        seat = get(r, "seat").strip()
        # Column K (index 10) is the assignment column - read directly by index
        assigned_to = r[10].strip() if len(r) > 10 else ""
        if not (game and block and row and seat):
            continue
        try:
            row_i = int(float(row)); seat_i = int(float(seat))
        except Exception:
            continue
        tickets.append(Ticket(idx=i, game=game, block=str(block).strip(), row=row_i, seat=seat_i, assigned_to=assigned_to))
    return tickets

_expanded_mappings_cache = {}

def expand_hierarchical_mapping(mapping: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Expand parent categories to include all blocks from their child categories.
    
    Structure: Parent categories have empty arrays [], followed by child categories with blocks.
    Example:
        "CATEGORY 1 NORMAL": []     <- Parent (empty)
        "LONGSIDE 3RD TIER": [501, 502...]  <- Child (has blocks)
        "SHORTSIDE 3RD TIER": [513, 514...]  <- Child (has blocks)
        "CATEGORY 2 NORMAL": []     <- Next Parent (empty)
    """
    expanded = {}
    current_parent = None
    parent_blocks = []
    
    for key, blocks in mapping.items():
        if blocks == [] or blocks is None:
            # This is a parent category - save previous parent first
            if current_parent is not None:
                expanded[current_parent] = parent_blocks
            current_parent = key
            parent_blocks = []
        else:
            # This is a child category with blocks
            expanded[key] = blocks
            if current_parent is not None:
                parent_blocks.extend(blocks)
    
    # Save last parent
    if current_parent is not None:
        expanded[current_parent] = parent_blocks
    
    return expanded

def load_mapping_for_source(source: str) -> Dict[str, List[str]]:
    if source in _expanded_mappings_cache:
        return _expanded_mappings_cache[source]
    
    path = MAPPING_DIR / f"{source}.json"
    if not path.exists():
        return {}
    
    raw_mapping = load_json(path)
    
    # For livefootballtickets, expand hierarchical structure
    if source == "livefootballtickets":
        expanded = expand_hierarchical_mapping(raw_mapping)
    else:
        expanded = raw_mapping
    
    _expanded_mappings_cache[source] = expanded
    return expanded

def allowed_blocks(source: str, category: str, include_upgrades: bool = True) -> Optional[List[str]]:
    # First check if category contains a specific block number at the end
    specific_block = extract_block_from_category(category)
    if specific_block:
        return [specific_block]
    
    # Otherwise use the mapping with flexible matching
    mapping = load_mapping_for_source(source)
    exact_blocks = None
    for key, blocks in mapping.items():
        if match_category(category, key):
            exact_blocks = blocks
            break
    
    if not include_upgrades:
        return exact_blocks
    
    # If no exact match or we want to include upgrade options
    all_blocks = list(exact_blocks) if exact_blocks else []
    
    # Add blocks from upgrade categories (better categories)
    upgrade_cats = get_upgrade_categories(category)
    for upgrade_cat in upgrade_cats:
        # Check if this upgrade is blocked (e.g., shortside -> lateral)
        if is_lateral_upgrade_blocked(category, upgrade_cat):
            continue
        
        # Find blocks for this upgrade category in the source's mapping
        for key, blocks in mapping.items():
            if match_category(upgrade_cat, key):
                for b in blocks:
                    if b not in all_blocks:
                        all_blocks.append(b)
    
    return all_blocks if all_blocks else None

# Cache for block exclusivity analysis
_block_sources_cache = None

def get_block_sources_map() -> Dict[str, set]:
    """
    Returns a map of block -> set of sources that can use this block.
    Used to determine if a block is 'exclusive' (only one source) or 'shared' (multiple sources).
    """
    global _block_sources_cache
    if _block_sources_cache is not None:
        return _block_sources_cache
    
    sources = ["livefootballtickets", "footballticketnet", "sportsevents365", "tixstock", "goldenseat"]
    block_sources = {}  # block -> set of sources
    
    for source in sources:
        mapping = load_mapping_for_source(source)
        for category, blocks in mapping.items():
            for block in blocks:
                block_str = str(block).upper().strip()
                if block_str not in block_sources:
                    block_sources[block_str] = set()
                block_sources[block_str].add(source)
    
    _block_sources_cache = block_sources
    return block_sources

def sort_blocks_by_exclusivity(blocks: List[str], source: str) -> List[str]:
    """
    Sort blocks so that:
    1. Exclusive blocks (only this source can use) come first
    2. Then shared blocks (multiple sources can use)
    3. Within each group, sort by block number descending (highest = cheapest first)
    """
    block_sources = get_block_sources_map()
    
    def exclusivity_key(block):
        block_upper = str(block).upper().strip()
        sources_for_block = block_sources.get(block_upper, set())
        
        # Is this block exclusive to current source?
        is_exclusive = len(sources_for_block) == 1 and source in sources_for_block
        
        # Extract numeric part for sorting (descending)
        try:
            num = int(re.sub(r'\D', '', str(block)) or '0')
        except:
            num = 0
        
        # Sort: exclusive first (0), then shared (1), then by block number descending
        return (0 if is_exclusive else 1, -num)
    
    return sorted(blocks, key=exclusivity_key)

auto_task: Optional[asyncio.Task] = None

async def auto_loop():
    while True:
        ensure_local_settings()
        settings = load_json(LOCAL_SETTINGS)
        if not settings.get("auto_run_enabled"):
            await asyncio.sleep(1)
            continue
        try:
            # Run sync function in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, run_once_sync, settings, settings.get("mode") == "assign", False)
        except Exception as e:
            # swallow to keep loop alive
            pass
        await asyncio.sleep(int(settings.get("poll_seconds", 60)))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_local_settings()
    global auto_task
    auto_task = asyncio.create_task(auto_loop())
    yield
    # Shutdown
    if auto_task:
        auto_task.cancel()
        try:
            await auto_task
        except asyncio.CancelledError:
            pass

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "web/static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "web/templates"))

def run_once_sync(settings: Dict, commit: bool, resume: bool = False):
    global stop_requested, is_running, last_results
    stop_requested = False
    is_running = True
    last_results = None
    
    try:
        rules = load_json(RULES_PATH)
        oid = settings["google"]["orders_spreadsheet_id"]
        otab = settings["google"]["orders_tab"]
        tid = settings["google"]["tickets_spreadsheet_id"]
        ttab = settings["google"]["tickets_tab"]

        mode_text = "מצב הקצאה אוטומטית" if commit else "מצב הצעות בלבד"
        
        # Check for resume
        start_index = 0
        if resume:
            progress = load_progress()
            start_index = progress.get("last_index", 0)
            if start_index > 0:
                emit_log(f"ממשיך מהזמנה #{start_index + 1} (הזמנה אחרונה: {progress.get('last_order', '?')})", "info")
            else:
                emit_log("אין התקדמות שמורה - מתחיל מההתחלה", "info")
        else:
            clear_progress()
            emit_log(f"מתחיל הרצה חדשה - {mode_text}", "info")
        
        emit_log("קורא נתונים מ-Google Sheets...", "info")
        
        orders_values = read_sheet(oid, otab)
        tickets_values = read_sheet(tid, ttab)
        orders = parse_orders(orders_values)
        tickets = parse_tickets(tickets_values)
        
        # CRITICAL: Build set of order numbers that already have assignments in column K
        already_assigned_orders = set()
        for t in tickets:
            if t.assigned_to and str(t.assigned_to).strip():
                already_assigned_orders.add(str(t.assigned_to).strip())
        
        emit_log(f"הזמנות שכבר שובצו בעבר: {len(already_assigned_orders)}", "info")
        
        # Sort orders: specific block orders first (iron rule!), then by category
        def order_priority(o):
            specific = extract_block_from_category(o.category)
            # Specific blocks get priority 0, others get priority 1
            return (0 if specific else 1, o.category)
        
        orders = sorted(orders, key=order_priority)
        
        emit_log(f"נמצאו {len(orders)} הזמנות ו-{len(tickets)} כרטיסים", "success")
        
        # Count specific block orders
        specific_count = sum(1 for o in orders if extract_block_from_category(o.category))
        if specific_count > 0:
            emit_log(f"הזמנות עם בלוק ספציפי: {specific_count} (עדיפות ראשונה!)", "info")

        out = []
        for idx, o in enumerate(orders):
            # Skip if resuming and haven't reached start point
            if idx < start_index:
                continue
                
            # IRON RULE: Skip orders that already have tickets assigned!
            if str(o.order_number).strip() in already_assigned_orders:
                emit_log(f"[{idx+1}/{len(orders)}] דילוג על הזמנה {o.order_number} - כבר שובצה בעבר!", "warning")
                out.append({"order": o.order_number, "source": o.source, "status": "ALREADY_ASSIGNED", "reason": "הזמנה כבר קיבלה כרטיסים"})
                save_progress(idx + 1, len(orders), o.order_number)
                continue
            if stop_requested:
                emit_log("נעצר על ידי המשתמש!", "warning")
                break
                
            emit_log(f"[{idx+1}/{len(orders)}] מעבד הזמנה {o.order_number} ({o.source})", "info")
            
            # Check for specific block in category - if exists, no mapping needed!
            specific_block = extract_block_from_category(o.category)
            
            if specific_block:
                # Specific block order - bypass source check, use only that block
                blocks = [specific_block]
                emit_log(f"  בלוק ספציפי מהזמנה: {specific_block}", "info")
            elif o.source not in ("livefootballtickets","footballticketnet","sportsevents365","tixstock","goldenseat"):
                emit_log(f"דילוג - מקור לא נתמך: {o.source}", "warning")
                continue
            else:
                blocks = allowed_blocks(o.source, o.category)
            if blocks is None:
                emit_log(f"הזמנה {o.order_number} [{o.source}] - קטגוריה לא במיפוי: {o.category}", "warning")
                # Show what categories ARE in the mapping
                mapping = load_mapping_for_source(o.source)
                emit_log(f"  קטגוריות זמינות: {list(mapping.keys())[:5]}", "info")
                out.append({"order": o.order_number, "source": o.source, "status": "CHANGED_CATEGORY_NOT_IN_MAPPING", "reason": f"CATEGORY_NOT_IN_MAPPING: {o.category}"})
                continue
            
            # Sort blocks: exclusive first, then by number descending (highest = cheapest)
            blocks = sort_blocks_by_exclusivity(blocks, o.source)
            
            emit_log(f"  בלוקים מותרים (ממויינים): {blocks[:10]}{'...' if len(blocks)>10 else ''}", "info")
            res = choose_tickets_for_order(o, tickets, blocks, rules)
            
            if res.status == "ASSIGNED":
                ticket_info = ", ".join([f"בלוק {t.block} שורה {t.row} מושב {t.seat}" for t in res.tickets])
                emit_log(f"✓ הזמנה {o.order_number} [{o.source}] - שובץ: {ticket_info}", "success")
            else:
                emit_log(f"✗ הזמנה {o.order_number} [{o.source}] - {res.reason}", "warning")
                
            out.append({"order": o.order_number, "source": o.source, "status": res.status, "reason": res.reason,
                        "tickets": [{"rownum": t.idx, "game": t.game, "block": t.block, "row": t.row, "seat": t.seat} for t in res.tickets]})
                        
            if commit and res.status == "ASSIGNED":
                col_k = 11
                written_count = 0
                skipped_count = 0
                for t in res.tickets:
                    # Double protection: check our cached value AND check the sheet again
                    if t.assigned_to:
                        emit_log(f"  דילוג על כרטיס שורה {t.idx} ({t.block}/{t.row}/{t.seat}) - כבר שובץ ל-{t.assigned_to}", "warning")
                        skipped_count += 1
                        continue
                    
                    sheet_row = t.idx
                    # write_cell returns (status, message)
                    status, msg = write_cell(tid, ttab, sheet_row, col_k, o.order_number)
                    if status == "written":
                        emit_log(f"  ✓ שורה {sheet_row}: {t.block}/{t.row}/{t.seat} -> {o.order_number}", "success")
                        written_count += 1
                        t.assigned_to = o.order_number
                    elif status == "skipped":
                        emit_log(f"  ⊘ שורה {sheet_row}: {t.block}/{t.row}/{t.seat} - תא כבר מלא", "warning")
                        skipped_count += 1
                        t.assigned_to = msg
                    else:  # failed
                        emit_log(f"  ✗ שורה {sheet_row}: שגיאה בכתיבה", "error")
                        skipped_count += 1
                
                if written_count > 0:
                    emit_log(f"נכתב לעמודה K - הזמנה {o.order_number} [{o.source}] ({written_count} כרטיסים, {skipped_count} דולגו)", "info")
            
            # Save progress after each order
            save_progress(idx + 1, len(orders), o.order_number)
                
        assigned_count = len([r for r in out if r["status"] == "ASSIGNED"])
        not_assigned = [r for r in out if r["status"] != "ASSIGNED"]
        
        if not stop_requested:
            emit_log("", "info")
            emit_log("═══════════════════════════════════════════", "info")
            emit_log(f"סיכום: שובצו {assigned_count} מתוך {len(out)} הזמנות", "success")
            emit_log("═══════════════════════════════════════════", "info")
            
            if not_assigned:
                emit_log("", "info")
                emit_log(f"הזמנות שלא שובצו ({len(not_assigned)}):", "warning")
                for r in not_assigned:
                    emit_log(f"  • {r['order']} [{r.get('source', '?')}] - {r.get('reason', 'N/A')}", "warning")
        
        last_results = {"ok": True, "results": out}
    except Exception as e:
        emit_log(f"שגיאה: {str(e)}", "error")
        last_results = {"ok": False, "error": str(e)}
    finally:
        is_running = False

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    i18n = load_json(I18N_PATH)
    lang = settings.get("language","he")
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "t": lambda k: t(i18n, lang, k),
        "settings": settings,
        "lang": lang
    })

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    i18n = load_json(I18N_PATH)
    lang = settings.get("language","he")
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "t": lambda k: t(i18n, lang, k),
        "settings": settings,
        "lang": lang
    })

@app.post("/settings/save")
async def save_settings(
    language: str = Form("he"),
    auto_run_enabled: Optional[str] = Form(None),
    poll_seconds: int = Form(60),
    mode: str = Form("suggest"),
    service_account_json: str = Form(""),
    orders_spreadsheet_id: str = Form(""),
    orders_tab: str = Form("Sheet1"),
    tickets_spreadsheet_id: str = Form(""),
    tickets_tab: str = Form("Sheet1"),
):
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    settings["language"] = language
    settings["auto_run_enabled"] = bool(auto_run_enabled)
    settings["poll_seconds"] = int(poll_seconds)
    settings["mode"] = mode
    # Only update service_account_json if provided (don't overwrite with empty)
    if service_account_json.strip():
        settings["google"]["service_account_json"] = service_account_json.strip()
    settings["google"]["orders_spreadsheet_id"] = orders_spreadsheet_id
    settings["google"]["orders_tab"] = orders_tab
    settings["google"]["tickets_spreadsheet_id"] = tickets_spreadsheet_id
    settings["google"]["tickets_tab"] = tickets_tab
    save_json(LOCAL_SETTINGS, settings)
    return RedirectResponse(url="/settings?saved=1", status_code=303)

@app.post("/run_manual")
async def run_manual():
    global is_running
    if is_running:
        return JSONResponse({"ok": False, "error": "ALREADY_RUNNING"})
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    if not settings["google"]["orders_spreadsheet_id"] or not settings["google"]["tickets_spreadsheet_id"]:
        return JSONResponse({"ok": False, "error": "MISSING_SPREADSHEET_IDS"}, status_code=400)
    commit = (settings.get("mode") == "assign")
    thread = threading.Thread(target=run_once_sync, args=(settings, commit))
    thread.start()
    return JSONResponse({"ok": True, "started": True})

@app.get("/run_status")
async def run_status():
    return JSONResponse({"is_running": is_running, "results": last_results})

@app.post("/toggle_auto")
async def toggle_auto():
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    settings["auto_run_enabled"] = not settings.get("auto_run_enabled", False)
    save_json(LOCAL_SETTINGS, settings)
    return JSONResponse({"ok": True, "auto_run_enabled": settings["auto_run_enabled"]})

@app.get("/logs/poll")
async def poll_logs():
    logs = []
    while True:
        try:
            msg = log_queue.get_nowait()
            logs.append(json.loads(msg))
        except queue.Empty:
            break
    return JSONResponse({"logs": logs})

@app.post("/stop")
async def stop_run():
    global stop_requested
    stop_requested = True
    emit_log("מבקש לעצור...", "warning")
    return JSONResponse({"ok": True})

@app.post("/run_continue")
async def run_continue():
    """Continue from where we stopped"""
    global is_running
    if is_running:
        return JSONResponse({"ok": False, "error": "ALREADY_RUNNING"})
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    if not settings["google"]["orders_spreadsheet_id"] or not settings["google"]["tickets_spreadsheet_id"]:
        return JSONResponse({"ok": False, "error": "MISSING_SPREADSHEET_IDS"}, status_code=400)
    commit = (settings.get("mode") == "assign")
    thread = threading.Thread(target=run_once_sync, args=(settings, commit, True))  # resume=True
    thread.start()
    return JSONResponse({"ok": True, "started": True, "resumed": True})

@app.post("/run_restart")
async def run_restart():
    """Start fresh from the beginning"""
    global is_running
    if is_running:
        return JSONResponse({"ok": False, "error": "ALREADY_RUNNING"})
    clear_progress()
    ensure_local_settings()
    settings = load_json(LOCAL_SETTINGS)
    if not settings["google"]["orders_spreadsheet_id"] or not settings["google"]["tickets_spreadsheet_id"]:
        return JSONResponse({"ok": False, "error": "MISSING_SPREADSHEET_IDS"}, status_code=400)
    commit = (settings.get("mode") == "assign")
    thread = threading.Thread(target=run_once_sync, args=(settings, commit, False))  # resume=False
    thread.start()
    return JSONResponse({"ok": True, "started": True, "resumed": False})

@app.get("/progress_status")
async def progress_status():
    """Get current progress state"""
    progress = load_progress()
    return JSONResponse({
        "has_progress": progress.get("last_index", 0) > 0,
        "last_index": progress.get("last_index", 0),
        "total": progress.get("total", 0),
        "last_order": progress.get("last_order", ""),
        "timestamp": progress.get("timestamp", "")
    })
