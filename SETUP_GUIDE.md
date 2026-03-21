# Just Bake - Quick Setup Guide

This guide will help you get the Just Bake invoice automation system up and running.

## Step 1: Google Sheets Column Mapping

**IMPORTANT:** Before deploying, you need to update the column mapping in `src/google_sheets.py` to match your actual Google Sheets structure.

### Current Expected Structure

The code currently expects this column order (A=0, B=1, C=2, etc.):

| Column | Field | Type |
|--------|-------|------|
| A (0) | Row ID | UUID |
| B (1) | Customer Name | Text |
| C (2) | Date | Date |
| D (3) | Payment Method | Text (דיגיטלי/מזומן/העברה) |
| E (4) | Total Amount (₪) | Number |
| F-G (5-6) | Neapolitan Kit (Qty, Price) | Numbers |
| H-I (7-8) | Spelt Kit (Qty, Price) | Numbers |
| J-K (9-10) | Gluten-free Kit (Qty, Price) | Numbers |
| L-M (11-12) | Neapolitan Dough (Qty, Price) | Numbers |
| N-O (13-14) | Spelt Dough (Qty, Price) | Numbers |
| P-Q (15-16) | Gluten-free Dough (Qty, Price) | Numbers |
| R-S (17-18) | White Sauce (Qty, Price) | Numbers |
| T-U (19-20) | Red Sauce (Qty, Price) | Numbers |
| V-W (21-22) | Opening Flour (Qty, Price) | Numbers |
| X-Y (23-24) | Cheese (Qty, Price) | Numbers |
| Z (25) | Create Invoice Flag | Text ("yes" to trigger) |
| AA (26) | Invoice URL | Text (filled by automation) |
| AB (27) | Status/Error | Text (filled by automation) |

### How to Update Column Mapping

1. Open your Google Sheets "PIZZA TIME" spreadsheet
2. Note the actual column positions (A=0, B=1, etc.)
3. Edit `src/google_sheets.py`:

```python
# Around line 17-28, update these constants:
COL_ROW_ID = 0              # Column A
COL_CUSTOMER_NAME = 1       # Column B
COL_DATE = 2                # Column C
COL_PAYMENT_METHOD = 3      # Column D
COL_TOTAL_AMOUNT = 4        # Column E
COL_PRODUCTS_START = 5      # Column F (first product qty)
NUM_PRODUCTS = 10
COL_CREATE_INVOICE = 25     # Column Z
COL_INVOICE_URL = 26        # Column AA
COL_STATUS = 27             # Column AB
```

4. Verify the product order matches your sheet (around line 30-41)

## Step 2: Google Cloud Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use existing)
3. Enable **Google Sheets API**:
   - Go to "APIs & Services" → "Library"
   - Search for "Google Sheets API"
   - Click "Enable"
4. Create service account:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Name: "just-bake-automation"
   - Click "Create and Continue"
   - Skip role assignment (click "Continue")
   - Click "Done"
5. Create JSON key:
   - Click on the service account you just created
   - Go to "Keys" tab
   - Click "Add Key" → "Create new key"
   - Choose "JSON"
   - Download the JSON file (keep it safe!)
6. Share your Google Sheets:
   - Open your "PIZZA TIME" spreadsheet
   - Click "Share"
   - Copy the service account email (looks like `just-bake-automation@your-project.iam.gserviceaccount.com`)
   - Paste it in the share dialog
   - Give "Editor" access
   - Click "Share"

## Step 3: Get Keep.co.il API Credentials

You should already have these from your n8n workflow. If not:

1. Log in to Keep.co.il
2. Go to API settings
3. Generate or copy your:
   - Client ID
   - Client Secret
   - API Base URL (usually `https://api.keepo.co.il`)

## Step 4: Deploy Streamlit Order Entry UI

### 4.1 Push Code to GitHub

```bash
# Initialize git (if not already done)
git init
git add .
git commit -m "Initial commit: Just Bake invoice automation"

# Create GitHub repository and push
# (Follow GitHub instructions to create new repository)
git remote add origin <your-github-repo-url>
git branch -M main
git push -u origin main
```

### 4.2 Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select:
   - **Repository:** your-username/just-bake
   - **Branch:** main
   - **Main file path:** `streamlit_app/app.py`
5. Click "Deploy!"

### 4.3 Add Secrets to Streamlit

