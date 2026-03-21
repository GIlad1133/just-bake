# Just Bake - Invoice Automation System

**Pashut La'afot (פשוט לאפות)** - Neapolitan Pizza Invoice Automation

## Overview

Automated invoice system for Just Bake pizza business:
- 📝 **Order Entry UI** - Web form for entering orders (Streamlit)
- 🤖 **Invoice Automation** - Automatic receipt creation via Keep.co.il API
- 📊 **Google Sheets** - Order tracking and data source

## Features

- 10 product types (kits, dough, sauces, cheese, flour)
- Business customer support (B2B with ח.פ.)
- Payment methods: Bit, Paybox, מזומן, לא שולם
- Automatic receipt creation via Keep.co.il
- Mobile-friendly order entry

## Components

### 1. Streamlit Order Entry UI (`streamlit_app/`)
Web interface for entering new orders. Accessible from any device.

### 2. Invoice Automation (`src/`)
Python automation that:
- Reads pending orders from Google Sheets
- Validates totals and items
- Creates receipts via Keep.co.il API
- Updates sheet with invoice URLs

## Setup

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
pip install -r streamlit_app/requirements.txt
```

2. Create `.env` file with credentials:
```
GOOGLE_SHEETS_CREDENTIALS={"type": "service_account", ...}
GOOGLE_SHEETS_SPREADSHEET_ID=your-sheet-id
KEEP_CLIENT_ID=your-client-id
KEEP_CLIENT_SECRET=your-client-secret
KEEP_API_BASE_URL=https://app.keep.co.il
```

3. Run Streamlit UI:
```bash
streamlit run streamlit_app/app.py
```

4. Run invoice automation:
```bash
python -m src.main
```

## Deployment

- **Streamlit Cloud** - Order entry UI (free tier)
- **GitHub Actions** - Automated invoice processing (optional)

## Tech Stack

- Python 3.12+
- Streamlit (Web UI)
- gspread (Google Sheets API)
- Keep.co.il API (Israeli invoicing)

---

Built with ❤️ for Just Bake
