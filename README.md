# TicketSense.ai — Real Madrid Ticket Assignment (FastAPI + UI)

This project implements a **rule-based ticket assignment engine** for Real Madrid tickets.

## What it does
- Reads **Orders** sheet + **Tickets** sheet from Google Sheets (Service Account).
- Uses **Category→Blocks mapping** per source (3 sources included).
- Applies business rules:
  - STRICT `SINGLE`: never break PAIR/SCH to fulfill a single.
  - `Up To 2 Together`: for sources that allow SCH, consume SCH first, then PAIR.
  - `Up To 3/4`: currently conservative; exact N-together works when qty==N; advanced splitting requires approval (can be extended).

## Run locally / in Replit
1. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
2. Start server:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
3. Open the web UI.

## Google Sheets setup
- Create a Service Account in Google Cloud and enable Sheets API.
- Share your spreadsheets with the service account email.
- In the UI Settings page, paste the Service Account JSON and spreadsheet IDs.

## Manual vs Auto
- Manual: click "הרץ ידני" in Dashboard.
- Auto: toggle Auto and set poll interval + mode (Suggest / Auto assign).

## Deployment to Production

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions on deploying to:
- Railway (recommended)
- Render
- Heroku
- Docker

The app supports both Replit connectors (for Replit deployment) and Service Account JSON (for production deployment).

## IMPORTANT
Do not change business rules in code without syncing `config/seating_rules.json`.
