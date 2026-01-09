from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
import re

@dataclass(frozen=True)
class SeatKey:
    game: str
    block: str
    row: int
    seat: int

def _norm_str(x: str) -> str:
    return re.sub(r"\s+", " ", str(x or "").strip())

def classify_together(records: List[Dict]) -> Dict[int, str]:
    """
    Tag each ticket row index with: SINGLE, PAIR, '<N> together', SCH-<gaps>, SCH.
    This mirrors the user's Apps Script logic:
    - Group by (game, block, row)
    - Split by parity (odd/even)
    - Together if seat increments by 2
    - SCH within same row/parity for gaps (diff 4..40)
    - SCH diagonal (adjacent row, seat +/-2/0) for remaining singles
    Input: list of dicts with keys: game, block, row, seat
    Output: dict mapping record index -> tag
    """
    result = {i: "SINGLE" for i in range(len(records))}
    seat_map: Dict[Tuple[str,str,int,int], int] = {}
    row_groups: Dict[Tuple[str,str,int], List[Tuple[int,int]]] = {}

    for i, r in enumerate(records):
        game = _norm_str(r.get("game",""))
        block = _norm_str(r.get("block",""))
        row = int(r.get("row"))
        seat = int(r.get("seat"))
        seat_map[(game, block, row, seat)] = i
        row_groups.setdefault((game, block, row), []).append((i, seat))

    # Step 1: parity sequences (diff == 2)
    for (game, block, row), group in row_groups.items():
        even = sorted([(i,s) for i,s in group if s % 2 == 0], key=lambda x: x[1])
        odd  = sorted([(i,s) for i,s in group if s % 2 != 0], key=lambda x: x[1])

        for lst in (even, odd):
            temp: List[Tuple[int,int]] = []
            for i,s in lst:
                if not temp:
                    temp = [(i,s)]
                    continue
                _, last_s = temp[-1]
                if s - last_s == 2:
                    temp.append((i,s))
                else:
                    if len(temp) == 2:
                        result[temp[0][0]] = result[temp[1][0]] = "PAIR"
                    elif len(temp) >= 3:
                        tag = f"{len(temp)} together"
                        for ii,_ in temp:
                            result[ii] = tag
                    temp = [(i,s)]
            if len(temp) == 2:
                result[temp[0][0]] = result[temp[1][0]] = "PAIR"
            elif len(temp) >= 3:
                tag = f"{len(temp)} together"
                for ii,_ in temp:
                    result[ii] = tag

    # Step 2: SCH within same row/parity for remaining SINGLEs
    for (game, block, row), group in row_groups.items():
        even = [(i,s) for i,s in group if s % 2 == 0]
        odd  = [(i,s) for i,s in group if s % 2 != 0]
        for lst in (even, odd):
            if len(lst) < 2:
                continue
            lst = sorted(lst, key=lambda x: x[1])
            for a_i, a_s in lst:
                for b_i, b_s in lst:
                    if b_s <= a_s:
                        continue
                    if result[a_i] != "SINGLE" or result[b_i] != "SINGLE":
                        continue
                    diff = abs(a_s - b_s)
                    if diff > 2 and diff <= 40 and diff % 2 == 0:
                        gaps = (diff // 2) - 1
                        tag = f"SCH-{gaps}"
                        result[a_i] = result[b_i] = tag
                        break

    # Step 3: diagonal SCH for remaining SINGLEs
    # Also handle special stadium edge cases where seats above/below have different seat numbers
    SPECIAL_SCH_PAIRS = [
        # Block 618: row 7 seat 24 is directly above row 6 seat 28
        ("618", 7, 24, 6, 28),
        ("618", 6, 28, 7, 24),
    ]
    
    for i, r in enumerate(records):
        if result[i] != "SINGLE":
            continue
        game = _norm_str(r.get("game",""))
        block = _norm_str(r.get("block",""))
        row = int(r.get("row"))
        seat = int(r.get("seat"))
        
        # Check special stadium edge cases first
        for spec in SPECIAL_SCH_PAIRS:
            spec_block, spec_row1, spec_seat1, spec_row2, spec_seat2 = spec
            if block.upper() == spec_block and row == spec_row1 and seat == spec_seat1:
                # Look for the matching seat
                j = seat_map.get((game, block, spec_row2, spec_seat2))
                if j is not None and result[j] == "SINGLE":
                    result[i] = result[j] = "SCH"
                    break
        
        if result[i] == "SCH":
            continue
        
        # Standard diagonal SCH: adjacent rows with seat offset -2, 0, or +2
        for dr in (-1, 1):
            nr = row + dr
            for ds in (-2, 0, 2):
                ns = seat + ds
                j = seat_map.get((game, block, nr, ns))
                if j is not None and result[j] == "SINGLE":
                    result[i] = result[j] = "SCH"
                    break
            if result[i] == "SCH":
                break

    return result
