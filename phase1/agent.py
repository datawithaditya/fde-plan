import os
import json
import logging
from dotenv import load_dotenv
from openai import OpenAI
from tools import TOOL_SCHEMAS, TOOL_MAP

load_dotenv()

MAX_ITERATIONS = 10

if os.getenv("USE_OLLAMA") == "1":
    client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
    MODEL  = os.getenv("MODEL", "qwen2.5:3b")
else:
    client = OpenAI(api_key=os.getenv("GROQ_API_KEY"),
                    base_url="https://api.groq.com/openai/v1")
    MODEL  = os.getenv("MODEL", "qwen/qwen3-32b")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

SYSTEM_PROMPT = """\
You are a rate-approval assistant for D&H Secheron.

When asked about an item's discounted rate, follow EXACTLY these steps — call each tool ONCE only:

STEP 1: Call get_discount_rule(item_no) — get the rule for this item.
STEP 2: Call get_dp_price(item_no) — get the dealer base price.
STEP 3: Calculate and answer based on rule_type:

  - rule_type = "discount" or rule_type = "sku_rate_table" with sku_entry.discount set:
      discounted_rate = dp_price × (1 - discount_percent / 100)
      Answer: "Item <X>: DP price = <dp>, discount = <d>%, discounted rate = <result>"

  - rule_type = "min_rate":
      Answer: "Item <X>: minimum approved rate is <min_rate>"

  - rule_type = "fail":
      Answer: "Item <X> is BLOCKED — it will always fail approval. DP price = <dp>"

  - rule_type = "skip":
      Answer: "Item <X> is AUTO-APPROVED — no rate check needed."

  - sku_entry not found / dp not found:
      Answer what was found and what was missing.

Do NOT call the same tool twice. Do NOT make up numbers.\
"""


def run_agent(question: str) -> str:
    log.info("[Q] %s", question)

    messages = [
        {"role": "system",  "content": SYSTEM_PROMPT},
        {"role": "user",    "content": question},
    ]

    for iteration in range(1, MAX_ITERATIONS + 1):
        log.info("[iter=%d] calling LLM...", iteration)

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )

        msg           = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # ── Model wants to call tools ──────────────────────────
        if finish_reason == "tool_calls":
            messages.append(msg)  # append assistant's tool_call request

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)
                log.info("[iter=%d] tool call → %s(%s)", iteration, fn_name, fn_args)

                fn      = TOOL_MAP.get(fn_name)
                result  = fn(**fn_args) if fn else {"error": f"Unknown tool: {fn_name}"}
                log.info("[iter=%d] tool result → %s", iteration, result)

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result),
                })

        # ── Model has a final text answer ──────────────────────
        else:
            answer = msg.content or ""
            log.info("[iter=%d] final answer: %s", iteration, answer[:200])
            return answer

    log.warning("MAX_ITERATIONS (%d) reached", MAX_ITERATIONS)
    return "MAX_ITERATIONS reached — no answer produced"


if __name__ == "__main__":
    test_questions = [
        "What is the discounted rate for item TRG0000590?",
        "What is the discounted rate for item TRG0000001?",
    ]

    for q in test_questions:
        print(f"\n{'=' * 60}")
        print(f"Q: {q}")
        answer = run_agent(q)
        print(f"A: {answer}")
        print("=" * 60)
