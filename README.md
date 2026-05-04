# Meta Ads AI Agent

An autonomous AI agent that pulls Meta Ads campaign data, analyzes performance, makes actionable decisions, and can execute changes directly in your ad account — powered by Google Gemini and LangChain.

---

## What It Does

**Read mode (weekly review):**
1. Pulls live campaign data from Meta Ads API (any date range)
2. Analyzes every campaign — SCALE / PAUSE / TEST / WATCH decisions
3. Generates a formatted performance report
4. Scores its own output across 7 quality checks

**Write mode (account changes):**
- Pause or activate campaigns
- Update daily budgets
- Duplicate campaigns or ad sets
- Change audience targeting (age, gender, countries)
- Create new campaigns
- Edit bid strategies
- Schedule campaign start/end dates
- Swap ad creatives (image + copy + URL)

> The agent always asks for confirmation before executing any write action.

---

## Project Structure

```
meta_agent/
  ├── .env.example       ← Copy → rename to .env → fill in keys
  ├── .gitignore
  ├── requirements.txt
  ├── tools.py           ← All 12 tools (3 read + 9 write)
  ├── agent.py           ← Agent brain (Gemini + tools + system prompt)
  ├── evals.py           ← 7-point quality control system
  └── run.py             ← Entry point
```

---

## Quick Start

### 1. Clone and open
```bash
git clone https://github.com/shuklaankit2011-dev/meta-ads-agent.git
cd meta-ads-agent
```

### 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up your keys
```bash
cp .env.example .env
# Open .env and fill in your actual values
```

| Key | Where to get it |
|---|---|
| `GOOGLE_API_KEY` | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `META_ACCESS_TOKEN` | Meta for Developers → My Apps → Marketing API → Generate Token (needs `ads_read` + `ads_management`) |
| `META_AD_ACCOUNT_ID` | Meta Ads Manager → top-left dropdown → copy the `act_XXXXXXX` ID |

### 5. Run it
```bash
python run.py
```

---

## How It Works

```
python run.py
      ↓
[Gemini 2.5 Flash — Agent Brain]
      ↓
[Tool 1] pull_meta_ads_data      → Hits Meta Ads API, returns live campaign metrics
      ↓
[Tool 2] analyze_campaign_performance → Applies decision rules → SCALE / PAUSE / TEST / WATCH
      ↓
[Tool 3] write_performance_report     → Formats the final report
      ↓
[evals.py] 7 quality checks score the output
      ↓
Report printed to terminal
```

---

## Metrics Pulled Per Campaign

| Metric | Source |
|---|---|
| Spend | Meta Insights API |
| Daily Budget | Meta Campaigns API |
| Results (leads) | `lead` action type only (no double-counting) |
| Cost per Result | Spend ÷ Results |
| ROAS | Purchase revenue ÷ Spend |
| CTR | Meta Insights API |
| CPM | Meta Insights API |
| CPC | Meta Insights API |
| Impressions | Meta Insights API |
| Reach | Meta Insights API |
| Frequency | Meta Insights API |

---

## Decision Rules

| Condition | Decision |
|---|---|
| ROAS ≥ 4.0x AND CTR ≥ 2.0% | SCALE AGGRESSIVELY |
| ROAS ≥ 3.0x AND CTR ≥ 1.5% | SCALE |
| ROAS < 1.0x AND Spend > ₹1000 | PAUSE IMMEDIATELY |
| ROAS < 1.0x AND Spend > ₹500 | PAUSE |
| 0 purchases AND Spend > ₹300 | PAUSE |
| ROAS ≥ 2.0x AND CTR < 0.8% | TEST NEW CREATIVE |
| ROAS ≥ 1.5x AND CTR < 1.0% | TEST NEW CREATIVE |
| Cost/Result > ₹500 AND Results < 5 | TEST |
| Frequency > 3.0x | TEST NEW CREATIVE (fatigue) |
| ROAS 1.0–2.0x AND CTR ≥ 1.0% | WATCH |
| No spend | INACTIVE |

Lead-gen campaigns are evaluated separately — e-commerce ROAS rules do not apply.

---

## Eval System (7 Checks)

| Check | What it verifies |
|---|---|
| Coverage | Every campaign got a decision |
| Logic | Decisions match the numbers (e.g. ROAS < 1x must be PAUSE) |
| Hallucination | No invented metrics — all numbers traceable to source data |
| Format | All required report sections are present |
| Metrics Accuracy | CPM, CPC, frequency values match source data |
| Frequency Check | High-frequency campaigns flagged for creative fatigue |
| Cost per Result | CPL calculation within 5% tolerance |

---

## Write Tools Reference

| Tool | What it does |
|---|---|
| `pause_or_activate_campaign` | Set campaign status to PAUSED or ACTIVE |
| `update_campaign_budget` | Change daily budget (pass INR, converts to paise automatically) |
| `duplicate_campaign` | Copy a campaign with a new name |
| `duplicate_adset` | Copy an ad set with a new name |
| `update_audience_targeting` | Change age range, gender, or target countries on an ad set |
| `create_campaign` | Create a new campaign from scratch |
| `update_bid_strategy` | Change bid strategy and bid cap across all ad sets in a campaign |
| `schedule_campaign` | Set start and end dates on an ad set |
| `swap_ad_creative` | Replace image, copy, and destination URL on an existing ad |

---

## Example Prompts

```
Run weekly review for last 15 days
Pause campaign 'Retargeting - Mumbai'
Increase budget on 'Lead Gen - Delhi' to ₹2000/day
Duplicate campaign 'Top Performer' as 'Top Performer - Test B'
Change targeting on adset 'Lookalike 1%' to ages 25-45, women only, India
Create a new PAUSED campaign called 'Brand Awareness - Q2' with ₹500/day budget
```

---

## Tech Stack

- **LLM:** Google Gemini 2.5 Flash via `langchain-google-genai`
- **Agent framework:** LangChain `create_tool_calling_agent` + `AgentExecutor`
- **Data source:** Meta Marketing API v18.0
- **Language:** Python 3.10+
