# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Just Bake** (Pashut La'afot - פשוט לאפות) is a Neapolitan pizza business automation platform consisting of:
1. **Streamlit Order Entry UI** - Web-based order form (deployed on Streamlit Cloud)
2. **Invoice Automation** - Automated Keep.co.il invoice creation (runs on GitHub Actions)
3. **Google Sheets** - Single source of truth for all order data

The system is designed to be **zero-cost**, **zero-maintenance**, and accessible from any device.

## Development Commands

### Local Development

```bash
# Run Streamlit order entry UI locally
streamlit run streamlit_app/app.py

# Run invoice automation locally (requires pending orders in sheet)
python src/main.py

# Run tests
pytest

# Install dependencies for invoice automation
pip install -r requirements.txt

# Install dependencies for Streamlit UI
pip install -r streamlit_app/requirements.txt
```

### Environment Setup

Create `.env` file with:
```
GOOGLE_SHEETS_CREDENTIALS={"type": "service_account", ...}
GOOGLE_SHEETS_SPREADSHEET_ID=your-sheet-id
KEEP_CLIENT_ID=your-client-id
KEEP_CLIENT_SECRET=your-client-secret
KEEP_API_BASE_URL=https://app.keep.co.il
```

## Architecture

### Two Independent Components

**1. Order Entry (streamlit_app/)**
- Single-page Streamlit app for order entry
- Writes directly to Google Sheets
- Password-protected with `check_password()` function
- Customer autocomplete from existing orders (cached 5 min)
- Auto-clears form after submission

**2. Invoice Automation (src/)**
- Reads pending orders from Google Sheets (`create invoice` = "yes")
- Creates receipts via Keep.co.il API
- Updates sheet with invoice URLs and status
- Runs every 6 hours via GitHub Actions (or manually)

### Data Flow

```
User → Streamlit UI → Google Sheets → Invoice Automation → Keep.co.il API → Google Sheets (updated)
```

### Google Sheets Structure

Critical columns:
- **Column A**: Date (DD/MM/YYYY)
- **Column B**: Customer Name
- **Column C**: Total Amount (₪)
- **Column D**: Payment Method
- **Column E**: create invoice flag ("yes" triggers automation)
- **Column F**: invoice_url (populated after invoice created)
- **Columns G-Z**: 10 products (qty, price pairs) - see products.py
- **Column AA**: RowId (UUID)
- **Column AB**: Status (error messages)
- **Column AC**: Phone Number
- **Column AD**: Business ID (ח.פ.)

## Key Components

### streamlit_app/app.py
The main order entry UI. Key functions:
- `check_password()` - Password protection (uses st.secrets["app_password"])
- `get_sheets_client()` - Google Sheets authentication (tries 3 methods)
- `get_existing_customers()` - Customer autocomplete (cached 5 min)
- `submit_order()` - Writes order to Google Sheets
- Uses `st.session_state.product_data` for form state

**Credentials Loading**: Tries 3 methods in order:
1. `GOOGLE_CREDENTIALS_JSON` (flat JSON string - avoids TOML parsing issues)
2. `google_sheets_credentials` (nested TOML)
3. `.env` file (local development)

### streamlit_app/products.py
Product catalog - 10 products with Hebrew names:
- 3 Kits (Neapolitan, Spelt, Gluten-free)
- 3 Doughs (Neapolitan, Spelt, Gluten-free)
- 2 Sauces (White, Red)
- Opening Flour
- Cheese (SPECIAL: has swapped column order - Price then Qty)

Payment methods: `not_paid`, `bit`, `paybox`, `cash`

### src/models.py
Type-safe data structures:
- `OrderItem` - Individual product (qty, price, totals)
- `Order` - Complete order with validation
- `KeepReceiptItem` - Keep.co.il API format
- `KeepReceipt` - Keep.co.il receipt request

**Important**: Prices in agorot (1₪ = 100 agorot) for Keep.co.il

### src/google_sheets.py
Google Sheets integration. Key functions:
- `get_pending_orders()` - Get orders where "create invoice" = "yes"
- `update_order_status()` - Mark order as processed
- Uses service account authentication

### src/keep_client.py
Keep.co.il API client with:
- OAuth token caching and auto-refresh
- Retry logic with exponential backoff
- Rate limit handling (429 errors)
- `create_receipt()` - Creates invoice via API

### src/invoice_processor.py
Business logic:
- `process_pending_orders()` - Main entry point
- Validates order totals (tolerance ±0.01₪)
- Transforms data to Keep.co.il format
- Error handling and status updates