1. Once deployed, click on the app menu (⋯) → "Settings"
2. Go to "Secrets" tab
3. Paste your secrets in TOML format:

```toml
[google_sheets_credentials]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "your-cert-url"

spreadsheet_id = "your-spreadsheet-id"
```

4. Click "Save"
5. App will restart automatically

### 4.4 Test Order Entry

1. Visit your Streamlit app URL (e.g., `https://just-bake.streamlit.app`)
2. Enter a test order
3. Check your Google Sheets - the order should appear with "create invoice" = "yes"

## Step 5: Deploy Invoice Automation (GitHub Actions)

### 5.1 Add Secrets to GitHub

1. Go to your GitHub repository
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Click "New repository secret"
4. Add each secret:

**Secret 1: GOOGLE_SHEETS_CREDENTIALS**
- Name: `GOOGLE_SHEETS_CREDENTIALS`
- Value: Your entire service account JSON file contents (as a single line, or multiline is fine)

**Secret 2: GOOGLE_SHEETS_SPREADSHEET_ID**
- Name: `GOOGLE_SHEETS_SPREADSHEET_ID`
- Value: Your spreadsheet ID (from the URL)

**Secret 3: KEEP_CLIENT_ID**
- Name: `KEEP_CLIENT_ID`
- Value: Your Keep.co.il client ID

**Secret 4: KEEP_CLIENT_SECRET**
- Name: `KEEP_CLIENT_SECRET`
- Value: Your Keep.co.il client secret

**Secret 5: KEEP_API_BASE_URL**
- Name: `KEEP_API_BASE_URL`
- Value: `https://api.keepo.co.il` (or your actual API URL)

### 5.2 Enable GitHub Actions

1. Go to "Actions" tab in your repository
2. If prompted, click "I understand my workflows, go ahead and enable them"

### 5.3 Test Manual Run

1. Go to "Actions" tab
2. Select "Invoice Automation" workflow
3. Click "Run workflow" dropdown
4. Click "Run workflow" button
5. Watch the workflow run (click on it to see logs)
6. Check your Google Sheets - invoices should be created and marked "Done"

## Step 6: Verify Everything Works

### Checklist

- [ ] Streamlit app is accessible from phone/computer
- [ ] Can submit test order via Streamlit app
- [ ] Order appears in Google Sheets with "create invoice" = "yes"
- [ ] GitHub Actions workflow runs successfully
- [ ] Invoice is created in Keep.co.il
- [ ] Google Sheets updated with invoice URL and status "Done"
- [ ] Error handling works (try submitting order with total mismatch)

## Step 7: Migration from n8n

### Parallel Running Period (Recommended: 1-2 weeks)

1. Keep both systems running:
   - n8n workflow: ON
   - GitHub Actions: ON
2. Compare invoices created by both systems
3. Verify they match exactly
4. Monitor for any discrepancies

### When You're Confident

1. Disable n8n workflow
2. Keep `invoice-flow.json` file in repository for reference
3. Document any differences or lessons learned

## Troubleshooting

### "Access denied" on Google Sheets

**Solution:**
- Make sure you shared the sheet with the service account email
- Grant "Editor" access (not just "Viewer")

### Streamlit app doesn't load

**Solution:**
- Check secrets are configured correctly in Streamlit Cloud
- Check app logs for errors (click on app → "Manage app" → "Logs")

### GitHub Actions workflow fails

**Solution:**
- Check secrets are added correctly in GitHub
- View workflow logs: Actions tab → click on failed run
- Common issues:
  - JSON syntax in GOOGLE_SHEETS_CREDENTIALS
  - Wrong spreadsheet ID
  - Wrong Keep.co.il credentials

### Invoice created but no URL

**Solution:**
- The Keep.co.il API response format may differ
- Edit `src/keep_client.py` → `get_receipt_url()` method
- Check the error message in Google Sheets (contains full API response)

## Next Steps

1. Customize the Streamlit app colors/logo if desired
2. Add more products if needed (edit `streamlit_app/products.py`)
3. Set up email notifications for failed invoices (future enhancement)
4. Consider adding a dashboard to view order history

## Support

For questions or issues:
- Check the main [README.md](README.md) file
- Review GitHub Actions logs
- Check Google Sheets error messages
- Compare with original n8n workflow (`invoice-flow.json`)
