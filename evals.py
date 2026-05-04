"""
evals.py — Quality Control System for the Meta Ads Agent

7 automated checks run after every agent output:

  Eval 1 — Coverage Check        Did every campaign get a decision?
  Eval 2 — Logic Check           Do decisions match the actual numbers?
  Eval 3 — Hallucination Check   Did the agent make up any metrics?
  Eval 4 — Format Check          Is the report properly structured?
  Eval 5 — Metrics Accuracy      Are CPM, CPC, frequency correctly reported?
  Eval 6 — Frequency Check       High-frequency campaigns flagged for creative fatigue?
  Eval 7 — Cost/Result Accuracy  Is CPL / cost-per-purchase mathematically correct?

All results are saved to eval_history.json so you can track
whether the agent is improving over time.
"""

import re
import json
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 1 — Coverage Check
# Every campaign that went IN must come OUT with a decision
# ─────────────────────────────────────────────────────────────────────────────

def eval_coverage(campaign_data: str, report: str) -> dict:
    """
    Checks if every campaign in the input data
    appears by name in the final report.
    Score: 1.0 = all campaigns covered, 0.5 = half covered, etc.
    """
    campaigns_in = []
    for line in campaign_data.split("\n"):
        if line.strip().startswith("Campaign:"):
            name = line.replace("Campaign:", "").strip()
            campaigns_in.append(name)

    if not campaigns_in:
        return {
            "eval_name": "Coverage Check",
            "score":     1.0,
            "passed":    True,
            "details":   "No campaigns found in source data",
            "failures":  [],
        }

    missing  = [c for c in campaigns_in if c not in report]
    covered  = len(campaigns_in) - len(missing)
    total    = len(campaigns_in)
    score    = covered / total

    return {
        "eval_name": "Coverage Check",
        "score":     round(score, 2),
        "passed":    score == 1.0,
        "details":   f"{covered}/{total} campaigns have decisions in the report",
        "failures":  [f"Missing from report: '{c}'" for c in missing],
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 2 — Logic Check
# Do the agent's decisions match the numbers?
# ─────────────────────────────────────────────────────────────────────────────

def eval_logic(campaign_data: str, report: str) -> dict:
    """
    For campaigns with clear-cut metrics, checks that the agent
    made the correct call (e.g., ROAS < 1.0 + high spend = must be PAUSE).
    Catches wrong decisions or hallucinated recommendations.
    """
    failures      = []
    checks_run    = 0
    checks_passed = 0

    blocks = campaign_data.strip().split("\n\n")

    for block in blocks:
        name      = ""
        roas      = 0.0
        spend     = 0.0
        purchases = 0
        leads     = 0

        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("Campaign:"):
                name = line.replace("Campaign:", "").strip()
            if "ROAS:" in line:
                try:
                    roas = float(line.split("ROAS:")[1].split("x")[0].strip())
                except (IndexError, ValueError):
                    pass
            if "Spend:" in line:
                try:
                    spend = float(line.split("Spend: ₹")[1].split("|")[0].strip())
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

        if not name or name not in report:
            continue  # Coverage check already caught this

        is_lead_gen = leads > 0 or (purchases == 0 and roas == 0 and spend > 0)

        # Grab what the agent said about this campaign (300 chars after name)
        idx = report.find(name)
        window = report[idx: idx + 300] if idx != -1 else ""

        checks_run += 1

        # Rule 1: ROAS < 1.0 AND spend > 500 → MUST be PAUSE (e-commerce only)
        if not is_lead_gen and roas < 1.0 and spend > 500:
            if "PAUSE" in window:
                checks_passed += 1
            else:
                failures.append(
                    f"'{name}': ROAS={roas:.2f}x, Spend=₹{spend:.0f} "
                    f"→ Should be PAUSE. Agent said something else."
                )

        # Rule 2: ROAS >= 3.0 → MUST be SCALE
        elif roas >= 3.0:
            if "SCALE" in window:
                checks_passed += 1
            else:
                failures.append(
                    f"'{name}': ROAS={roas:.2f}x "
                    f"→ Should be SCALE. Agent said something else."
                )

        # Rule 3: Zero purchases AND spend > 300 → MUST be PAUSE (e-commerce only)
        elif not is_lead_gen and purchases == 0 and spend > 300:
            if "PAUSE" in window:
                checks_passed += 1
            else:
                failures.append(
                    f"'{name}': 0 purchases, Spend=₹{spend:.0f} "
                    f"→ Should be PAUSE. Agent said something else."
                )

        else:
            # Middle-ground cases — harder to auto-verify, give benefit of doubt
            checks_passed += 1

    if checks_run == 0:
        return {
            "eval_name": "Logic Check",
            "score":     1.0,
            "passed":    True,
            "details":   "No clear-cut cases to verify",
            "failures":  [],
        }

    score = checks_passed / checks_run

    return {
        "eval_name": "Logic Check",
        "score":     round(score, 2),
        "passed":    len(failures) == 0,
        "details":   f"{checks_passed}/{checks_run} decisions are logically correct",
        "failures":  failures,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 3 — Hallucination Check
# Did the agent make up any numbers not in the original data?
# ─────────────────────────────────────────────────────────────────────────────

def eval_hallucination(campaign_data: str, report: str) -> dict:
    """
    Extracts all metric-range decimal numbers from source data,
    then checks if the report contains numbers that don't exist in the source.
    Flags potential hallucinations.
    """
    # All decimal numbers in source data
    real_numbers = set(re.findall(r"\d+\.\d+", campaign_data))

    # All decimal numbers in the report
    report_numbers = re.findall(r"\d+\.\d+", report)

    # Flag numbers in metric range (ROAS, CTR, CPM-like) not in source
    suspicious = []
    for num in report_numbers:
        try:
            val = float(num)
        except ValueError:
            continue
        # Only care about numbers that could be a metric (not timestamps etc.)
        if 0.1 < val < 50 and num not in real_numbers:
            suspicious.append(num)

    suspicious = list(set(suspicious))  # Deduplicate

    # Allow small tolerance — flag only if more than 2 unknown numbers
    hallucination_risk = len(suspicious) > 2

    return {
        "eval_name": "Hallucination Check",
        "score":     0.0 if hallucination_risk else 1.0,
        "passed":    not hallucination_risk,
        "details":   (
            f"Found {len(suspicious)} metric-range numbers in report "
            f"not present in source data"
        ),
        "failures":  (
            [f"Suspicious number not in source data: {n}" for n in suspicious]
            if hallucination_risk
            else []
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 4 — Format Check
# Is the report properly structured with all required sections?
# ─────────────────────────────────────────────────────────────────────────────

def eval_format(report: str) -> dict:
    """
    Checks that the report contains all required sections.
    A broken format breaks downstream use (e.g. Slack parsing, email).
    """
    required = {
        "Report header":       "META ADS WEEKLY PERFORMANCE REPORT",
        "Period line":         "Period",
        "Summary snapshot":    "SUMMARY SNAPSHOT",
        "Campaign decisions":  "CAMPAIGN-BY-CAMPAIGN DECISIONS",
        "Action list":         "PRIORITISED ACTION LIST",
        "Disclaimer":          "Auto-generated",
    }

    missing = [
        label
        for label, keyword in required.items()
        if keyword not in report
    ]

    total = len(required)
    score = (total - len(missing)) / total

    return {
        "eval_name": "Format Check",
        "score":     round(score, 2),
        "passed":    len(missing) == 0,
        "details":   f"{total - len(missing)}/{total} required sections present",
        "failures":  [f"Missing section: '{s}'" for s in missing],
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 5 — Metrics Accuracy Check
# CPM, CPC, impressions, reach in report must match source data
# ─────────────────────────────────────────────────────────────────────────────

def eval_metrics_accuracy(campaign_data: str, report: str) -> dict:
    """
    For each campaign, verifies that CPM, CPC, and Impressions reported
    match what was in the raw source data.
    """
    failures   = []
    checks_run = 0
    checks_ok  = 0

    for block in campaign_data.strip().split("\n\n"):
        name        = ""
        src_cpm     = 0.0
        src_cpc     = 0.0
        src_impr    = 0
        src_reach   = 0
        src_freq    = 0.0

        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("Campaign:"):
                name = line.replace("Campaign:", "").strip()
            if "CPM: ₹" in line:
                try:
                    src_cpm = float(line.split("CPM: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass
            if "CPC: ₹" in line:
                try:
                    src_cpc = float(line.split("CPC: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass
            if "Impressions:" in line:
                try:
                    src_impr = int(line.split("Impressions:")[1].split("|")[0].replace(",", "").strip())
                except (IndexError, ValueError):
                    pass
            if "Reach:" in line:
                try:
                    src_reach = int(line.split("Reach:")[1].split("|")[0].replace(",", "").strip())
                except (IndexError, ValueError):
                    pass
            if "Frequency:" in line:
                try:
                    src_freq = float(line.split("Frequency:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

        if not name or name not in report:
            continue

        idx    = report.find(name)
        window = report[idx: idx + 600] if idx != -1 else ""

        # Check CPM
        if src_cpm > 0:
            checks_run += 1
            if f"₹{src_cpm:.0f}" in window or f"₹{int(src_cpm)}" in window:
                checks_ok += 1
            else:
                failures.append(f"'{name}': CPM ₹{src_cpm:.0f} not found in report")

        # Check CPC
        if src_cpc > 0:
            checks_run += 1
            if f"₹{src_cpc:.0f}" in window or f"₹{int(src_cpc)}" in window:
                checks_ok += 1
            else:
                failures.append(f"'{name}': CPC ₹{src_cpc:.0f} not found in report")

        # Check Frequency
        if src_freq > 0:
            checks_run += 1
            freq_str = f"{src_freq:.2f}"
            if freq_str in window or f"{src_freq:.1f}" in window:
                checks_ok += 1
            else:
                failures.append(f"'{name}': Frequency {src_freq:.2f}x not found in report")

    if checks_run == 0:
        return {
            "eval_name": "Metrics Accuracy",
            "score":     1.0,
            "passed":    True,
            "details":   "No metrics to verify",
            "failures":  [],
        }

    score = checks_ok / checks_run
    return {
        "eval_name": "Metrics Accuracy",
        "score":     round(score, 2),
        "passed":    len(failures) == 0,
        "details":   f"{checks_ok}/{checks_run} metric values correctly reported",
        "failures":  failures,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 6 — Frequency Check
# Campaigns with frequency > 3.0 MUST mention creative fatigue or TEST
# ─────────────────────────────────────────────────────────────────────────────

def eval_frequency_check(campaign_data: str, report: str) -> dict:
    """
    High-frequency campaigns (>3.0) must get a creative fatigue warning
    or a TEST NEW CREATIVE recommendation in the report.
    """
    failures   = []
    checks_run = 0
    checks_ok  = 0

    for block in campaign_data.strip().split("\n\n"):
        name      = ""
        frequency = 0.0

        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("Campaign:"):
                name = line.replace("Campaign:", "").strip()
            if "Frequency:" in line:
                try:
                    frequency = float(line.split("Frequency:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

        if not name or name not in report or frequency < 3.0:
            continue

        checks_run += 1
        idx    = report.find(name)
        window = report[idx: idx + 400] if idx != -1 else ""

        fatigue_keywords = ["TEST", "creative fatigue", "frequency", "FREQ", "creative refresh"]
        if any(kw.lower() in window.lower() for kw in fatigue_keywords):
            checks_ok += 1
        else:
            failures.append(
                f"'{name}': Frequency {frequency:.2f}x (>3.0) — "
                f"report must flag creative fatigue or recommend TEST NEW CREATIVE"
            )

    if checks_run == 0:
        return {
            "eval_name": "Frequency Check",
            "score":     1.0,
            "passed":    True,
            "details":   "No high-frequency campaigns (>3.0x) found",
            "failures":  [],
        }

    score = checks_ok / checks_run
    return {
        "eval_name": "Frequency Check",
        "score":     round(score, 2),
        "passed":    len(failures) == 0,
        "details":   f"{checks_ok}/{checks_run} high-frequency campaigns flagged correctly",
        "failures":  failures,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EVAL 7 — Cost per Result Accuracy
# Verify CPL / cost-per-purchase in report is mathematically correct
# ─────────────────────────────────────────────────────────────────────────────

def eval_cost_per_result(campaign_data: str, report: str) -> dict:
    """
    Recalculates cost per result from spend and conversions in source data,
    then checks the report's cost-per-result figure is within 5% tolerance.
    """
    failures   = []
    checks_run = 0
    checks_ok  = 0

    for block in campaign_data.strip().split("\n\n"):
        name      = ""
        spend     = 0.0
        leads     = 0
        purchases = 0

        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("Campaign:"):
                name = line.replace("Campaign:", "").strip()
            if "Spend:" in line:
                try:
                    spend = float(line.split("Spend: ₹")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass
            if "Results:" in line:
                try:
                    leads = int(line.split("Results:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass
            if "Purchases:" in line:
                try:
                    purchases = int(line.split("Purchases:")[1].split("|")[0].strip())
                except (IndexError, ValueError):
                    pass

        total_conv = leads if leads > 0 else purchases
        if not name or name not in report or total_conv == 0 or spend == 0:
            continue

        expected_cpr = spend / total_conv
        checks_run  += 1

        idx    = report.find(name)
        window = report[idx: idx + 600] if idx != -1 else ""

        # Look for any number within 5% of expected CPR
        numbers = re.findall(r'₹(\d+)', window)
        tolerance = expected_cpr * 0.05
        found = any(abs(float(n) - expected_cpr) <= max(tolerance, 5) for n in numbers)

        if found:
            checks_ok += 1
        else:
            failures.append(
                f"'{name}': Expected cost/result ₹{expected_cpr:.0f} "
                f"(spend ₹{spend:.0f} / {total_conv} conversions) not found in report"
            )

    if checks_run == 0:
        return {
            "eval_name": "Cost/Result Accuracy",
            "score":     1.0,
            "passed":    True,
            "details":   "No campaigns with conversions to verify",
            "failures":  [],
        }

    score = checks_ok / checks_run
    return {
        "eval_name": "Cost/Result Accuracy",
        "score":     round(score, 2),
        "passed":    len(failures) == 0,
        "details":   f"{checks_ok}/{checks_run} cost-per-result figures verified correct",
        "failures":  failures,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MASTER EVAL RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_all_evals(campaign_data: str, report: str) -> dict:
    """
    Runs all 4 evals and returns a final verdict + score.
    Call this after every agent run.

    Returns:
        dict with keys: overall_score, verdict, passed,
                        individual_results, all_failures
    """
    results = [
        eval_coverage(campaign_data, report),
        eval_logic(campaign_data, report),
        eval_hallucination(campaign_data, report),
        eval_format(report),
        eval_metrics_accuracy(campaign_data, report),
        eval_frequency_check(campaign_data, report),
        eval_cost_per_result(campaign_data, report),
    ]

    overall_score = sum(r["score"] for r in results) / len(results)
    all_passed    = all(r["passed"] for r in results)
    all_failures  = [f for r in results for f in r["failures"]]

    if overall_score >= 0.9:
        verdict = "✅ PASS — Report is high quality. Safe to send."
    elif overall_score >= 0.7:
        verdict = "⚠️  REVIEW — Mostly good. Check failures before acting."
    else:
        verdict = "🚫 FAIL — Do not use this report. Re-run the agent."

    # ── Print Results ────────────────────────────────────────────────────────
    print("\n" + "=" * 54)
    print("  EVAL RESULTS")
    print("=" * 54)

    for r in results:
        icon = "✅" if r["passed"] else "❌"
        score_display = f"{r['score'] * 10:.1f}/10"
        print(f"  {icon}  {r['eval_name']:<24} {score_display}")
        print(f"      {r['details']}")
        for f in r["failures"]:
            print(f"      ⚠  {f}")
        print()

    print(f"  OVERALL SCORE  :  {overall_score * 10:.1f}/10")
    print(f"  VERDICT        :  {verdict}")
    print("=" * 54 + "\n")

    # ── Save to history ───────────────────────────────────────────────────────
    _save_eval_history(overall_score, verdict, all_failures)

    return {
        "overall_score":      round(overall_score, 2),
        "verdict":            verdict,
        "passed":             all_passed,
        "individual_results": results,
        "all_failures":       all_failures,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HISTORY LOGGER
# Saves every run so you can track whether the agent is improving
# ─────────────────────────────────────────────────────────────────────────────

def _save_eval_history(score: float, verdict: str, failures: list):
    """
    Appends this run's eval results to eval_history.json.
    Over time this builds a trend showing whether your agent is improving.
    """
    entry = {
        "timestamp":        datetime.now().isoformat(),
        "score":            round(score, 2),
        "score_out_of_10":  round(score * 10, 1),
        "verdict":          verdict,
        "failure_count":    len(failures),
        "failures":         failures,
    }

    history_file = "eval_history.json"

    try:
        with open(history_file, "r") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        history = []

    history.append(entry)

    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)

    run_number = len(history)
    print(f"  📈  Run #{run_number} saved to eval_history.json")

    # Show trend after 3+ runs
    if run_number >= 3:
        recent = [h["score"] * 10 for h in history[-5:]]
        trend  = "📈 Improving" if recent[-1] > recent[0] else "📉 Declining"
        avg    = sum(recent) / len(recent)
        print(f"  {trend}  |  Last {len(recent)} runs avg: {avg:.1f}/10")

    print()
