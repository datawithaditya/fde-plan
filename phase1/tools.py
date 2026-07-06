import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

RATE_DIR       = r"D:\System_Data\Desktop\Work\Project\Rate Approval\Automation - UI"
ITEMS_FILE     = os.path.join(RATE_DIR, "items.xlsx")
DP_FILE        = os.path.join(RATE_DIR, "DP.xlsx")
CUSTOMERS_FILE = os.path.join(RATE_DIR, "Customers.xlsx")

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
# TOOL 3 — Look up customer state from Customers.xlsx
# --------------------------------------------------
def lookup_customer_state(customer_name: str) -> dict:
    """Return the state/region code for a customer from Customers.xlsx."""
    try:
        df = pd.read_excel(CUSTOMERS_FILE)
        df["Customer Name"] = df["Cust Name"].astype(str).str.strip()
        df["State"]         = df["Dimension Value Code"].astype(str).str.strip().str.upper()

        row = df[df["Customer Name"].str.upper() == customer_name.strip().upper()]
        if row.empty:
            return {"found": False, "customer_name": customer_name,
                    "error": "Customer not found in master"}

        return {"found": True, "customer_name": customer_name,
                "state": row.iloc[0]["State"]}
    except Exception as e:
        return {"found": False, "customer_name": customer_name, "error": str(e)}


