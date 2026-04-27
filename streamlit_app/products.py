"""
Product definitions for Just Bake (Pashut La'afot).
Defines the 10 product types available for ordering.
"""

PRODUCTS = [
    {
        "name": "Neapolitan Kit",
        "hebrew": "ערכה נפוליטנית",
        "default_price": 0,
        "column_prefix": "neapolitan_kit"
    },
    {
        "name": "Spelt Kit",
        "hebrew": "ערכה כוסמין",
        "default_price": 0,
        "column_prefix": "spelt_kit"
    },
    {
        "name": "Gluten-free Kit",
        "hebrew": "ערכה ללא גלוטן",
        "default_price": 0,
        "column_prefix": "gluten_free_kit"
    },
    {
        "name": "Neapolitan Dough",
        "hebrew": "בצק נפוליטני",
        "default_price": 0,
        "column_prefix": "neapolitan_dough"
    },
    {
        "name": "Spelt Dough",
        "hebrew": "בצק כוסמין",
        "default_price": 0,
        "column_prefix": "spelt_dough"
    },
    {
        "name": "Gluten-free Dough",
        "hebrew": "בצק ללא גלוטן",
        "default_price": 0,
        "column_prefix": "gluten_free_dough"
    },
    {
        "name": "White Sauce",
        "hebrew": "רוטב לבן",
        "default_price": 0,
        "column_prefix": "white_sauce"
    },
    {
        "name": "Red Sauce",
        "hebrew": "רוטב אדום",
        "default_price": 0,
        "column_prefix": "red_sauce"
    },
    {
        "name": "Opening Flour",
        "hebrew": "קמח פתיחה",
        "default_price": 0,
        "column_prefix": "opening_flour"
    },
    {
        "name": "Cheese",
        "hebrew": "גבינה",
        "default_price": 0,
        "column_prefix": "cheese"
    },
    {
        "name": "Pizza Sandwich",
        "hebrew": "סנדאות פיצה",
        "default_price": 0,
        "column_prefix": "pizza_sandwich",
        "qty_col": 30,   # AE — appended after business_id to avoid shifting existing columns
        "price_col": 31, # AF
    },
]

PAYMENT_METHODS = {
    "not_paid": "לא שולם",  # Not paid yet
    "bit": "Bit",
    "paybox": "Paybox",
    "cash": "מזומן"
}
