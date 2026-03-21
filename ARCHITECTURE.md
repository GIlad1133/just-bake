# Just Bake - System Architecture

## Overview

The Just Bake invoice automation system consists of two independent components that work together:

1. **Order Entry UI** (Streamlit Cloud) - For entering new orders
2. **Invoice Automation** (GitHub Actions) - For creating invoices automatically

Both components use Google Sheets as the single source of truth.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Just Bake System                                │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  ORDER ENTRY COMPONENT (Streamlit Cloud - FREE)                          │
└──────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   User       │  (Gilad or staff)
    │ (Any Device) │  Phone, Tablet, Computer
    └──────┬───────┘
           │
           │ HTTPS
           ▼
    ┌─────────────────────┐
    │  Streamlit Web App  │  Hosted on Streamlit Cloud (Free)
    │  just-bake.streamlit.app
    │                     │
    │  • Customer form    │
    │  • Product grid     │
    │  • Auto-calculate   │
    │  • Validation       │
    └─────────┬───────────┘
              │
              │ Google Sheets API
              │ (gspread library)
              ▼
    ┌──────────────────────────────────────────────────────┐
    │         Google Sheets (PIZZA TIME)                   │
    │                                                       │
    │  Single Source of Truth - Contains:                  │
    │  • Customer info                                     │
    │  • Order details                                     │
    │  • 10 products (qty + price each)                    │
    │  • "create invoice" flag (yes/no)                    │
    │  • Invoice URL (filled by automation)                │
    │  • Status/errors (filled by automation)              │
    └───────────────────────┬──────────────────────────────┘
                            │
                            │ Read pending orders
                            │ (where "create invoice" = "yes")
                            │
                            ▼

┌──────────────────────────────────────────────────────────────────────────┐
│  INVOICE AUTOMATION COMPONENT (GitHub Actions - FREE)                    │
└──────────────────────────────────────────────────────────────────────────┘

    ┌────────────────────────────────────────┐
    │      GitHub Actions Workflow           │
    │                                        │
    │  Triggers:                             │
    │  • Schedule: Every 6 hours             │
    │  • Manual: Via GitHub UI               │
    │                                        │
    │  Runtime: Ubuntu, Python 3.11          │
    └──────────────┬─────────────────────────┘
                   │
                   │ Runs: python src/main.py
                   ▼
    ┌─────────────────────────────────────┐
    │   Invoice Processor                 │
    │   (Python Application)              │
    │                                     │
    │   Components:                       │
    │   ├─ google_sheets.py               │
    │   │   └─ Get pending orders         │
    │   │   └─ Update status              │
    │   │                                 │
    │   ├─ keep_client.py                 │
    │   │   └─ OAuth authentication       │
    │   │   └─ Create receipts            │
    │   │                                 │
    │   ├─ invoice_processor.py           │
    │   │   └─ Validate orders            │
    │   │   └─ Transform data             │
    │   │   └─ Error handling             │
    │   │                                 │
    │   └─ models.py                      │
    │       └─ Type-safe data structures  │
    └──────────┬──────────────────────────┘
               │
               │ For each pending order:
               │
               ├──> 1. Read order from Google Sheets
               │
               ├──> 2. Validate total (sum items vs. sheet total)
               │
               ├──> 3. Transform to Keep.co.il format
               │         (shekels → agorot, Hebrew names)
               │
               ├──> 4. POST to Keep.co.il Income API
               │         │
               │         ▼
               │    ┌─────────────────────────┐
               │    │  Keep.co.il API         │
               │    │  https://api.keepo.co.il │
               │    │                         │
               │    │  • OAuth token          │
               │    │  • Create receipt       │
               │    │  • Return invoice URL   │
               │    └─────────┬───────────────┘
               │              │
               │              │ Receipt created
               │              ▼
               │
               └──> 5. Update Google Sheets
                      • "create invoice" = "Done"
                      • Invoice URL
                      • Status (success/error)

```

## Data Flow

### 1. Order Entry Flow

```
User enters order
    ↓
Streamlit validates (customer name, at least 1 item)
    ↓
Calculate total (qty × price for all items)
    ↓
