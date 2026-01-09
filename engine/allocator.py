from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import re

from .seat_classifier import classify_together

def norm(x: str) -> str:
    return re.sub(r"\s+", " ", str(x or "").strip())

# TixStock block translation: TixStock uses different block numbering
TIXSTOCK_BLOCK_MAP = {
    "1": "101", "2": "102", "3": "103", "4": "104", "5": "105", "6": "106",
    "15": "115", "17": "117", "18": "118", "19": "119", "20": "120",
    "21": "121", "22": "122", "23": "123", "24": "124",
    "115": "15", "117": "17", "118": "18", "119": "19", "120": "20",
    "121": "21", "122": "22", "123": "23", "124": "24",
    "101": "1", "102": "2", "103": "3", "104": "4", "105": "5", "106": "6",
}

def translate_block_for_tixstock(block: str, source: str) -> List[str]:
    """Return possible block translations for TixStock orders"""
    if source.lower() != "tixstock":
        return [block]
    block_upper = str(block).upper().strip()
    result = [block_upper]
    if block_upper in TIXSTOCK_BLOCK_MAP:
        result.append(TIXSTOCK_BLOCK_MAP[block_upper])
    return result

def is_specific_block_order(allowed_blocks: List[str]) -> bool:
    """Check if order is for a specific block (only 1 block allowed)"""
    return len(allowed_blocks) == 1

def extract_teams(game_name: str) -> set:
    """Extract team names from a game string like 'Real Madrid vs Barcelona (Santiago Bernabéu)'"""
    s = norm(game_name).upper()
    # Remove parentheses content (stadium/date info)
    s = re.sub(r'\([^)]*\)', '', s)
    # Remove common date patterns
    s = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', s)
    # Split on VS, V, -, – separators
    parts = re.split(r'\s+(?:VS|V|VS\.|-|–)\s+', s, flags=re.IGNORECASE)
    teams = set()
    for p in parts:
        team = p.strip()
        if team and len(team) > 2:
            teams.add(team)
    return teams

def games_match(order_event: str, ticket_game: str) -> bool:
    """Check if order event matches ticket game (flexible matching)"""
    order_teams = extract_teams(order_event)
    ticket_teams = extract_teams(ticket_game)
    
    # At least one team from order must appear in ticket game
    for order_team in order_teams:
        for ticket_team in ticket_teams:
            # Check if one contains the other (for partial matches like "REAL MADRID" vs "R. MADRID")
            if order_team in ticket_team or ticket_team in order_team:
                return True
    return False

@dataclass
class Order:
    order_number: str
    source: str
    event_name: str
    category: str
    qty: int
    seating: str  # e.g. 'Up To 2 Together', 'Single Seat(s)'

@dataclass
class Ticket:
    idx: int
    game: str
    block: str
    row: int
    seat: int
    assigned_to: str  # existing assignment field (can be empty)

@dataclass
class AssignmentResult:
    status: str  # ASSIGNED / CHANGED_CATEGORY_NOT_IN_MAPPING / NOT_AVAILABLE / NEEDS_APPROVAL
    tickets: List[Ticket]
    reason: str

def parse_up_to(seating: str) -> Optional[int]:
    s = norm(seating).lower()
    if "single" in s:
        return 1
    m = re.search(r"up\s*to\s*(\d+)\s*together", s)
    if m:
        return int(m.group(1))
    return None

