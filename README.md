# 📊 Meta Ads Autonomous Agent

An AI agent that autonomously pulls Meta Ads campaign data, analyzes performance,
makes SCALE / PAUSE / TEST / WATCH decisions, and scores its own output quality.

---

## 📁 Project Structure

```
meta_agent/
  ├── .env.example       ← Copy this → rename to .env → fill in keys
  ├── .gitignore         ← Keeps your .env safe from GitHub
  ├── requirements.txt   ← All dependencies
  ├── tools.py           ← 3 tools the agent can use
  ├── agent.py           ← The agent brain (GPT-4o + tools wired together)
  ├── evals.py           ← 4 quality checks that run after every report
  ├── run.py             ← Entry point — run this to start everything
  └── eval_history.json  ← Auto-created, tracks scores over time
```

---

## ⚡ Quick Start

### 1. Clone / open in VS Code
```bash
cd meta_agent
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
# Open .env and fill in your actual keys
```

**Getting your keys:**
- `OPENAI_API_KEY` → https://platform.openai.com/api-keys
- `META_ACCESS_TOKEN` → https://developers.facebook.com → My Apps → Marketing API → Generate Token (needs `ads_read` permission)
- `META_AD_ACCOUNT_ID` → Meta Ads Manager → top left dropdown → copy the `act_XXXXXXX` ID

### 5. Run it
```bash
python run.py
```

> **No Meta credentials yet?** No problem. Leave them as-is in `.env` and the agent
> will automatically use realistic mock data so you can test the full pipeline.

---

## 🤖 How It Works

```
You run: python run.py
              ↓
    [Agent Brain — GPT-4o]
    "I need data first"
              ↓
    [Tool 1: pull_meta_ads_data]
    Hits Meta Ads API → returns campaign numbers
              ↓
    [Agent Brain — GPT-4o]
    "Now I'll analyze it"
              ↓
    [Tool 2: analyze_campaign_performance]
    Applies decision rules → SCALE / PAUSE / TEST / WATCH
              ↓
    [Agent Brain — GPT-4o]
    "Now write the report"
              ↓
    [Tool 3: write_performance_report]
    Formats the final report
              ↓
    [Eval System — evals.py]
    Scores the report on 4 checks
              ↓
    Report shown if score ≥ 7/10
```

---

## 📊 Eval System

After every run, 4 checks score the output automatically:

| Eval | What it checks |
|---|---|
| Coverage Check | Did every campaign get a decision? |
| Logic Check | Do decisions match the numbers? (e.g. ROAS < 1x must be PAUSE) |
| Hallucination Check | Did the agent make up any metrics? |
| Format Check | Are all required report sections present? |

Results are saved to `eval_history.json` so you can track improvement over time.

---

## 🔧 Decision Rules (in tools.py → analyze_campaign_performance)

| Condition | Decision |
|---|---|
| ROAS ≥ 4.0x AND CTR ≥ 2.0% | SCALE AGGRESSIVELY |
| ROAS ≥ 3.0x AND CTR ≥ 1.5% | SCALE |
| ROAS < 1.0x AND Spend > ₹1000 | PAUSE IMMEDIATELY |
| ROAS < 1.0x AND Spend > ₹500 | PAUSE |
| 0 purchases AND Spend > ₹300 | PAUSE |
| ROAS ≥ 2.0x AND CTR < 0.8% | TEST NEW CREATIVE |
| ROAS ≥ 1.5x AND CTR < 1.0% | TEST NEW CREATIVE |
| ROAS 1.0–2.0x AND CTR ≥ 1.0% | WATCH |
| ROAS 1.0–1.5x AND CTR < 1.0% | WATCH & OPTIMISE |
| No spend | INACTIVE |

Adjust these thresholds in `tools.py` to match your account benchmarks.

---

## 🚀 Next Steps (Coming Soon)

- **Gap 3 — Production:** Schedule to run every Monday 9AM automatically
- **Slack Integration:** Agent pings your team with the report
- **Alert System:** Notifies you if something breaks at 3AM