Generate UUID for row ID
    ↓
Submit to Google Sheets
    ↓
Set "create invoice" = "yes"
    ↓
Order ready for automation
```

### 2. Invoice Creation Flow

```
GitHub Actions triggers (schedule or manual)
    ↓
Load environment variables (secrets)
    ↓
Initialize Google Sheets client
    ↓
Initialize Keep.co.il client
    ↓
Query Google Sheets for rows where "create invoice" = "yes"
    ↓
For each pending order:
    │
    ├─> Parse order data (customer, date, items, total)
    │
    ├─> Extract 10 products (only if qty > 0 AND price > 0)
    │
    ├─> Validate: sum(item totals) ≈ sheet total (±0.01)
    │       │
    │       ├─> If invalid: Write error to sheet, skip
    │       │
    │       └─> If valid: Continue
    │
    ├─> Build Keep.co.il receipt format
    │   • Convert shekels to agorot (×100)
    │   • Add customer name
    │   • Add payment method comment
    │   • Format date as "YYYY-MM-DD HH:MM:SS"
    │
    ├─> Get OAuth token (cached, auto-refresh)
    │
    ├─> POST to Keep.co.il /income endpoint
    │   • Retry on 429 (rate limit)
    │   • Retry on 5xx (server error)
    │   • Exponential backoff
    │
    ├─> Extract invoice URL from response
    │
    └─> Update Google Sheets:
        • "create invoice" = "Done"
        • Invoice URL column
        • Status = success (or error message)
```

## Component Details

### Streamlit Order Entry UI

**Technology:**
- Framework: Streamlit (Python web framework)
- Hosting: Streamlit Cloud (free tier)
- Dependencies: streamlit, gspread, google-auth

**Features:**
- Customer information form
- 10 product inputs (quantity + price)
- Real-time total calculation
- Form validation
- Direct Google Sheets integration
- Mobile-responsive

**Why Streamlit?**
- Zero cost hosting (free tier)
- No frontend coding needed (pure Python)
- Auto-generates responsive UI
- Built-in secrets management
- Automatic HTTPS
- Easy deployment (git push)

### Invoice Automation

**Technology:**
- Runtime: GitHub Actions (Ubuntu + Python 3.11)
- Schedule: Cron (every 6 hours)
- Dependencies: gspread, google-auth, requests

**Features:**
- Automated scheduling
- Manual trigger option
- Batch processing
- Error handling & logging
- Token caching (Keep.co.il OAuth)
- Retry logic with backoff
- Validation before API calls

**Why GitHub Actions?**
- Zero cost (2000 free minutes/month, we use ~240)
- Version controlled (all code in git)
- Secrets management built-in
- Logs accessible via GitHub UI
- Can trigger from anywhere (GitHub web/mobile)
- No server management

## Security & Credentials

### Secrets Storage

**Streamlit Cloud:**
- Google Sheets service account JSON
- Spreadsheet ID
- Stored in Streamlit UI (encrypted)

**GitHub Actions:**
- Google Sheets service account JSON
- Spreadsheet ID
- Keep.co.il client ID & secret
- Stored as GitHub repository secrets (encrypted)

**Local Development:**
- `.env` file (gitignored)
- Never committed to repository

### Google Sheets Authentication

```
Service Account (Google Cloud)
    ↓
JSON key file with private key
    ↓
Stored as secret (Streamlit/GitHub)
    ↓
gspread library authenticates
    ↓
Access granted to shared spreadsheet
```

**Note:** No OAuth flow needed (service account = server-to-server auth)

### Keep.co.il Authentication

```
Client ID + Client Secret
    ↓
POST /oauth/token
    ↓
Access token (expires in ~1 hour)
    ↓
Cached in memory
    ↓
Used for API requests (Bearer token)
    ↓
