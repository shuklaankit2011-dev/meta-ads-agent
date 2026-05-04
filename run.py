"""
run.py — Entry point

Runs the 4-agent orchestrated pipeline:
  1. DataFetcherAgent  — pulls live Meta Ads data
  2. AnalystAgent      — applies decision rules
  3. DecisionAgent     — LLM adds strategic layer
  4. ReportingAgent    — formats the report
  5. Evals            — 7 quality checks score the output
"""

import sys
from orchestrator import Orchestrator
from evals import run_all_evals


def main():
    print("\n" + "=" * 54)
    print("  META ADS AGENT — DAILY REPORT")
    print("=" * 54 + "\n")

    orchestrator = Orchestrator()

    try:
        report, raw_data = orchestrator.run(days=7)
    except KeyboardInterrupt:
        print("\n⚠️  Run cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌  Pipeline failed: {str(e)}")
        print("\n    Things to check:")
        print("    • Is GOOGLE_API_KEY set correctly in .env?")
        print("    • Is META_ACCESS_TOKEN valid and not expired?")
        print("    • Is your internet connection working?")
        sys.exit(1)

    if not report:
        print("❌  Pipeline returned an empty report.")
        print("    Check your GOOGLE_API_KEY and try again.")
        sys.exit(1)

    if not raw_data:
        print("⚠️  No raw campaign data — skipping quality checks.\n")
        print(report)
        return

    # ── Evals ────────────────────────────────────────────────────────────────
    print("\n🔍  Running quality checks on the report...\n")
    eval_results = run_all_evals(raw_data, report)

    score   = eval_results["overall_score"]
    passed  = eval_results["passed"]

    print("\n" + "=" * 54)

    if passed:
        print("  ✅  FINAL REPORT  (All Quality Checks Passed)")
        print("=" * 54)
        print(report)

    elif score >= 0.7:
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
        print("  🚫  REPORT FAILED QUALITY CHECKS")
        print("=" * 54)
        print(f"  Score: {score * 10:.1f}/10 — Below acceptable threshold (7.0/10)")
        print("\n  Issues found:")
        for f in eval_results["all_failures"]:
            print(f"  • {f}")
        print("\n  ❌  Do NOT act on this report.")
        print("      Fix the issues above, then re-run: python run.py")

    print("\n" + "=" * 54 + "\n")


if __name__ == "__main__":
    main()
