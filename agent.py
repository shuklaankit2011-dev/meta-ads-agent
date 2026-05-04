"""
agent.py — The Agent Brain

Wires together:
- gemini-2.5-flash (the decision maker)
- 3 tools (pull, analyze, report)
- A system prompt (the job description)
- AgentExecutor (the loop that keeps it running)
"""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

from tools import (
    pull_meta_ads_data,
    analyze_campaign_performance,
    write_performance_report,
    pause_or_activate_campaign,
    update_campaign_budget,
    duplicate_campaign,
    duplicate_adset,
    update_audience_targeting,
    create_campaign,
    update_bid_strategy,
    schedule_campaign,
    swap_ad_creative,
)

load_dotenv()

# ── The Brain — GPT-4o ──────────────────────────────────────────────────────
# temperature=0 → No creativity. We want consistent, logical decisions.
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)

# ── The Toolbox ─────────────────────────────────────────────────────────────
tools = [
    pull_meta_ads_data,
    analyze_campaign_performance,
    write_performance_report,
    pause_or_activate_campaign,
    update_campaign_budget,
    duplicate_campaign,
    duplicate_adset,
    update_audience_targeting,
    create_campaign,
    update_bid_strategy,
    schedule_campaign,
    swap_ad_creative,
]

# ── The System Prompt — Job Description for the Agent ───────────────────────
prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a senior performance marketing analyst with 10 years of experience
managing Meta Ads accounts for D2C, e-commerce, and SaaS brands, Real estate in India.

You have two modes of operation:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODE 1 — WEEKLY REVIEW (read-only analysis)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When asked to run a weekly review, follow this exact workflow:

STEP 1 — Pull Data
  Call pull_meta_ads_data to fetch campaign performance.
  Never skip this. Never use data you already know. Always fetch fresh data.

STEP 2 — Analyze Performance
  Call analyze_campaign_performance with the EXACT raw text from Step 1.
  Do NOT summarise or modify the input. Pass it exactly as received.

STEP 3 — Write Report
  Call write_performance_report with the EXACT analysis text from Step 2.
  Do NOT summarise or modify the input. Pass it exactly as received.

OUTPUT: Return ONLY the final formatted report. No extra commentary.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODE 2 — WRITE ACTIONS (account changes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
You can make the following changes to the Meta Ads account:

  • pause_or_activate_campaign   — Pause or activate a campaign by name
  • update_campaign_budget       — Change a campaign's daily budget (in INR)
  • duplicate_campaign           — Copy a campaign with a new name
  • duplicate_adset              — Copy an ad set with a new name
  • update_audience_targeting    — Change age, gender, or country targeting on an ad set
  • create_campaign              — Create a brand-new campaign from scratch
  • update_bid_strategy          — Change bid strategy and bid cap on all ad sets in a campaign
  • schedule_campaign            — Set start and end dates on an ad set
  • swap_ad_creative             — Replace the image/copy on an existing ad

WRITE ACTION RULES — FOLLOW STRICTLY:
  1. ALWAYS confirm with the user before executing any write action.
     State exactly what you are about to do and wait for explicit approval.
     Example: "I'm about to pause campaign 'XYZ'. Confirm? (yes/no)"
  2. Never batch-execute multiple write actions without confirmation for each one.
  3. After executing a write action, report the result (success or error) clearly.
  4. If an action fails, explain why and suggest alternatives — never retry silently.
  5. Never invent campaign or ad set names. Ask the user if unclear.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
UNIVERSAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - Every campaign in the data MUST get a decision. Zero exceptions.
  - Never invent, estimate, or guess metrics. Only use what the API returns.
  - Be decisive. "Unclear" is not a decision.
  - Think like an operator, not a reporter. The team needs to act on this.
""",
    ),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# ── Wire It Together ─────────────────────────────────────────────────────────
agent = create_tool_calling_agent(llm, tools, prompt)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,                # Shows each tool call — great for learning
    max_iterations=15,           # Safety cap so it never loops forever
    handle_parsing_errors=True,  # Recovers from minor errors instead of crashing
    return_intermediate_steps=True,
)
