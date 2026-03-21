# Google Sheets Column Mapping Helper

This guide helps you identify and update the column mapping for your Google Sheets.

## Step 1: Open Your Spreadsheet

Open your "PIZZA TIME" Google Sheets spreadsheet.

## Step 2: Identify Column Letters

Excel and Google Sheets use letters for columns:
- A = 0
- B = 1
- C = 2
- ...
- Z = 25
- AA = 26
- AB = 27

## Step 3: Map Your Columns

Fill in the table below with your actual column letters:

| Data Field | Expected Column Letter | Your Column Letter | Index (0-based) |
|------------|------------------------|--------------------|-----------------:|
| Row ID | A | _______ | _______ |
| Customer Name | B | _______ | _______ |
| Order Date | C | _______ | _______ |
| Payment Method | D | _______ | _______ |
| Total Amount (₪) | E | _______ | _______ |
| **Products (Qty + Price)** | | | |
| Neapolitan Kit Qty | F | _______ | _______ |
| Neapolitan Kit Price | G | _______ | _______ |
| Spelt Kit Qty | H | _______ | _______ |
| Spelt Kit Price | I | _______ | _______ |
| Gluten-free Kit Qty | J | _______ | _______ |
| Gluten-free Kit Price | K | _______ | _______ |
| Neapolitan Dough Qty | L | _______ | _______ |
| Neapolitan Dough Price | M | _______ | _______ |
| Spelt Dough Qty | N | _______ | _______ |
| Spelt Dough Price | O | _______ | _______ |
| Gluten-free Dough Qty | P | _______ | _______ |
| Gluten-free Dough Price | Q | _______ | _______ |
| White Sauce Qty | R | _______ | _______ |
| White Sauce Price | S | _______ | _______ |
| Red Sauce Qty | T | _______ | _______ |
| Red Sauce Price | U | _______ | _______ |
| Opening Flour Qty | V | _______ | _______ |
| Opening Flour Price | W | _______ | _______ |
| Cheese Qty | X | _______ | _______ |
| Cheese Price | Y | _______ | _______ |
| **Automation Columns** | | | |
| Create Invoice Flag | Z | _______ | _______ |
| Invoice URL | AA | _______ | _______ |
| Status/Error | AB | _______ | _______ |

## Step 4: Convert Letters to Indices

Use this conversion chart:

```
A=0   B=1   C=2   D=3   E=4   F=5   G=6   H=7   I=8   J=9
K=10  L=11  M=12  N=13  O=14  P=15  Q=16  R=17  S=18  T=19
U=20  V=21  W=22  X=23  Y=24  Z=25  AA=26 AB=27 AC=28 AD=29
```

## Step 5: Update src/google_sheets.py

Open `src/google_sheets.py` and find the column constants (around line 17-28):

```python
# Column indices (0-based) - UPDATE these to match your actual sheet structure
COL_ROW_ID = 0
COL_CUSTOMER_NAME = 1
COL_DATE = 2
COL_PAYMENT_METHOD = 3
COL_TOTAL_AMOUNT = 4

# Product columns start at index 5 (each product has 2 columns: qty, price)
COL_PRODUCTS_START = 5
NUM_PRODUCTS = 10

# After products (5 + 10*2 = 25), we have:
COL_CREATE_INVOICE = 25  # "create invoice" flag
COL_INVOICE_URL = 26     # Invoice URL (filled after creation)
COL_STATUS = 27          # Status/error message
```

Replace the numbers with your indices from the table above.

## Step 6: Verify Product Order

Make sure the product order in `src/google_sheets.py` matches your sheet.

Find the `PRODUCT_NAMES` list (around line 30-41):

```python
PRODUCT_NAMES = [
    "ערכה נפוליטנית",    # Neapolitan Kit
    "ערכה כוסמין",       # Spelt Kit
    "ערכה ללא גלוטן",    # Gluten-free Kit
    "בצק נפוליטני",      # Neapolitan Dough
    "בצק כוסמין",        # Spelt Dough
    "בצק ללא גלוטן",     # Gluten-free Dough
    "רוטב לבן",          # White Sauce
    "רוטב אדום",         # Red Sauce
    "קמח פתיחה",         # Opening Flour
    "גבינה",             # Cheese
]
```

**Important:** The order in this list MUST match the order of columns in your Google Sheets!

If your sheet has products in a different order, reorder this list to match.

## Step 7: Update streamlit_app/products.py

Make sure the products in `streamlit_app/products.py` match your Google Sheets columns.

The products should be in the SAME ORDER as your sheet columns.

## Example: If Your Sheet is Different

### Scenario: Your sheet has Customer Name in column A, Date in B, Row ID in C

**Original (expected):**
```python
COL_ROW_ID = 0          # Column A
COL_CUSTOMER_NAME = 1   # Column B
COL_DATE = 2            # Column C
```

**Your mapping:**
```python
COL_CUSTOMER_NAME = 0   # Column A
COL_DATE = 1            # Column B
COL_ROW_ID = 2          # Column C
```

## Quick Test

After updating the column mapping:

1. Create a `.env` file with your credentials
2. Run the verification script:
   ```bash
   python verify_setup.py
   ```
3. Test locally:
   ```bash
   python src/main.py
   ```
4. Check if it reads your pending orders correctly

## Common Issues

### Issue: "Index out of range" error

**Cause:** Column index is higher than the number of columns in your sheet

**Fix:** Double-check your column indices. Count from 0 (A=0, B=1, etc.)

### Issue: Wrong data appears in fields

**Cause:** Column mapping doesn't match your sheet structure

**Fix:** Verify each column index matches the actual data in that column

### Issue: Products not extracted

**Cause:** Product columns don't start where expected, or product order is wrong

**Fix:**
1. Verify `COL_PRODUCTS_START` points to the first product quantity column
2. Verify products are in the same order as `PRODUCT_NAMES` list

## Need Help?

If you're stuck:

1. Make a test row in your Google Sheets
2. Note which column each field appears in
3. Use the conversion chart above to get the index
4. Update the constants in `google_sheets.py`
5. Test with `python src/main.py`

## Visual Example

```
Google Sheets Row:

A      B         C          D          E      F    G      H    I    ...
───────────────────────────────────────────────────────────────────
uuid   John Doe  15/03/24   דיגיטלי   150    2    50     1    10   ...
       ▲         ▲          ▲         ▲      ▲    ▲      ▲    ▲
       │         │          │         │      │    │      │    │
       │         │          │         │      │    │      │    │
Col:   1         2          3         4      5    6      7    8

Code mapping:
COL_CUSTOMER_NAME = 1      (Column B)
COL_DATE = 2               (Column C)
COL_PAYMENT_METHOD = 3     (Column D)
COL_TOTAL_AMOUNT = 4       (Column E)
COL_PRODUCTS_START = 5     (Column F - first product qty)
```