Auto-refresh on 401 Unauthorized
```

## Scalability & Performance

### Current Scale
- **Orders per month:** ~50-100 (estimated)
- **Automation runs:** 120/month (every 6 hours)
- **API calls per run:** ~1-5 (depending on pending orders)
- **Processing time:** ~5-30 seconds per run

### Limits & Quotas

**Google Sheets API:**
- Free tier: 500 requests per 100 seconds
- Current usage: ~10 requests per run
- Plenty of headroom for growth

**GitHub Actions:**
- Free tier: 2000 minutes/month (private repo) or unlimited (public)
- Current usage: ~240 minutes/month
- Can scale to daily or hourly if needed

**Streamlit Cloud:**
- Free tier: 1 app, 1 GB RAM
- Current usage: <100 MB RAM
- Sufficient for order entry use case

**Keep.co.il API:**
- Rate limits: Unknown (handled with retry + backoff)
- Current usage: <1 request per minute average
- Unlikely to hit limits

## Error Handling

### Validation Errors
- Total mismatch → Write to sheet, skip invoice
- No items → Write to sheet, skip invoice
- Missing customer name → Not possible (UI validation)

### API Errors
- Google Sheets auth failure → Fail workflow, notify via GitHub
- Keep.co.il 401 → Refresh token, retry
- Keep.co.il 429 (rate limit) → Exponential backoff, retry
- Keep.co.il 5xx → Exponential backoff, retry
- Network timeout → Retry up to 3 times

### Recovery
- Errors written to Google Sheets
- Failed orders stay with "create invoice" = "yes"
- Next automation run will retry
- Manual inspection via sheet error column

## Monitoring & Logs

### Streamlit App
- Built-in logs in Streamlit Cloud UI
- App errors visible to users
- Form submission feedback

### GitHub Actions
- Workflow logs in GitHub Actions tab
- Each run shows:
  - Orders processed
  - Successes
  - Failures
  - Error details
- Logs retained for 90 days

### Google Sheets
- Live status for each order
- Error messages visible
- Invoice URLs for successful invoices

## Cost Analysis

| Component | Service | Cost |
|-----------|---------|------|
| Order Entry UI | Streamlit Cloud | $0/month (free tier) |
| Invoice Automation | GitHub Actions | $0/month (free tier) |
| Google Sheets API | Google Cloud | $0/month (free tier) |
| Keep.co.il API | Keep subscription | $0/month (included) |
| **Total** | | **$0/month** |

## Comparison with n8n

| Aspect | n8n Workflow | Python Solution |
|--------|--------------|-----------------|
| Maintainability | Visual, hard to debug | Code-based, type-safe |
| Version Control | JSON export | Full git history |
| Testing | Manual clicking | Unit tests possible |
| Error Handling | Limited visibility | Detailed logs + sheet |
| Deployment | Self-hosted or cloud | GitHub Actions (free) |
| Order Entry | Manual sheet editing | Web form (Streamlit) |
| Cost | ~$10-20/month (hosted) | $0/month |
| Accessibility | Only where n8n runs | Anywhere (GitHub/web) |
| Documentation | Workflow screenshots | Code + README |

## Future Enhancements (Ideas)

1. **Email Notifications**
   - Send email on failed invoices
   - Daily summary of created invoices

2. **Order Dashboard**
   - Streamlit page to view order history
   - Filter by date, customer, status

3. **Webhook Trigger**
   - Trigger automation immediately when order added
   - Instead of waiting for 6-hour schedule

4. **Product Templates**
   - Save common order combinations
   - One-click "Family Package", "Catering Package"

5. **Customer Database**
   - Auto-fill customer info from previous orders
   - Track repeat customers

6. **Invoice PDF Export**
   - Download invoices as PDF from Keep.co.il
   - Store in Google Drive folder

7. **Multi-language Support**
   - English + Hebrew UI
   - Auto-detect or user preference

8. **Analytics**
   - Most popular products
   - Revenue trends
   - Customer retention

## Support & Maintenance

### Regular Maintenance (None Required!)
- GitHub Actions runs automatically
- No server to maintain
- No infrastructure to monitor

### Occasional Updates
- Update Python dependencies (quarterly)
- Add new products (edit `products.py`)
- Adjust column mapping (if sheet structure changes)

### Troubleshooting
1. Check GitHub Actions logs
2. Check Google Sheets error column
3. Verify secrets are up to date
4. Consult README.md or SETUP_GUIDE.md
