import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

RATE_DIR  = r"D:\System_Data\Desktop\Work\Project\Rate Approval\Automation - UI"
ITEMS_FILE = os.path.join(RATE_DIR, "items.xlsx")
DP_FILE    = os.path.join(RATE_DIR, "DP.xlsx")

API_URL   = "https://dnhrateapproval.pythonanywhere.com/api/rate_conditions"
API_TOKEN = os.getenv("RATE_API_TOKEN", "12088566f9d79789ea4e9fc5946c16ebc7493fc0549dc677b4412de50e23f006")


# --------------------------------------------------
# TOOL 1 — Get DP (dealer) price for an item
# --------------------------------------------------
def get_dp_price(item_no: str) -> dict:
    """Read DP.xlsx and return the dealer base price for the item."""
    try:
        df = pd.read_excel(DP_FILE, sheet_name="Final", header=0, usecols=[0, 4])
        df.columns = ["Item No", "Dealer Price"]
        df["Item No"]      = df["Item No"].astype(str).str.strip()
        df["Dealer Price"] = pd.to_numeric(df["Dealer Price"], errors="coerce")
        df = df.dropna(subset=["Dealer Price"])

        row = df[df["Item No"] == item_no.strip()]
        if row.empty:
            return {"found": False, "item_no": item_no,
                    "error": "Item not found in DP price list"}

        return {"found": True, "item_no": item_no,
                "dp_price": float(row.iloc[0]["Dealer Price"])}
    except Exception as e:
        return {"found": False, "item_no": item_no, "error": str(e)}


# --------------------------------------------------
# TOOL 2 — Fetch applicable discount rule from live server
# --------------------------------------------------
def get_discount_rule(item_no: str) -> dict:
    """
    Fetch conditions from the live rate-approval server, look up the item's
    brand + category, walk the rules, and return the first matching rule
    with its discount/rate details.
    """
    try:
        # Step A — call live API
        resp = requests.get(
            API_URL,
            headers={"Authorization": f"Bearer {API_TOKEN}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return {"found": False, "item_no": item_no,
                    "error": f"API error {resp.status_code}"}

        conditions = resp.json()
        rules = [r for r in conditions.get("rules", []) if r.get("enabled", True)]

        # Step B — load item master for brand + category
        item_df = pd.read_excel(ITEMS_FILE, header=2)
        item_df["No."]            = item_df["No."].astype(str).str.strip()
        item_df["SPECIAL CATEGO."]= item_df["SPECIAL CATEGO."].astype(str).str.strip()
        item_df["ITEM BRAND"]     = item_df["ITEM BRAND"].astype(str).str.strip()

        item_row        = item_df[item_df["No."] == item_no.strip()]
        item_brand      = item_row["ITEM BRAND"].iloc[0]      if not item_row.empty else ""
        special_categ   = item_row["SPECIAL CATEGO."].iloc[0] if not item_row.empty else ""

        # Step C — walk rules, return first match
        for rule in rules:
            if not _matches(rule.get("match", {}), item_brand, special_categ, item_no):
                continue

            action = rule.get("action", {})
            atype  = action.get("type")
            result = {
                "found":          True,
                "item_no":        item_no,
                "item_brand":     item_brand,
                "special_categ":  special_categ,
                "rule_name":      rule.get("name"),
                "rule_type":      atype,
            }

            if atype == "min_rate":
                result["min_rate"] = action.get("min_rate")

            elif atype == "discount":
                result["discount_percent"] = action.get("percent")
                result["note"] = "Apply this % discount to the DP price to get the min rate"

            elif atype == "sku_rate_table":
                table = action.get("sku_table", {})
                entry = table.get(item_no.strip())
                if entry:
                    result["sku_entry"] = entry
                else:
                    result["note"] = "Item not in SKU table — fallback applies"

            elif atype == "fail":
                result["note"] = "This item is BLOCKED — will always fail approval"

            elif atype == "skip":
                result["note"] = "This item is AUTO-APPROVED — no rate check needed"

            return result

        return {"found": False, "item_no": item_no,
                "error": "No matching rule found for this item"}

    except Exception as e:
        return {"found": False, "item_no": item_no, "error": str(e)}


# --------------------------------------------------
# Match helper (item-only, no customer context)
# --------------------------------------------------
def _matches(match: dict, item_brand: str, special_categ: str, item_no: str) -> bool:
    field    = match.get("field",    "always")
    operator = match.get("operator", "always")
    value    = match.get("value")

    if field == "always" or operator == "always":
        return True
    if field == "customer_name":   # skip customer-only rules
        return False

    actual = {
        "item_brand":       (item_brand    or "").strip(),
        "special_category": (special_categ or "").strip(),
        "item_no":          (item_no       or "").strip(),
    }.get(field, "")

    if operator == "equals":
        return actual.upper() == str(value or "").strip().upper()
    if operator == "in_list":
        return actual.upper() in [str(v).strip().upper() for v in (value or [])]
    if operator == "not_in_list":
        return actual.upper() not in [str(v).strip().upper() for v in (value or [])]
    if operator == "contains":
        return str(value or "").strip().upper() in actual.upper()
    if operator == "starts_with":
        return actual.upper().startswith(str(value or "").strip().upper())
    return False


# --------------------------------------------------
# JSON schemas — what the LLM sees
# --------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_dp_price",
            "description": (
                "Look up the dealer base price (DP price) for an item number "
                "from the DP price list. Use this first before calculating any discounted rate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_no": {
                        "type": "string",
                        "description": "The item number, e.g. 'ABC1234'",
                    }
                },
                "required": ["item_no"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discount_rule",
            "description": (
                "Fetch the applicable discount rule for an item from the live "
                "rate-approval server. Returns the rule type and discount % or "
                "min rate. Use this to know what discount applies to the item."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_no": {
                        "type": "string",
                        "description": "The item number, e.g. 'ABC1234'",
                    }
                },
                "required": ["item_no"],
            },
        },
    },
]

# --------------------------------------------------
# Dispatcher — call by name
# --------------------------------------------------
TOOL_MAP = {
    "get_dp_price":       get_dp_price,
    "get_discount_rule":  get_discount_rule,
}