## Important Implementation Details

### Cheese Product Has Swapped Columns
In Google Sheets, Cheese (product #10) has **Price then Qty** instead of **Qty then Price**. This is handled in `streamlit_app/app.py:220`:
```python
if i == 9:  # Cheese
    row_data.append(product_data.get(f"{prefix}_price", 0.0))  # Y: Cheese Price
    row_data.append(product_data.get(f"{prefix}_qty", 0))      # Z: Cheese Qty
```

### Streamlit Cloud Credentials Format
The private_key in Google service account JSON causes TOML parsing issues when stored in nested format. Solution: use `GOOGLE_CREDENTIALS_JSON` as a flat JSON string at the top level of secrets.toml:
```toml
GOOGLE_CREDENTIALS_JSON = "{\"type\": \"service_account\", \"private_key\": \"-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n\", ...}"
```

### Customer Autocomplete
`get_existing_customers()` reads ALL rows from Google Sheets and builds a dict `{customer_name: phone}`. Cached for 5 minutes to avoid excessive API calls. When user selects existing customer, phone auto-fills.

### Auto-clear After Submit
After successful order submission, `time.sleep(2)` shows success message, then `st.rerun()` clears all form inputs and resets to initial state.

### Payment Method Tracking
The "Payment Method" column serves dual purpose:
- Before payment: "לא שולם" (not paid)
- After payment: Update to actual method (Bit, Paybox, מזומן)

This allows tracking which orders need payment follow-up.

## Deployment

### Streamlit Cloud
- **App URL**: Defined by user (e.g., `just-bake.streamlit.app`)
- **Secrets**: Set via Streamlit UI → Settings → Secrets
- **Required secrets**: `app_password`, `spreadsheet_id`, `GOOGLE_CREDENTIALS_JSON`
- **Auto-deploys**: On git push to main branch

### GitHub Actions
- **Workflow**: `.github/workflows/invoice-automation.yml`
- **Schedule**: Every 6 hours (`0 */6 * * *`)
- **Manual trigger**: Actions tab → "Run workflow"
- **Required secrets**: Set in repo Settings → Secrets → Actions
  - `GOOGLE_SHEETS_CREDENTIALS`
  - `GOOGLE_SHEETS_SPREADSHEET_ID`
  - `KEEP_CLIENT_ID`
  - `KEEP_CLIENT_SECRET`
  - `KEEP_API_BASE_URL`

## Git Workflow

The repository uses SSH authentication for automated pushes:
- SSH key: `~/.ssh/id_ed25519_gilad1133`
- GitHub account: GIlad1133 (klaingilad@gmail.com)
- Remote: `git@github.com:GIlad1133/just-bake.git`

When making commits, include co-author:
```bash
git commit -m "Your message

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

## Adding New Products

1. Add to `streamlit_app/products.py` PRODUCTS list
2. Add corresponding columns to Google Sheets (qty, price pair)
3. Update column mapping in `src/google_sheets.py` if needed
4. Update `streamlit_app/app.py` row_data assembly (line ~216)
5. Consider if column order is standard (Qty, Price) or special like Cheese

## Troubleshooting Common Issues

### "Failed to initialize Google Sheets client"
- Check that credentials are properly formatted in Streamlit secrets
- Use `GOOGLE_CREDENTIALS_JSON` format (flat JSON string)
- Verify service account has access to the spreadsheet

### Invoice automation skips orders
- Check "create invoice" column is exactly "yes" (case-sensitive)
- Verify order total matches sum of items (within 0.01₪)
- Check GitHub Actions logs for validation errors
- Error messages written to Status column (AB) in Google Sheets

### Customer autocomplete not working
- Check `get_existing_customers()` cache (5 min TTL)
- Verify customer names exist in Column B
- Phone numbers should be in Column AC (index 28)

### Form doesn't auto-clear after submit
- Check for errors during submission
- Auto-clear only happens on success
- Look for JavaScript errors in browser console

## Future Expansion Plans

The system is being expanded to include:
1. **Admin Dashboard** - View orders needing attention (not paid, missing invoices)
2. **Marketing Hub** - Instagram/Facebook integration
3. **Customer Analytics** - Sales trends, top customers, product performance
4. **Inventory Tracking** - Stock levels, reorder alerts

When building new features:
- Keep order entry UI simple (mobile-first)
- Create separate admin views in new files (e.g., `streamlit_app/admin.py`)
- Use same Google Sheets as single source of truth
- Maintain zero-cost architecture (free tiers only)
