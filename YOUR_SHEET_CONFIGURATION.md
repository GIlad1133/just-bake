# Your Google Sheet Configuration

This document shows the exact column mapping configured for your "PIZZA TIME" 2026 sheet.

## ✅ Configuration Complete!

Your code has been updated to match your Google Sheet structure.

## Column Mapping

| Column | Index | Field | Notes |
|--------|-------|-------|-------|
| **A** | 0 | Date | DD/MM/YYYY format |
| **B** | 1 | Customer Name | |
| **C** | 2 | Amount (₪) | Total in shekels |
| **D** | 3 | payment method | דיגיטלי, מזומן, העברה, Paybox, etc. |
| **E** | 4 | create invoice | "yes" triggers automation |
| **F** | 5 | invoice_url | Filled by automation after invoice created |
| **G** | 6 | Neapolitan Kit Qty | |
| **H** | 7 | Neapolitan Kit Price | |
| **I** | 8 | Spelt Kit Qty | |
| **J** | 9 | Spelt Kit Price | |
| **K** | 10 | Gluten-free Kit Qty | |
| **L** | 11 | Gluten-free Kit Price | |
| **M** | 12 | Neapolitan Dough Qty | |
| **N** | 13 | Neapolitan Dough Price | |
| **O** | 14 | Spelt Dough Qty | |
| **P** | 15 | Spelt Dough Price | |
| **Q** | 16 | Gluten-free Dough Qty | |
| **R** | 17 | Gluten-free Dough Price | |
| **S** | 18 | White Sauce Qty | |
| **T** | 19 | White Sauce Price | |
| **U** | 20 | Red Sauce Qty | |
| **V** | 21 | Red Sauce Price | |
| **W** | 22 | Opening Flour Qty | |
| **X** | 23 | Opening Flour Price | |
| **Y** | 24 | **Cheese PRICE** | ⚠️ SWAPPED! |
| **Z** | 25 | **Cheese QTY** | ⚠️ SWAPPED! |
| **AA** | 26 | RowId | Unique identifier |
| **AB** | 27 | Status/Error | Filled by automation on errors |

## ⚠️ Important Notes

### 1. Cheese Columns Are Swapped!

Unlike all other products (which have Qty, Price), Cheese has:
- **Y (24):** Cheese **Price** (not Qty!)
- **Z (25):** Cheese **Qty** (not Price!)

The code has been updated to handle this correctly.

### 2. RowId at the End

Your RowId is in column AA (26), not at the beginning. The code handles this.

### 3. Status Column

Column AB (27) will be used for error messages when invoice creation fails.

## What Was Updated

### ✅ `src/google_sheets.py`
- Column indices updated to match your sheet
- Special handling for swapped Cheese columns
- RowId read from column AA instead of column A

### ✅ `streamlit_app/app.py`
- Row data written in correct column order
- Cheese columns written in swapped order (Price, Qty)
- RowId written to column AA

## Example Row from Your Sheet

From row 2:
```
A: 2026-01-01        (Date)
B: ענבר גלוסקא       (Customer Name)
C: 260.0             (Amount ₪)
D: Paybox            (Payment method)
E: yes               (create invoice)
F: (empty)           (invoice_url - filled by automation)
G: 2.0               (Neapolitan Kit Qty)
H: 130.0             (Neapolitan Kit Price)
I-Z: (other products)
AA: 1.0              (RowId)
```

## Next Steps

Your configuration is complete! Now you need:

1. **Add Keep.co.il credentials to `.env`:**
   ```bash
   # Edit the .env file
   nano .env

   # Replace these lines with your actual credentials:
   KEEP_CLIENT_ID=your-actual-keep-client-id
   KEEP_CLIENT_SECRET=your-actual-keep-client-secret
   ```

2. **Test locally:**
   ```bash
   # Run the verification script
   python verify_setup.py

   # Test the automation (make sure you have a row with "create invoice" = "yes")
   python src/main.py
   ```

3. **Deploy to production** (follow QUICK_START.md)

## Troubleshooting

### Issue: Products not extracted correctly

**Check:** Make sure product quantities and prices are in the correct columns (G-Z)

### Issue: Cheese total doesn't match

**Likely cause:** The swapped columns. The code now handles this automatically.

### Issue: RowId not found

**Check:** Make sure column AA (26) has a value for each row

## Questions?

Refer to:
- **QUICK_START.md** - Next steps for deployment
- **README.md** - Full documentation
- **SETUP_GUIDE.md** - Detailed setup instructions
