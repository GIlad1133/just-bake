# Business Customer (B2B) Support

Added support for business customers who need invoices with their tax ID (ח.פ. / עוסק מורשה).

## ✅ What Was Added

### Google Sheet Columns
- **Column AC (28)**: Phone Number (optional for all customers)
- **Column AD (29)**: Business ID / ח.פ. (optional, for B2B customers only)

### Streamlit Order Entry UI
- Phone Number field (optional)
- Business Customer section (collapsible)
  - Business ID input field
  - Automatically included in invoice when provided

### Invoice Format
When Business ID is provided, the invoice includes:
```json
"client": {
  "name": "Company Name Ltd",
  "phone": "050-1234567",
  "hp": "123456789"  // Business tax ID
}
```

## 📋 How to Use

### For Regular Customers (B2C)
1. Enter customer name
2. Enter phone number (optional but recommended)
3. Leave Business ID empty
4. Enter order details

**Result:** Regular receipt without business tax ID

### For Business Customers (B2B)
1. Enter business/company name
2. Enter phone number
3. **Expand "Business Customer (B2B)" section**
4. **Enter Business ID (ח.פ. / עוסק מורשה)**
5. Enter order details

**Result:** Tax invoice (חשבונית מס) with business ID - customer can claim input VAT

## 🔍 Examples

### Example 1: Regular Customer
```
Customer Name: יוסי כהן
Phone: 050-1234567
Business ID: (empty)
→ Creates regular receipt
```

### Example 2: Business Customer
```
Customer Name: פיצריית האיטלקי בע"מ
Phone: 03-5551234
Business ID: 515123456
→ Creates tax invoice with ח.פ. 515123456
```

## ⚠️ Important Notes

1. **Business ID Format:**
   - Usually 9 digits
   - No dashes or spaces
   - Example: `515123456`

2. **When to Use:**
   - Use for registered businesses (בע"מ, עוסק מורשה, חברה)
   - Don't use for regular customers
   - Required for B2B customers to claim VAT deduction

3. **Validation:**
   - System doesn't validate Business ID format
   - Make sure to enter correct ID
   - Incorrect ID may cause issues with customer's accounting

## 🧪 Testing

Test with your own business ID to verify:
1. Invoice shows business name correctly
2. Business ID (ח.פ.) appears on invoice
3. Customer can download and use for accounting

## 📊 Google Sheet Structure

Columns have been added:
```
...
AA (26): RowId
AB (27): Status
AC (28): Phone Number     ← NEW
AD (29): Business ID      ← NEW
```

Both fields are optional and can be left empty.