def choose_tickets_for_order(
    order: Order,
    tickets: List[Ticket],
    allowed_blocks: List[str],
    rules: Dict
) -> AssignmentResult:
    import logging
    logger = logging.getLogger("ticketsense.allocator")
    
    # Build expanded allowed blocks set (including TixStock translations)
    allowed_blocks_set = set()
    for b in allowed_blocks:
        translations = translate_block_for_tixstock(b, order.source)
        for t_block in translations:
            allowed_blocks_set.add(t_block.upper().strip())
    
    # Check if this is a specific block order (iron rule: absolute priority)
    specific_block_order = is_specific_block_order(allowed_blocks)
    
    candidates = []
    game_fail_count = 0
    block_fail_count = 0
    assigned_count = 0
    
    for t in tickets:
        game_match = games_match(order.event_name, t.game)
        # Also check ticket block with TixStock translation
        ticket_block = norm(t.block).upper()
        block_match = ticket_block in allowed_blocks_set
        not_assigned = not norm(t.assigned_to)
        
        if not game_match:
            game_fail_count += 1
        elif not block_match:
            block_fail_count += 1
        elif not not_assigned:
            assigned_count += 1
        else:
            candidates.append(t)
    
    logger.info(f"Order {order.order_number}: allowed_blocks={list(allowed_blocks_set)[:5]}..., candidates={len(candidates)}, game_fail={game_fail_count}, block_fail={block_fail_count}, already_assigned={assigned_count}")
    
    if not allowed_blocks:
        return AssignmentResult("CHANGED_CATEGORY_NOT_IN_MAPPING", [], "NO_BLOCKS_FOR_CATEGORY")
    if not candidates:
        reason = f"אין מלאי - משחק:{game_fail_count} בלוק:{block_fail_count} תפוס:{assigned_count}"
        return AssignmentResult("NOT_AVAILABLE", [], reason)

    # Sort candidates to match the order of allowed_blocks (which is pre-sorted with exclusivity priority)
    # First priority: position in allowed_blocks list (exclusivity), Second priority: block number descending
    # Build priority map including all translations for TixStock
    block_priority = {}
    for i, b in enumerate(allowed_blocks):
        b_upper = str(b).upper().strip()
        block_priority[b_upper] = i
        # Also add translations for TixStock
        translations = translate_block_for_tixstock(b, order.source)
        for trans in translations:
            if trans.upper() not in block_priority:
                block_priority[trans.upper()] = i
    
    def block_sort_key(t):
        block_upper = norm(t.block).upper()
        priority = block_priority.get(block_upper, 999)
        try:
            num = -int(re.sub(r'\D', '', t.block) or '0')
        except:
            num = 0
        return (priority, num)
    
    candidates = sorted(candidates, key=block_sort_key)
    logger.info(f"Order {order.order_number}: sorted candidates (exclusivity first), first blocks: {[c.block for c in candidates[:5]]}")

    # classify together tags on candidates by constructing record list
    recs = [{"game": t.game, "block": t.block, "row": t.row, "seat": t.seat} for t in candidates]
    tags = classify_together(recs)

    up_to = parse_up_to(order.seating) or 2
    # SINGLE strict rule
    if order.qty == 1 or up_to == 1:
        singles = [candidates[i] for i,tag in tags.items() if tag == "SINGLE"]
        if singles:
            return AssignmentResult("ASSIGNED", [singles[0]], "SINGLE_OK")
        
        # IRON RULE: Specific block orders CAN split PAIR for singles
        if specific_block_order:
            # Take first ticket from any PAIR in the specific block
            pairs = [candidates[i] for i,tag in tags.items() if tag == "PAIR"]
            if pairs:
                return AssignmentResult("ASSIGNED", [pairs[0]], "SINGLE_FROM_PAIR_SPECIFIC_BLOCK")
        
        if rules.get("single_rule", {}).get("strict_single_only", True):
            return AssignmentResult("NOT_AVAILABLE", [], "SINGLE_REQUIRED_NO_SINGLE_AVAILABLE")
        # Fallback: use first seat from PAIR if allowed
        pairs = [candidates[i] for i,tag in tags.items() if tag == "PAIR"]
        if pairs:
            return AssignmentResult("ASSIGNED", [pairs[0]], "SINGLE_FROM_PAIR")
        # Try SCH as last resort
        schs = [candidates[i] for i,tag in tags.items() if tag == "SCH" or tag.startswith("SCH-")]
        if schs:
            return AssignmentResult("ASSIGNED", [schs[0]], "SINGLE_FROM_SCH")
        return AssignmentResult("NOT_AVAILABLE", [], "SINGLE_NO_CANDIDATES")

    allow_sch = rules["sources"].get(order.source, {}).get("allow_sch", False)
    source_lower = order.source.lower()
    
    # goldenseat has special priority: PAIR first, SCH only as last resort
    if source_lower == "goldenseat" and "goldenseat_priority" in rules["pairing_priority"]:
        priority = rules["pairing_priority"]["goldenseat_priority"]
    elif allow_sch:
        priority = rules["pairing_priority"]["when_allow_sch"]
    else:
        priority = rules["pairing_priority"]["when_disallow_sch"]

    # STRICT RULE: "Up To N Together" means ALL tickets must be in same row/block
    # Adjacent = diff 2 between seats
    # SCH allowed = max 1 seat gap (diff 4) - only if source allows SCH
    # More than 1 seat gap (diff 6+) = NEVER allowed
    need = order.qty
    chosen: List[Ticket] = []
    
    # Build all available groups (by game, block, row)
    groups_by_key = {}  # (game, block, row) -> list of tickets
    for i, tag in tags.items():
        t = candidates[i]
        key = (t.game, t.block, t.row)
        if key not in groups_by_key:
            groups_by_key[key] = []
        groups_by_key[key].append((t, i, tag))
    
    # Find valid sequences
    # Priority 1: Strictly adjacent (all diff == 2)
    # Priority 2: With SCH gap (max 1 gap of diff 4, rest diff 2) - only if allow_sch
    valid_groups_strict = []  # Strictly adjacent
    valid_groups_sch = []     # With SCH gap
    
    for key, members in groups_by_key.items():
        # Sort by seat number
        members_sorted = sorted(members, key=lambda x: x[0].seat)
        
        # Try to find sequences of 'need' tickets
        # Use sliding window approach
        for start_idx in range(len(members_sorted)):
            if start_idx + need > len(members_sorted):
                break
            
            window = members_sorted[start_idx:start_idx + need]
            seats = [m[0].seat for m in window]
            
            # Check differences between consecutive seats
            diffs = [seats[i+1] - seats[i] for i in range(len(seats)-1)]
            
            # All must be diff 2 or diff 4 (SCH gap)
            # diff 6+ is NEVER allowed
            valid = True
            sch_gaps = 0
            for d in diffs:
                if d == 2:
                    pass  # OK - adjacent
                elif d == 4:
                    sch_gaps += 1  # SCH gap (1 seat)
                else:
                    valid = False  # Gap too large (2+ seats)
                    break
            
            if not valid:
                continue
            
            # Max 1 SCH gap allowed
            if sch_gaps > 1:
                continue
            
            if sch_gaps == 0:
                # Strictly adjacent - always OK
                valid_groups_strict.append((key, window))
            elif sch_gaps == 1 and allow_sch:
                # Has SCH gap - only OK if source allows SCH
                valid_groups_sch.append((key, window))
    
    # Prefer strictly adjacent, then SCH
    valid_groups = valid_groups_strict if valid_groups_strict else valid_groups_sch
    
    if not valid_groups:
        return AssignmentResult("NOT_AVAILABLE", [], f"NO_GROUP_WITH_{need}_ADJACENT_SEATS")
    
    # Sort by block number (prefer higher blocks)
    def group_priority(item):
        key, members = item
        block = key[1]
        try:
            block_num = -int(re.sub(r'\D', '', str(block)) or '0')
        except:
            block_num = 0
        return block_num
    
    valid_groups.sort(key=group_priority)
    best_key, best_members = valid_groups[0]
    
    # Take the tickets from this single group
    for t, idx, tag in best_members:
        chosen.append(t)
    
    if len(chosen) == need:
        return AssignmentResult("ASSIGNED", chosen, f"ALL_{need}_TOGETHER_OK")
    
    return AssignmentResult("NOT_AVAILABLE", [], f"INSUFFICIENT_ADJACENT_NEED_{order.qty}_HAVE_{len(chosen)}")