# --------------------------------------------------
# TOOL 4 — Validate a proposed rate for customer + item
# --------------------------------------------------
def validate_rate(customer: str, item_no: str, proposed_rate: float) -> dict:
    """
    Check whether a proposed rate passes approval rules.
    Returns status (PASS/FAIL/SKIP), the reference rate used, and which rule decided it.
    Note: rules requiring transaction history (date_history, percent_increase) are
    skipped — they need TechOfferRDLC.xlsx which is only available during a live run.
    """
    try:
        # ── Fetch live conditions ──────────────────────────────
        resp = requests.get(API_URL, headers={"Authorization": f"Bearer {API_TOKEN}"}, timeout=10)
        if resp.status_code != 200:
            return {"status": "ERROR", "error": f"API returned {resp.status_code}"}

        rules = [r for r in resp.json().get("rules", []) if r.get("enabled", True)]

        # ── Load data files ────────────────────────────────────
        item_df = pd.read_excel(ITEMS_FILE, header=2)
        item_df["No."]            = item_df["No."].astype(str).str.strip()
        item_df["SPECIAL CATEGO."]= item_df["SPECIAL CATEGO."].astype(str).str.strip()
        item_df["ITEM BRAND"]     = item_df["ITEM BRAND"].astype(str).str.strip()

        cust_df = pd.read_excel(CUSTOMERS_FILE)
        cust_df["Customer Name"] = cust_df["Cust Name"].astype(str).str.strip()
        cust_df["State"]         = cust_df["Dimension Value Code"].astype(str).str.strip().str.upper()

        dp_df = pd.read_excel(DP_FILE, sheet_name="Final", header=0, usecols=[0, 4])
        dp_df.columns    = ["Item No", "Dealer Price"]
        dp_df["Item No"] = dp_df["Item No"].astype(str).str.strip()
        dp_df["Dealer Price"] = pd.to_numeric(dp_df["Dealer Price"], errors="coerce")
        dp_map = dp_df.dropna(subset=["Dealer Price"]).set_index("Item No")["Dealer Price"].to_dict()

        # ── Item attributes ────────────────────────────────────
        item_row      = item_df[item_df["No."] == item_no.strip()]
        item_brand    = item_row["ITEM BRAND"].iloc[0]      if not item_row.empty else ""
        special_categ = item_row["SPECIAL CATEGO."].iloc[0] if not item_row.empty else ""

        # ── Walk rules ─────────────────────────────────────────
        for rule in rules:
            name   = rule.get("name", rule["id"])
            action = rule.get("action", {})
            atype  = action.get("type")

            if not _matches_full(rule.get("match", {}), item_brand, special_categ, item_no, customer):
                continue

            if atype == "min_rate":
                ref = float(action.get("min_rate", 0))
                return {"status": "PASS" if proposed_rate >= ref else "FAIL",
                        "ref_rate": ref, "rule": name, "proposed": proposed_rate}

            elif atype == "state_min_rate":
                crow = cust_df[cust_df["Customer Name"].str.upper() == customer.strip().upper()]
                if crow.empty:
                    return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                            "rule": f"CUSTOMER_NOT_FOUND [{name}]"}
                state = crow["State"].iloc[0]
                ref   = action.get("state_rates", {}).get(state)
                if ref is None:
                    return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                            "rule": f"STATE_NOT_MAPPED [{state}] [{name}]"}
                ref = float(ref)
                return {"status": "PASS" if proposed_rate >= ref else "FAIL",
                        "ref_rate": ref, "rule": f"{name} [{state}]", "proposed": proposed_rate}

            elif atype == "discount":
                pct = float(action.get("percent", 0))
                dp  = dp_map.get(item_no.strip())
                if dp is None:
                    return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                            "rule": f"DP_NOT_FOUND [{name}]"}
                ref = round(dp * (1 - pct / 100))
                return {"status": "PASS" if proposed_rate >= ref else "FAIL",
                        "ref_rate": ref, "rule": f"DISCOUNT -{pct}% [{name}]", "proposed": proposed_rate}

            elif atype == "sku_rate_table":
                table    = action.get("sku_table", {})
                entry    = table.get(item_no.strip())
                fallback = action.get("fallback", "continue")
                if entry is None:
                    if fallback == "fail":
                        return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                                "rule": f"SKU_NOT_FOUND [{name}]"}
                    if fallback == "skip":
                        return {"status": "SKIP", "ref_rate": None, "proposed": proposed_rate,
                                "rule": f"SKU_AUTO_SKIP [{name}]"}
                    continue
                if entry.get("rate") is not None:
                    ref = float(entry["rate"])
                    return {"status": "PASS" if proposed_rate >= ref else "FAIL",
                            "ref_rate": ref, "rule": f"SKU_RATE [{name}]", "proposed": proposed_rate}
                if entry.get("discount") is not None:
                    dp = dp_map.get(item_no.strip())
                    if dp is None:
                        return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                                "rule": f"DP_NOT_FOUND [{name}]"}
                    ref = round(dp * (1 - float(entry["discount"]) / 100))
                    return {"status": "PASS" if proposed_rate >= ref else "FAIL",
                            "ref_rate": ref, "rule": f"SKU_DISC -{entry['discount']}% [{name}]",
                            "proposed": proposed_rate}
                continue

            elif atype in ("date_history", "percent_increase"):
                continue  # needs TechOfferRDLC — not available in agent mode

            elif atype == "fail":
                return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                        "rule": f"BLOCKED [{name}]"}

            elif atype == "skip":
                return {"status": "SKIP", "ref_rate": None, "proposed": proposed_rate,
                        "rule": f"AUTO_APPROVED [{name}]"}

        return {"status": "FAIL", "ref_rate": None, "proposed": proposed_rate,
                "rule": "NO_RULE_MATCHED"}

    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


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
# Match helper WITH customer context (used by validate_rate)
# --------------------------------------------------
def _matches_full(match: dict, item_brand: str, special_categ: str,
                  item_no: str, customer: str) -> bool:
    field    = match.get("field",    "always")
    operator = match.get("operator", "always")
    value    = match.get("value")

    if field == "always" or operator == "always":
        return True

    actual = {
        "item_brand":       (item_brand    or "").strip(),
        "special_category": (special_categ or "").strip(),
        "item_no":          (item_no       or "").strip(),
        "customer_name":    (customer      or "").strip(),
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
    {
        "type": "function",
        "function": {
            "name": "lookup_customer_state",
            "description": "Look up the state/region code for a customer from the customer master. Required for state-based rate rules (CO2 and similar).",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Full customer name as it appears in the system"}
                },
                "required": ["customer_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_rate",
            "description": "Check whether a proposed rate for a customer+item combination will PASS or FAIL approval. Returns status, the reference rate used, and which rule decided it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer":      {"type": "string",  "description": "Full customer name"},
                    "item_no":       {"type": "string",  "description": "Item number"},
                    "proposed_rate": {"type": "number",  "description": "The rate being proposed for approval"},
                },
                "required": ["customer", "item_no", "proposed_rate"],
            },
        },
    },
]

# --------------------------------------------------
# Dispatcher — call by name
# --------------------------------------------------
TOOL_MAP = {
    "get_dp_price":          get_dp_price,
    "get_discount_rule":     get_discount_rule,
    "lookup_customer_state": lookup_customer_state,
    "validate_rate":         validate_rate,
}
