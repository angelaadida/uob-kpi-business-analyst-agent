"""
UOB Business Analyst Agent - Step 3
Portfolio Project - Level 6, Mastering Claude curriculum

Reads the quarterly KPI CSV, sends it to Claude API with the System Prompt
defined in system_prompt.py, and saves the structured JSON analysis to a
report file for review.

API key is read automatically from the ANTHROPIC_API_KEY environment
variable - never hardcode it here.
"""

import json
import os
from datetime import datetime

import anthropic
import pandas as pd

from system_prompt import SYSTEM_PROMPT

# --- Configuration ---
DATA_PATH = os.path.join("data", "uob_kpi_q1_2026.csv")
REPORT_OUTPUT_PATH = os.path.join("data", "analysis_report.json")
EMAIL_OUTPUT_PATH = os.path.join("data", "email_draft.txt")
MODEL = "claude-sonnet-5"
MAX_TOKENS = 8000  # must cover both the model's internal thinking budget AND the final text output


def load_kpi_data(csv_path: str) -> pd.DataFrame:
    """Read the KPI CSV into a DataFrame and do a basic sanity check."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Cannot find {csv_path}. Make sure uob_kpi_q1_2026.csv is inside the data/ folder."
        )
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} KPI rows from {csv_path}")
    return df


def build_user_message(df: pd.DataFrame) -> str:
    """Convert the DataFrame back to CSV text to send as the user message.
    Sending raw CSV (not a summary) lets Claude see every column, including
    source_url and calculation_formula, exactly as described in the System Prompt.
    """
    return df.to_csv(index=False)


def call_claude_api(csv_text: str) -> str:
    """Call Claude API once with the System Prompt and the CSV data.
    No streaming - this is a background/automated call, not an interactive chat
    (same principle learned in Level 5 Bai 5).

    Claude Sonnet 5 may think before answering, so response.content can contain
    multiple blocks (e.g. a ThinkingBlock followed by a TextBlock). We must loop
    through all blocks and only collect the ones with type == "text" - taking
    content[0] directly is not safe.
    """
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": csv_text}
        ],
    )

    text_parts = [block.text for block in response.content if block.type == "text"]
    if not text_parts:
        block_types = [block.type for block in response.content]
        raise ValueError(
            f"Claude API returned no text block. stop_reason={response.stop_reason}, "
            f"block types received={block_types}. Try increasing MAX_TOKENS."
        )
    return "".join(text_parts)


def parse_json_response(raw_text: str) -> dict:
    """Parse Claude's response as JSON. Strips markdown code fences if Claude
    accidentally wraps the JSON in ```json ... ``` despite the System Prompt
    instruction not to.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def save_report(result: dict, output_path: str) -> None:
    """Save the analysis result with a timestamp, for audit trail purposes."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "model_used": MODEL,
        "analysis": result,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Report saved to {output_path}")


def build_email_draft(result: dict) -> dict:
    """Format the analysis JSON into an email subject + body, using plain
    Python string formatting only - no additional API call needed, since
    every piece of text here has already been verified against the source CSV.
    """
    trend_tag = result.get("overall_trend_tag", "")
    subject = f"UOB Q1 2026 KPI Analysis - {trend_tag}"

    highlights_text = "\n".join(
        f"  - {h['metric']}: {h['insight']}" for h in result.get("key_highlights", [])
    )
    risks_text = "\n".join(
        f"  - [{r['severity'].upper()}] {r['metric']}: {r['concern']}"
        for r in result.get("risk_flags", [])
    )
    gaps_text = "\n".join(f"  - {g}" for g in result.get("data_gaps_noted", []))

    body = f"""Subject: {subject}

SUMMARY
{result.get('summary', '')}

KEY HIGHLIGHTS
{highlights_text}

RISK FLAGS (require review)
{risks_text}

RECOMMENDATION
{result.get('recommendation', {}).get('action', '')}
Requires human approval before external use: {result.get('recommendation', {}).get('requires_human_approval')}

DATA GAPS NOTED
{gaps_text}

---
{result.get('ai_disclaimer', '')}
Data as of: {result.get('data_as_of', '')}
"""
    return {"subject": subject, "body": body}


def save_email_draft(email: dict, output_path: str) -> None:
    """Save the formatted email to a text file. This file is what gets pasted
    into Claude Chat (where Gmail MCP is connected) to actually create the draft.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"SUBJECT: {email['subject']}\n\n")
        f.write(email["body"])
    print(f"Email draft text saved to {output_path}")


def main():
    df = load_kpi_data(DATA_PATH)
    csv_text = build_user_message(df)

    print("Calling Claude API...")
    raw_response = call_claude_api(csv_text)

    try:
        result = parse_json_response(raw_response)
    except json.JSONDecodeError as e:
        print("ERROR: Claude did not return valid JSON.")
        print("Raw response was:")
        print(raw_response)
        raise e

    save_report(result, REPORT_OUTPUT_PATH)

    email = build_email_draft(result)
    save_email_draft(email, EMAIL_OUTPUT_PATH)

    # Quick human-readable preview in the terminal
    print("\n--- QUICK PREVIEW ---")
    print("Overall trend:", result.get("overall_trend_tag"))
    print("Summary:", result.get("summary"))
    print("Number of key highlights:", len(result.get("key_highlights", [])))
    print("Number of risk flags:", len(result.get("risk_flags", [])))


if __name__ == "__main__":
    main()
