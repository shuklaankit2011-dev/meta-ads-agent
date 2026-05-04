"""
tools.py — All tools the Meta Ads Agent can use

READ TOOLS
  Tool 1: pull_meta_ads_data              → Fetches campaign performance from Meta API
  Tool 2: analyze_campaign_performance    → Applies decision rules, flags campaigns
  Tool 3: write_performance_report        → Formats the final shareable report

WRITE TOOLS
  Tool 4: pause_or_activate_campaign      → Pause or activate a campaign
  Tool 5: update_campaign_budget          → Change daily budget of a campaign
  Tool 6: duplicate_campaign              → Duplicate a campaign
  Tool 7: duplicate_adset                 → Duplicate an adset to a campaign
  Tool 8: update_audience_targeting       → Update age, gender, geo targeting on an adset
  Tool 9: create_campaign                 → Create a new campaign from scratch
  Tool 10: update_bid_strategy            → Change bid strategy on campaign adsets
  Tool 11: schedule_campaign              → Set start/end dates on a campaign
  Tool 12: swap_ad_creative               → Upload new image and swap creative on an ad
"""

import base64
import json
import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain.tools import tool

load_dotenv()

ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")

# Global variable — stores raw campaign data so evals.py can access it
last_campaign_data = ""


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — Pull Meta Ads Data
# ─────────────────────────────────────────────────────────────────────────────

