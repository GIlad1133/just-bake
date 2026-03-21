# Just Bake - Quick Start Guide

Get your invoice automation system running in 30 minutes!

## What You're Building

✅ **Order Entry Web App** - Enter orders from any device (phone/computer)
✅ **Automated Invoice Creation** - Creates invoices every 6 hours automatically
✅ **Zero Cost** - Completely free using Streamlit Cloud + GitHub Actions

## Prerequisites (Gather These First)

Before you start, make sure you have:

- [ ] Google Cloud service account JSON file
- [ ] Your Google Sheets spreadsheet ID
- [ ] Keep.co.il Client ID
- [ ] Keep.co.il Client Secret
- [ ] GitHub account
- [ ] Streamlit Cloud account (sign up at streamlit.io - free)

**Don't have these?** See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed instructions.

## 5-Step Setup

### Step 1: Configure Column Mapping (5 minutes)

The code needs to know where your data is in Google Sheets.

1. Open your "PIZZA TIME" spreadsheet
2. Open [COLUMN_MAPPING_HELPER.md](COLUMN_MAPPING_HELPER.md)
3. Fill in the column letters (A, B, C, etc.) for each field
4. Convert letters to numbers using the chart (A=0, B=1, etc.)
5. Edit `src/google_sheets.py` and update the constants:

```python
COL_ROW_ID = 0              # Your Row ID column
COL_CUSTOMER_NAME = 1       # Your Customer Name column
COL_DATE = 2                # Your Date column
# ... etc
```

### Step 2: Test Locally (5 minutes)

Make sure everything works on your computer first.

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Edit .env and add your credentials
# (Use your favorite text editor)

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify setup
python verify_setup.py

# 5. Test automation (optional - requires a pending order)
python src/main.py
```

**Tip:** Create a test order in your Google Sheets with "create invoice" = "yes" to test invoice creation.

### Step 3: Deploy Order Entry UI (10 minutes)

Get your web-based order form live.

1. **Push code to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit: Just Bake invoice automation"
   git remote add origin <your-github-repo-url>
   git push -u origin main
   ```

2. **Deploy to Streamlit Cloud:**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Click "New app"
   - Select your repository
   - Main file: `streamlit_app/app.py`
   - Click "Deploy!"

3. **Add secrets** (in Streamlit Cloud UI):
   - App menu (⋯) → Settings → Secrets
   - Copy from `.streamlit/secrets.toml.example`
   - Fill in your actual credentials
   - Click "Save"

4. **Test it:**
   - Visit your app URL (e.g., `https://just-bake.streamlit.app`)
   - Enter a test order
   - Check Google Sheets - order should appear!

### Step 4: Deploy Automation (5 minutes)

Set up automatic invoice creation.

1. **Add secrets to GitHub:**
   - Go to your repository → Settings → Secrets and variables → Actions
   - Click "New repository secret" for each:
     - `GOOGLE_SHEETS_CREDENTIALS` (paste your service account JSON)
     - `GOOGLE_SHEETS_SPREADSHEET_ID`
     - `KEEP_CLIENT_ID`
     - `KEEP_CLIENT_SECRET`
     - `KEEP_API_BASE_URL` (usually `https://api.keepo.co.il`)

2. **Enable GitHub Actions:**
   - Go to Actions tab
   - Click "I understand my workflows, go ahead and enable them"

3. **Test manual run:**
   - Actions tab → "Invoice Automation" → "Run workflow"
   - Watch the logs
   - Check Google Sheets - invoices should be created!

### Step 5: Verify Everything (5 minutes)

Final checklist:

- [ ] Streamlit app loads and accepts orders
- [ ] Orders appear in Google Sheets with "create invoice" = "yes"
- [ ] GitHub Actions workflow runs successfully
- [ ] Invoices created in Keep.co.il
- [ ] Google Sheets updated with invoice URLs and status "Done"
- [ ] Error handling works (try an order with mismatched total)

## You're Done!

🎉 Your invoice automation system is now live!

### What Happens Now?

**Every 6 hours automatically:**
- GitHub Actions checks for pending orders
- Creates invoices via Keep.co.il
- Updates Google Sheets with results

**Anytime you want:**
- Use Streamlit app to enter new orders
- Manually trigger automation from GitHub Actions

### Next Steps

1. **Parallel Run with n8n** (recommended for 1-2 weeks)
   - Keep both systems running
   - Compare results
   - When confident, disable n8n

2. **Customize** (optional)
   - Add more products to `streamlit_app/products.py`
   - Adjust automation schedule in `.github/workflows/invoice-automation.yml`
   - Customize Streamlit theme in `.streamlit/config.toml`

3. **Monitor**
   - Check GitHub Actions logs occasionally
   - Review Google Sheets error column
   - Everything should run smoothly!

## Troubleshooting

### Issue: Streamlit app shows "Access denied"

**Fix:** Make sure you shared your Google Sheets with the service account email (in the JSON credentials).

### Issue: GitHub Actions workflow fails

**Fix:** Check that all 5 secrets are added correctly in GitHub repository settings.

### Issue: Invoice created but no URL

**Fix:** The Keep.co.il API response format may differ. Check the error message in Google Sheets.

### Issue: Total mismatch error

**Fix:** Verify the total in your sheet matches the sum of (quantity × price) for all products.

## Need More Help?

- **Detailed setup:** [SETUP_GUIDE.md](SETUP_GUIDE.md)
- **Architecture overview:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **Column mapping help:** [COLUMN_MAPPING_HELPER.md](COLUMN_MAPPING_HELPER.md)
- **Full documentation:** [README.md](README.md)

## Cost Reminder

Your entire system runs for **₪0 per month**:
- Streamlit Cloud: FREE
- GitHub Actions: FREE
- Google Sheets API: FREE
- Keep.co.il API: Included in subscription

## Questions?

The system is designed to be:
- ✅ Zero maintenance (runs automatically)
- ✅ Zero cost (free tiers for everything)
- ✅ Accessible anywhere (web-based)
- ✅ More maintainable than n8n (code-based)

Enjoy your automated pizza business! 🍕
