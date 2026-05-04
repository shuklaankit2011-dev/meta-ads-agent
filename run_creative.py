"""
run_creative.py — Creative Agent entry point

Finds your best performing ads, generates 5 new variations,
scores them, and flags the top 2 for launch.

Usage:
  python run_creative.py
"""

import sys
from dotenv import load_dotenv
load_dotenv()

from agents.creative import CreativeAgent


def main():
    print("\n" + "=" * 60)
    print("  META ADS — CREATIVE AGENT")
    print("=" * 60)

    agent = CreativeAgent()
    scored, top_2, best_ad = agent.run(days=30)

    if not scored:
        print("❌  No ad data or generation failed. Check credentials.")
        sys.exit(1)

    # ── Reference Ad ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  REFERENCE — BEST PERFORMING AD (Last 30 days)")
    print("=" * 60)
    print(f"  Name    : {best_ad.get('name')}")
    print(f"  CPL     : ₹{best_ad.get('cpl', 0):.0f}  |  CTR: {best_ad.get('ctr', 0):.2f}%  |  Leads: {best_ad.get('leads', 0)}")
    print(f"  Copy    : {(best_ad.get('primary_text') or 'N/A')[:120]}...")
    slides = best_ad.get("carousel_headlines", [])[:4]
    if slides:
        print(f"  Slides  : {' | '.join(slides)}")

    # ── All 5 Scored ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  ALL 5 VARIATIONS — RANKED BY SCORE")
    print("=" * 60)

    for i, var in enumerate(scored):
        s      = var.get("scores", {})
        flag   = "  🚀 LAUNCH" if var in top_2 else ""
        slides = " | ".join(var.get("carousel_headlines", [])[:3])

        print(f"\n{'━' * 60}")
        print(f"  #{i+1}  [{var.get('angle')}]   Score: {var.get('total_score', 0)}/50{flag}")
        print(f"{'━' * 60}")
        print(f"  Copy    : {var.get('primary_text', '')}")
        print(f"  Slides  : {slides}")
        print(f"  CTA     : {var.get('cta', '')}")
        print(f"  Scores  : Hook {s.get('hook',0)} | Clarity {s.get('clarity',0)} | Specific {s.get('specificity',0)} | CTA {s.get('cta_urgency',0)} | Audience {s.get('audience_fit',0)}")
        print(f"  Verdict : {s.get('verdict', '')}")
        print(f"  Why     : {var.get('reasoning', '')}")

    # ── Top 2 Summary ─────────────────────────────────────────────────────────
    print("\n\n" + "=" * 60)
    print("  🚀  TOP 2 FLAGGED FOR LAUNCH")
    print("=" * 60)

    for i, var in enumerate(top_2):
        slides = " | ".join(var.get("carousel_headlines", []))
        print(f"\n  #{i+1}  [{var.get('angle')}]   Score: {var.get('total_score')}/50")
        print(f"  Copy   : {var.get('primary_text', '')}")
        print(f"  Slides : {slides}")
        print(f"  CTA    : {var.get('cta', '')}")

    print("\n" + "=" * 60)
    print("  Next step: hand these to your creative team to build the visuals.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
