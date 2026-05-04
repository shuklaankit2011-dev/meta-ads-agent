"""
run.py — The Ignition Key

Run this file to start the entire agent pipeline:
  1. Agent pulls Meta Ads data
  2. Agent analyzes every campaign
  3. Agent writes the report
  4. Evals score the report automatically
  5. Report is shown only if it passes quality checks

Usage:
  python run.py
"""

import sys
import tools
from agent import agent_executor
from evals import run_all_evals


def main():
    print("\n" + "=" * 54)
    print("  META ADS AGENT — WEEKLY REVIEW")
    print("=" * 54 + "\n")

    # ── Step 1: Run the Agent ─────────────────────────────────────────────────
    print("🤖  Agent starting...\n")

    try:
        result = agent_executor.invoke({
            "input": (
                "Run the complete weekly Meta Ads performance review "
                "for the last 7 days. "
                "Pull the campaign data, analyze every single campaign, "
                "and write the full formatted report."
            )
        })
    except KeyboardInterrupt:
        print("\n⚠️  Run cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌  Agent failed to run.")
        print(f"    Error: {str(e)}")
        print("\n    Things to check:")
        print("    • Is OPENAI_API_KEY set correctly in .env?")
        print("    • Do you have credits in your OpenAI account?")
        print("    • Is your internet connection working?")
        sys.exit(1)

    report = result.get("output", "").strip()

    if not report:
        print("❌  Agent returned an empty response.")
        print("    Check your OpenAI API key and try again.")
        sys.exit(1)

    # ── Step 2: Get the raw campaign data the agent pulled ────────────────────
    # Stored as a global in tools.py when Tool 1 (pull_meta_ads_data) ran
    campaign_data = tools.last_campaign_data

    if not campaign_data:
        print("⚠️  Warning: Could not retrieve raw campaign data for quality checks.")
        print("   This usually means the Meta credentials aren't set up yet.")
        print("   Showing the report without eval scoring:\n")
        print(report)
        return

    # ── Step 3: Run Evals ─────────────────────────────────────────────────────
    print("\n🔍  Running quality checks on the report...\n")
    eval_results = run_all_evals(campaign_data, report)

    # ── Step 4: Show Report Based on Eval Verdict ─────────────────────────────
    score   = eval_results["overall_score"]
    passed  = eval_results["passed"]
    verdict = eval_results["verdict"]

    print("\n" + "=" * 54)

    if passed:
        # All 4 evals passed — safe to use
        print("  ✅  FINAL REPORT  (All Quality Checks Passed)")
        print("=" * 54)
        print(report)

    elif score >= 0.7:
        # Mostly good but has some issues — show with warning
        print("  ⚠️   FINAL REPORT  (Review Before Acting)")
        print("=" * 54)
        print(report)
        print("\n" + "-" * 54)
        print("  Issues found during quality check:")
        for f in eval_results["all_failures"]:
            print(f"  • {f}")
        print("-" * 54)
        print("  Double-check the above before taking action.")

    else:
        # Scored below 7/10 — do not act on this report
        print("  🚫  REPORT FAILED QUALITY CHECKS")
        print("=" * 54)
        print(f"  Score: {score * 10:.1f}/10 — Below acceptable threshold (7.0/10)")
        print(f"  Verdict: {verdict}")
        print("\n  Issues found:")
        for f in eval_results["all_failures"]:
            print(f"  • {f}")
        print("\n  ❌  Do NOT act on this report.")
        print("      Fix the issues above, then re-run: python run.py")

    print("\n" + "=" * 54 + "\n")


if __name__ == "__main__":
    main()