@tool
def pull_meta_ads_data(days: int = 7) -> str:
    """
    Pulls Meta Ads campaign performance data for the last N days.
    Returns spend, impressions, clicks, conversions, ROAS for each campaign.
    Always call this first before any analysis.
    """
    global last_campaign_data

    # ── Use mock data if no real credentials are set ──
    if not ACCESS_TOKEN or ACCESS_TOKEN == "your_meta_token_here":
        mock_data = _get_mock_data()
        last_campaign_data = mock_data
        return mock_data

    # ── Fetch insights (spend, reach, frequency, etc.) ──────────────────────
    insights_url = f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/insights"

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    until = datetime.now().strftime("%Y-%m-%d")

    params = {
        "fields": "campaign_name,campaign_id,spend,impressions,reach,frequency,clicks,actions,action_values,cpm,cpc,ctr",
        "time_range": f'{{"since":"{since}","until":"{until}"}}',
        "level": "campaign",
        "access_token": ACCESS_TOKEN,
        "limit": 100,
    }

    try:
        response = requests.get(insights_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.ConnectionError:
        return "ERROR: Could not connect to Meta API. Check your internet connection."
    except requests.exceptions.Timeout:
        return "ERROR: Meta API request timed out. Try again."
    except requests.exceptions.RequestException as e:
        return f"ERROR: Failed to fetch Meta Ads data. Reason: {str(e)}"

    if "error" in data:
        err = data["error"]
        return (
            f"META API ERROR {err.get('code', '?')}: "
            f"{err.get('message', 'Unknown error')}. "
            f"Type: {err.get('type', 'Unknown')}"
        )

    campaigns = data.get("data", [])

    if not campaigns:
        return "No campaigns with spend found in the last 7 days."

    # ── Fetch budgets (daily/lifetime) — campaign-level field, not in insights ──
    budget_map = {}
    try:
        budget_resp = requests.get(
            f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/campaigns",
            params={
                "fields": "id,daily_budget,lifetime_budget",
                "access_token": ACCESS_TOKEN,
                "limit": 100,
            },
            timeout=15,
        )
        for c in budget_resp.json().get("data", []):
            daily    = int(c.get("daily_budget", 0)) // 100      # Meta returns in cents
            lifetime = int(c.get("lifetime_budget", 0)) // 100
            budget_map[c["id"]] = daily if daily > 0 else lifetime
    except Exception:
        pass  # Budget is non-critical — continue without it

    result = []

    for ins in campaigns:
        name        = ins.get("campaign_name", "Unknown Campaign")
        campaign_id = ins.get("campaign_id", "")
        spend       = float(ins.get("spend", 0))
        impressions = int(ins.get("impressions", 0))
        reach       = int(ins.get("reach", 0))
        frequency   = float(ins.get("frequency", 0))
        clicks      = int(ins.get("clicks", 0))
        budget      = budget_map.get(campaign_id, 0)

        actions       = ins.get("actions", [])
        action_values = ins.get("action_values", [])

        # Purchases (e-commerce)
        purchases        = sum(int(a["value"]) for a in actions if a.get("action_type") == "purchase")
        purchase_revenue = sum(float(av["value"]) for av in action_values if av.get("action_type") == "purchase")

        # Results — use only "lead" action type; "onsite_conversion.lead_grouped" is the same leads re-reported, summing both double-counts
        leads = sum(int(a["value"]) for a in actions if a.get("action_type") == "lead")

        revenue = purchase_revenue
        roas    = (revenue / spend) if spend > 0 and revenue > 0 else 0

        ctr = float(ins.get("ctr", 0))
        cpm = float(ins.get("cpm", 0))
        cpc = float(ins.get("cpc", 0))

        total_conversions = purchases if purchases > 0 else leads
        cost_per_result   = (spend / total_conversions) if total_conversions > 0 else 0

        if purchases > 0:
            conv_label = f"Purchases: {purchases}"
        elif leads > 0:
            conv_label = f"Results: {leads}"
        else:
            conv_label = "Conversions: 0"

        budget_str = f"₹{budget:,}" if budget > 0 else "N/A"

        result.append(
            f"Campaign: {name}\n"
            f"  Spend: ₹{spend:.0f} | Budget: {budget_str} | Revenue: ₹{revenue:.0f}\n"
            f"  ROAS: {roas:.2f}x | CTR: {ctr:.2f}% | CPM: ₹{cpm:.0f}\n"
            f"  CPC: ₹{cpc:.0f} | Cost per Result: ₹{cost_per_result:.0f} | {conv_label}\n"
            f"  Impressions: {impressions:,} | Reach: {reach:,} | Frequency: {frequency:.2f}"
        )

    output = "\n\n".join(result)
    last_campaign_data = output  # Save for evals

    return output


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — Analyze Campaign Performance
# ─────────────────────────────────────────────────────────────────────────────

@tool
def analyze_campaign_performance(campaign_data: str) -> str:
    """
    Analyzes campaign data and flags each campaign as:
    SCALE, PAUSE, TEST NEW CREATIVE, or WATCH — with clear reasoning.
    Pass the EXACT output from pull_meta_ads_data as input.
    """
    blocks   = campaign_data.strip().split("\n\n")
    analysis = []

    for block in blocks:
        name             = "Unknown"
        roas             = 0.0
        ctr              = 0.0
        spend            = 0.0
        cpc              = 0.0
        cpm              = 0.0
        purchases        = 0
        leads            = 0
        frequency        = 0.0
        reach            = 0
        cost_per_result  = 0.0

        for line in block.split("\n"):
            line = line.strip()

            if line.startswith("Campaign:"):
                name = line.replace("Campaign:", "").strip()
                continue

            if "ROAS:" in line:
                try:
                    roas = float(line.split("ROAS:")[1].split("x")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "CTR:" in line:
                try:
                    ctr = float(line.split("CTR:")[1].split("%")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "CPM: ₹" in line:
                try:
                    cpm = float(line.split("CPM: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "Spend:" in line:
                try:
                    spend = float(line.split("Spend: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "CPC: ₹" in line:
                try:
                    cpc = float(line.split("CPC: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "Cost per Result: ₹" in line:
                try:
                    cost_per_result = float(line.split("Cost per Result: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "Purchases:" in line:
                try:
                    purchases = int(line.split("Purchases:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "Results:" in line:
                try:
                    leads = int(line.split("Results:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "Frequency:" in line:
                try:
                    frequency = float(line.split("Frequency:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

            if "Reach:" in line:
                try:
                    reach = int(line.split("Reach:")[1].split("|")[0].replace(",", "").strip())
                except (IndexError, ValueError):
                    pass

        is_lead_gen = leads > 0 or (purchases == 0 and roas == 0 and spend > 0)
        cpl = (spend / leads) if leads > 0 else 0

        # ── Decision Engine — your marketing brain encoded as rules ──

        if spend == 0:
            decision = (
                "⏸️  INACTIVE — Zero spend this period. "
                "Check if campaign was paused intentionally or has budget issues."
            )
            priority = "LOW"

        # ── Lead Gen decision rules ──────────────────────────────────────────
        elif is_lead_gen:
            if leads == 0 and spend > 300:
                decision = (
                    "🚫 PAUSE — Zero results despite meaningful spend."
                    "Likely a form issue or audience-offer mismatch. "
                    "Check: Meta lead form, audience targeting, and ad creative."
                )
                priority = "URGENT"
            elif cpl > 0 and cpl <= 300 and leads >= 10:
                decision = (
                    f"✅ SCALE — Strong results performance."
                    f"CPL ₹{cpl:.0f} with {leads} results."
                    f"Increase daily budget 20–30%. Monitor lead quality before scaling further."
                )
                priority = "HIGH"
            elif cpl > 0 and cpl <= 500 and leads >= 5:
                decision = (
                    f"⚠️  WATCH — Decent results ({leads}) at CPL ₹{cpl:.0f}."
                    f"Test new creatives to bring CPL below ₹300. "
                    f"Review lead quality before scaling."
                )
                priority = "MEDIUM"
            elif cpl > 500 and spend > 1000:
                decision = (
                    f"🚫 PAUSE — CPL ₹{cpl:.0f} is too high for sustainable lead gen. "
                    f"Refresh creative and tighten audience before restarting."
                )
                priority = "URGENT"
            elif ctr < 1.0 and spend > 500:
                decision = (
                    "🧪 TEST NEW CREATIVE — Low CTR is limiting reach. "
                    "Try new hooks, visuals, and lead form headline. Keep audience as-is."
                )
                priority = "MEDIUM"
            else:
                decision = (
                    f"⚠️  WATCH — Campaign with {leads} results at CPL ₹{cpl:.0f}."
                    f"Monitor for 3 more days before scaling or pausing."
                )
                priority = "MEDIUM"

        # ── E-commerce / ROAS decision rules ────────────────────────────────
        elif roas >= 4.0 and ctr >= 2.0:
            decision = (
                "✅ SCALE AGGRESSIVELY — Exceptional ROAS and CTR. "
                "Increase budget 30–50%. Duplicate adset to fresh audiences. "
                "Lock this creative while scaling."
            )
            priority = "HIGH"

        elif roas >= 3.0 and ctr >= 1.5:
            decision = (
                "✅ SCALE — Strong performance across metrics. "
                f"Increase daily budget 20–30%. Monitor frequency — "
                "if it crosses 3, duplicate to new audience."
            )
            priority = "HIGH"

        elif roas < 1.0 and spend > 1000:
            loss = spend - (spend * roas)
            decision = (
                f"🚫 PAUSE IMMEDIATELY — Burning budget with negative returns. "
                f"Estimated loss this week: ₹{loss:.0f}. Stop this campaign now. "
                f"Review creative, audience, and landing page before restarting."
            )
            priority = "URGENT"

        elif roas < 1.0 and spend > 500:
            decision = (
                "🚫 PAUSE — Spending above ₹500 with ROAS below break-even. "
                "Do not let this run further without a full creative refresh. "
                "Check: Is the landing page converting? Is the audience relevant?"
            )
            priority = "HIGH"

        elif purchases == 0 and spend > 300:
            decision = (
                "🚫 PAUSE — Zero purchases despite meaningful spend. "
                "Likely a tracking issue or major audience-offer mismatch. "
                "Check: Meta pixel firing, checkout flow, and audience targeting."
            )
            priority = "URGENT"

        elif roas >= 2.0 and ctr < 0.8:
            decision = (
                "🧪 TEST NEW CREATIVE — ROAS is healthy but low CTR signals "
                "creative fatigue. The audience is right, the ad isn't clicking. "
                "Refresh visuals and hooks. Keep targeting as-is."
            )
            priority = "MEDIUM"

        elif roas >= 1.5 and ctr < 1.0:
            decision = (
                "🧪 TEST NEW CREATIVE — Decent ROAS but CTR is underperforming. "
                "Try 2–3 new ad variations. Test different hooks and thumbnails. "
                "Don't change audience until creative is refreshed."
            )
            priority = "MEDIUM"

        elif 1.0 <= roas < 2.0 and ctr >= 1.0:
            decision = (
                "⚠️  WATCH — Break-even territory with acceptable CTR. "
                "Test one variable at a time (audience OR creative, not both). "
                "Do not scale. Give it 3 more days before deciding."
            )
            priority = "MEDIUM"

        elif 1.0 <= roas < 1.5 and ctr < 1.0:
            decision = (
                "⚠️  WATCH & OPTIMISE — Both ROAS and CTR are underperforming. "
                "Narrow the audience, tighten the creative angle. "
                "Set a 3-day review checkpoint."
            )
            priority = "MEDIUM"

        else:
            decision = (
                "🔍 REVIEW MANUALLY — Unusual pattern or insufficient data. "
                "Log into Meta Ads Manager and check at adset level."
            )
            priority = "LOW"

        freq_flag = f" ⚠️ HIGH FREQ {frequency:.1f}x" if frequency >= 3.0 else ""

        analysis.append(
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 {name}\n"
            f"   Decision : {decision}\n"
            f"   Priority : {priority}\n"
            f"   Metrics  : Spend ₹{spend:.0f} | CPM ₹{cpm:.0f} | CPC ₹{cpc:.0f} | CTR {ctr:.2f}%\n"
            f"   Audience : Reach {reach:,} | Frequency {frequency:.2f}x{freq_flag}\n"
            f"   Result   : Cost/Result ₹{cost_per_result:.0f} | "
            + (f"Results {leads} | CPL ₹{cpl:.0f}" if is_lead_gen else f"ROAS {roas:.2f}x | Purchases {purchases}")
        )

    return "\n\n".join(analysis)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — Write Performance Report
# ─────────────────────────────────────────────────────────────────────────────

@tool
def write_performance_report(analysis: str) -> str:
    """
    Takes the full campaign analysis and writes a clean, shareable weekly report.
    Includes a summary snapshot, all decisions, and a prioritised action list.
    Pass the EXACT output from analyze_campaign_performance as input.
    """
    today      = datetime.now().strftime("%d %b %Y")
    week_start = (datetime.now() - timedelta(days=7)).strftime("%d %b")
    week_end   = datetime.now().strftime("%d %b %Y")

    # Count decision types for summary
    urgent_count = analysis.count("URGENT")
    scale_count  = analysis.count("✅ SCALE")
    pause_count  = analysis.count("🚫 PAUSE")
    test_count   = analysis.count("🧪 TEST")
    watch_count  = analysis.count("⚠️")

    report = f"""
╔══════════════════════════════════════════════════════╗
   📊  META ADS WEEKLY PERFORMANCE REPORT
   Period   : {week_start} → {week_end}
   Generated: {today}
   By       : Autonomous Marketing Agent
╚══════════════════════════════════════════════════════╝

SUMMARY SNAPSHOT
──────────────────────────────────────────────────────
  🚨 Urgent Actions  : {urgent_count}
  ✅ Scale           : {scale_count}
  🚫 Pause           : {pause_count}
  🧪 Test Creative   : {test_count}
  ⚠️  Watch / Optimise: {watch_count}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAMPAIGN-BY-CAMPAIGN DECISIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{analysis}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIORITISED ACTION LIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. 🚨 URGENT FIRST   — Pause all loss-making campaigns immediately
  2. ✅ SCALE WINNERS  — Increase budgets on Scale campaigns today
  3. 🧪 BRIEF CREATIVE — Share Test campaigns with creative team for new assets
  4. ⚠️  SET REMINDER   — Review Watch campaigns in exactly 72 hours
  5. 🔍 CHECK TRACKING — Verify pixel and checkout for zero-purchase campaigns

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  Auto-generated by AI agent. Always verify in Meta Ads Manager before acting.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return report.strip()


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS — ID lookups (not exposed as agent tools)
# ─────────────────────────────────────────────────────────────────────────────

def _get_campaign_id(name: str) -> str:
    r = requests.get(
        f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/campaigns",
        params={"fields": "id,name", "access_token": ACCESS_TOKEN, "limit": 200},
        timeout=15,
    )
    for c in r.json().get("data", []):
        if c["name"].strip().lower() == name.strip().lower():
            return c["id"]
    raise ValueError(f"Campaign '{name}' not found. Check the exact name and try again.")


def _get_adset_id(name: str) -> str:
    r = requests.get(
        f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/adsets",
        params={"fields": "id,name", "access_token": ACCESS_TOKEN, "limit": 200},
        timeout=15,
    )
    for a in r.json().get("data", []):
        if a["name"].strip().lower() == name.strip().lower():
            return a["id"]
    raise ValueError(f"Adset '{name}' not found. Check the exact name and try again.")


def _get_ad_id(name: str) -> str:
    r = requests.get(
        f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/ads",
        params={"fields": "id,name,creative", "access_token": ACCESS_TOKEN, "limit": 200},
        timeout=15,
    )
    for a in r.json().get("data", []):
        if a["name"].strip().lower() == name.strip().lower():
            return a["id"], a.get("creative", {}).get("id", "")
    raise ValueError(f"Ad '{name}' not found. Check the exact name and try again.")


def _api_error(resp: dict) -> str:
    err = resp.get("error", {})
    return f"❌ Meta API Error {err.get('code','?')}: {err.get('message','Unknown error')}"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — Pause or Activate Campaign
# ─────────────────────────────────────────────────────────────────────────────

@tool
def pause_or_activate_campaign(campaign_name: str, action: str) -> str:
    """
    Pause or activate a campaign by name.
    action: 'PAUSE' to pause the campaign, 'ACTIVATE' to make it active.
    Always confirm with the user before calling this tool.
    """
    status = "PAUSED" if action.strip().upper() in ("PAUSE", "PAUSED") else "ACTIVE"
    try:
        campaign_id = _get_campaign_id(campaign_name)
    except ValueError as e:
        return str(e)

    r = requests.post(
        f"https://graph.facebook.com/v18.0/{campaign_id}",
        data={"status": status, "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    result = r.json()
    if result.get("success"):
        icon = "⏸️" if status == "PAUSED" else "▶️"
        return f"{icon} Campaign '{campaign_name}' is now {status}."
    return _api_error(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — Update Campaign Budget
# ─────────────────────────────────────────────────────────────────────────────

@tool
def update_campaign_budget(campaign_name: str, new_daily_budget: int) -> str:
    """
    Change the daily budget of a campaign.
    new_daily_budget is in INR (e.g. 1000 = ₹1,000/day).
    Always confirm the new budget with the user before calling this tool.
    """
    try:
        campaign_id = _get_campaign_id(campaign_name)
    except ValueError as e:
        return str(e)

    # Meta API requires budget in paise (cents) — multiply by 100
    r = requests.post(
        f"https://graph.facebook.com/v18.0/{campaign_id}",
        data={"daily_budget": new_daily_budget * 100, "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    result = r.json()
    if result.get("success"):
        return f"✅ Budget updated. '{campaign_name}' daily budget is now ₹{new_daily_budget:,}/day."
    return _api_error(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — Duplicate Campaign
# ─────────────────────────────────────────────────────────────────────────────

@tool
def duplicate_campaign(campaign_name: str, new_name: str = "") -> str:
    """
    Duplicate an existing campaign. The copy is created as PAUSED by default.
    Optionally provide new_name for the duplicate. If empty, Meta auto-names it.
    """
    try:
        campaign_id = _get_campaign_id(campaign_name)
    except ValueError as e:
        return str(e)

    payload = {"access_token": ACCESS_TOKEN, "deep_copy": "true", "status_option": "PAUSED"}
    if new_name:
        payload["name"] = new_name

    r = requests.post(
        f"https://graph.facebook.com/v18.0/{campaign_id}/copies",
        data=payload,
        timeout=30,
    )
    result = r.json()
    copied_ids = result.get("copied_campaign_id") or result.get("id")
    if copied_ids:
        label = new_name if new_name else f"Copy of {campaign_name}"
        return f"✅ Campaign duplicated successfully. New campaign: '{label}' (ID: {copied_ids}) — status: PAUSED."
    return _api_error(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 7 — Duplicate Adset
# ─────────────────────────────────────────────────────────────────────────────

@tool
def duplicate_adset(adset_name: str, new_name: str = "") -> str:
    """
    Duplicate an existing adset. The copy is created as PAUSED by default.
    Optionally provide new_name for the duplicate.
    """
    try:
        adset_id = _get_adset_id(adset_name)
    except ValueError as e:
        return str(e)

    payload = {"access_token": ACCESS_TOKEN, "deep_copy": "true", "status_option": "PAUSED"}
    if new_name:
        payload["name"] = new_name

    r = requests.post(
        f"https://graph.facebook.com/v18.0/{adset_id}/copies",
        data=payload,
        timeout=30,
    )
    result = r.json()
    copied_id = result.get("copied_adset_id") or result.get("id")
    if copied_id:
        label = new_name if new_name else f"Copy of {adset_name}"
        return f"✅ Adset duplicated. New adset: '{label}' (ID: {copied_id}) — status: PAUSED."
    return _api_error(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 8 — Update Audience Targeting
# ─────────────────────────────────────────────────────────────────────────────

@tool
def update_audience_targeting(
    adset_name: str,
    age_min: int = 18,
    age_max: int = 65,
    genders: str = "all",
    countries: str = "IN",
) -> str:
    """
    Update audience targeting on an adset.
    genders: 'all', 'male', or 'female'.
    countries: comma-separated country codes e.g. 'IN' or 'IN,AE'.
    age_min / age_max: integer age range.
    Always confirm targeting changes with the user before calling.
    """
    try:
        adset_id = _get_adset_id(adset_name)
    except ValueError as e:
        return str(e)

    gender_map = {"male": [1], "female": [2], "all": []}
    gender_list = gender_map.get(genders.lower(), [])
    country_list = [c.strip().upper() for c in countries.split(",")]

    targeting = {
        "age_min": age_min,
        "age_max": age_max,
        "geo_locations": {"countries": country_list},
    }
    if gender_list:
        targeting["genders"] = gender_list

    r = requests.post(
        f"https://graph.facebook.com/v18.0/{adset_id}",
        data={"targeting": json.dumps(targeting), "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    result = r.json()
    if result.get("success"):
        gender_label = genders if genders != "all" else "all genders"
        return (
            f"✅ Targeting updated for adset '{adset_name}':\n"
            f"   Age: {age_min}–{age_max} | Gender: {gender_label} | Countries: {', '.join(country_list)}"
        )
    return _api_error(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 9 — Create New Campaign
# ─────────────────────────────────────────────────────────────────────────────

@tool
def create_campaign(
    name: str,
    objective: str,
    daily_budget: int,
    status: str = "PAUSED",
) -> str:
    """
    Create a new campaign from scratch.
    objective options: LEAD_GENERATION, CONVERSIONS, LINK_CLICKS, BRAND_AWARENESS,
                       REACH, VIDEO_VIEWS, MESSAGES, OUTCOME_LEADS, OUTCOME_TRAFFIC.
    daily_budget in INR. status: 'PAUSED' (default, safe) or 'ACTIVE'.
    Always confirm name, objective, and budget with user before calling.
    """
    r = requests.post(
        f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/campaigns",
        data={
            "name": name,
            "objective": objective.upper(),
            "daily_budget": daily_budget * 100,
            "status": status.upper(),
            "special_ad_categories": "[]",
            "access_token": ACCESS_TOKEN,
        },
        timeout=15,
    )
    result = r.json()
    campaign_id = result.get("id")
    if campaign_id:
        return (
            f"✅ Campaign created successfully!\n"
            f"   Name      : {name}\n"
            f"   Objective : {objective.upper()}\n"
            f"   Budget    : ₹{daily_budget:,}/day\n"
            f"   Status    : {status.upper()}\n"
            f"   ID        : {campaign_id}"
        )
    return _api_error(result)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 10 — Update Bid Strategy
# ─────────────────────────────────────────────────────────────────────────────

@tool
def update_bid_strategy(
    campaign_name: str,
    bid_strategy: str,
    bid_amount: int = 0,
) -> str:
    """
    Update bid strategy on all adsets within a campaign.
    bid_strategy options:
      LOWEST_COST_WITHOUT_CAP  — let Meta spend freely (default)
      LOWEST_COST_WITH_BID_CAP — set a max bid (requires bid_amount in INR)
      COST_CAP                 — target average cost per result (requires bid_amount in INR)
    bid_amount in INR, only needed for LOWEST_COST_WITH_BID_CAP and COST_CAP.
    """
    try:
        campaign_id = _get_campaign_id(campaign_name)
    except ValueError as e:
        return str(e)

    # Fetch all adsets under this campaign
    r = requests.get(
        f"https://graph.facebook.com/v18.0/{campaign_id}/adsets",
        params={"fields": "id,name", "access_token": ACCESS_TOKEN, "limit": 100},
        timeout=15,
    )
    adsets = r.json().get("data", [])
    if not adsets:
        return f"No adsets found under campaign '{campaign_name}'."

    results = []
    for adset in adsets:
        payload = {
            "bid_strategy": bid_strategy.upper(),
            "access_token": ACCESS_TOKEN,
        }
        if bid_amount > 0 and bid_strategy.upper() in ("LOWEST_COST_WITH_BID_CAP", "COST_CAP"):
            payload["bid_amount"] = bid_amount * 100  # in paise

        resp = requests.post(
            f"https://graph.facebook.com/v18.0/{adset['id']}",
            data=payload,
            timeout=15,
        )
        result = resp.json()
        if result.get("success"):
            results.append(f"  ✅ {adset['name']}")
        else:
            results.append(f"  ❌ {adset['name']}: {result.get('error',{}).get('message','failed')}")

    bid_label = f"₹{bid_amount}/result" if bid_amount > 0 else "auto"
    return (
        f"Bid strategy update — '{bid_strategy}' ({bid_label}):\n"
        + "\n".join(results)
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 11 — Schedule Campaign
# ─────────────────────────────────────────────────────────────────────────────

@tool
def schedule_campaign(
    campaign_name: str,
    start_date: str,
    end_date: str = "",
) -> str:
    """
    Set start and optional end date for a campaign.
    start_date and end_date must be in YYYY-MM-DD format (e.g. '2026-05-10').
    If end_date is empty, the campaign runs indefinitely from start_date.
    Scheduling is applied at the adset level (Meta requires it there).
    """
    try:
        campaign_id = _get_campaign_id(campaign_name)
    except ValueError as e:
        return str(e)

    # Fetch all adsets under this campaign
    r = requests.get(
        f"https://graph.facebook.com/v18.0/{campaign_id}/adsets",
        params={"fields": "id,name", "access_token": ACCESS_TOKEN, "limit": 100},
        timeout=15,
    )
    adsets = r.json().get("data", [])
    if not adsets:
        return f"No adsets found under campaign '{campaign_name}'."

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        start_unix = int(start_dt.timestamp())
    except ValueError:
        return "❌ Invalid start_date format. Use YYYY-MM-DD (e.g. 2026-05-10)."

    end_unix = None
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_unix = int(end_dt.timestamp())
        except ValueError:
            return "❌ Invalid end_date format. Use YYYY-MM-DD."

    results = []
    for adset in adsets:
        payload = {"start_time": start_unix, "access_token": ACCESS_TOKEN}
        if end_unix:
            payload["end_time"] = end_unix

        resp = requests.post(
            f"https://graph.facebook.com/v18.0/{adset['id']}",
            data=payload,
            timeout=15,
        )
        result = resp.json()
        if result.get("success"):
            results.append(f"  ✅ {adset['name']}")
        else:
            results.append(f"  ❌ {adset['name']}: {result.get('error',{}).get('message','failed')}")

    end_label = end_date if end_date else "no end date"
    return (
        f"Schedule set for '{campaign_name}' — Start: {start_date} | End: {end_label}\n"
        + "\n".join(results)
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 12 — Swap Ad Creative
# ─────────────────────────────────────────────────────────────────────────────

@tool
def swap_ad_creative(
    ad_name: str,
    new_image_url: str,
    new_message: str = "",
    new_link_url: str = "",
) -> str:
    """
    Upload a new image and swap the creative on an existing ad.
    new_image_url: public URL of the image to upload (JPEG/PNG, min 600x600).
    new_message: new ad copy/body text (optional, keeps existing if empty).
    new_link_url: destination URL (optional, keeps existing if empty).
    Always confirm with the user before swapping a live ad creative.
    """
    # Step 1: Get ad ID and current creative ID
    try:
        r = requests.get(
            f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/ads",
            params={"fields": "id,name,creative{id,object_story_spec}", "access_token": ACCESS_TOKEN, "limit": 200},
            timeout=15,
        )
        ad_data = None
        for a in r.json().get("data", []):
            if a["name"].strip().lower() == ad_name.strip().lower():
                ad_data = a
                break
        if not ad_data:
            return f"❌ Ad '{ad_name}' not found. Check the exact ad name."
    except Exception as e:
        return f"❌ Failed to fetch ad: {str(e)}"

    ad_id       = ad_data["id"]
    old_creative = ad_data.get("creative", {})
    old_story   = old_creative.get("object_story_spec", {})

    # Step 2: Download and upload image to Meta
    try:
        img_resp = requests.get(new_image_url, timeout=20)
        img_resp.raise_for_status()
        img_bytes   = img_resp.content
        img_b64     = base64.b64encode(img_bytes).decode("utf-8")
        img_filename = new_image_url.split("/")[-1].split("?")[0] or "creative.jpg"
    except Exception as e:
        return f"❌ Failed to download image from URL: {str(e)}"

    upload_resp = requests.post(
        f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/adimages",
        data={"access_token": ACCESS_TOKEN, "filename": img_filename, "bytes": img_b64},
        timeout=30,
    )
    upload_result = upload_resp.json()
    images = upload_result.get("images", {})
    if not images:
        return _api_error(upload_result)

    image_hash = list(images.values())[0].get("hash", "")
    if not image_hash:
        return "❌ Image uploaded but hash not returned. Cannot create creative."

    # Step 3: Build new creative spec
    link_data = old_story.get("link_data", {})
    new_link_data = {
        "image_hash": image_hash,
        "link": new_link_url or link_data.get("link", ""),
        "message": new_message or link_data.get("message", ""),
    }

    page_id = old_story.get("page_id", "")
    if not page_id:
        return "❌ Could not retrieve page_id from existing creative. Cannot create new creative."

    creative_resp = requests.post(
        f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/adcreatives",
        data={
            "object_story_spec": json.dumps({"page_id": page_id, "link_data": new_link_data}),
            "access_token": ACCESS_TOKEN,
        },
        timeout=15,
    )
    creative_result = creative_resp.json()
    new_creative_id = creative_result.get("id")
    if not new_creative_id:
        return _api_error(creative_result)

    # Step 4: Update ad with new creative
    update_resp = requests.post(
        f"https://graph.facebook.com/v18.0/{ad_id}",
        data={"creative": json.dumps({"creative_id": new_creative_id}), "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    update_result = update_resp.json()
    if update_result.get("success"):
        return (
            f"✅ Creative swapped on ad '{ad_name}'.\n"
            f"   New image uploaded (hash: {image_hash})\n"
            f"   New creative ID: {new_creative_id}"
        )
    return _api_error(update_result)


# ─────────────────────────────────────────────────────────────────────────────
# MOCK DATA — Used when Meta credentials are not set up yet
# ─────────────────────────────────────────────────────────────────────────────

def _get_mock_data() -> str:
    """
    Returns realistic mock campaign data for testing.
    Covers all decision types: SCALE, PAUSE, TEST, WATCH.
    """
    print("⚠️  No Meta credentials found. Running with MOCK DATA for testing.")
    return """Campaign: Diwali Sale - Retargeting
  Spend: ₹4200 | Budget: ₹1,000 | Revenue: ₹18900
  ROAS: 4.50x | CTR: 2.10% | CPM: ₹84
  CPC: ₹40 | Cost per Result: ₹93 | Purchases: 45
  Impressions: 50,000 | Reach: 18,000 | Frequency: 2.78

Campaign: New User Acquisition - Broad
  Spend: ₹8500 | Budget: ₹2,000 | Revenue: ₹5100
  ROAS: 0.60x | CTR: 0.55% | CPM: ₹120
  CPC: ₹218 | Cost per Result: ₹708 | Purchases: 12
  Impressions: 70,833 | Reach: 14,500 | Frequency: 4.89

Campaign: Lookalike - Top Buyers 1%
  Spend: ₹3200 | Budget: ₹800 | Revenue: ₹8960
  ROAS: 2.80x | CTR: 0.65% | CPM: ₹96
  CPC: ₹80 | Cost per Result: ₹114 | Purchases: 28
  Impressions: 33,333 | Reach: 22,000 | Frequency: 1.52

Campaign: Brand Awareness - Video Views
  Spend: ₹1500 | Budget: ₹500 | Revenue: ₹1800
  ROAS: 1.20x | CTR: 1.10% | CPM: ₹50
  CPC: ₹45 | Cost per Result: ₹250 | Purchases: 6
  Impressions: 30,000 | Reach: 27,500 | Frequency: 1.09

Campaign: Abandoned Cart - Dynamic
  Spend: ₹650 | Budget: ₹300 | Revenue: ₹0
  ROAS: 0.00x | CTR: 0.30% | CPM: ₹130
  CPC: ₹433 | Cost per Result: ₹0 | Purchases: 0
  Impressions: 5,000 | Reach: 1,200 | Frequency: 4.17"""
