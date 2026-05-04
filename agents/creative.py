"""
creative.py — Creative Agent

1. Fetches best performing ads from Meta API (last N days)
2. Generates 5 new ad variations using Gemini LLM
3. Scores each variation on 5 dimensions using LLM-as-judge
4. Returns all 5 ranked + top 2 flagged for launch
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage

load_dotenv()

ACCESS_TOKEN  = os.getenv("META_ACCESS_TOKEN")
AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID")


GENERATE_PROMPT = """You are a senior Meta Ads copywriter for Indian markets — home interiors, real estate, and D2C lead gen.

You have studied the best-performing ad below. Generate 5 NEW variations that could outperform it.

BEST PERFORMING AD:
{best_ad_block}

RULES:
- Each variation uses a DIFFERENT creative angle (listed below)
- Primary text: max 4 lines. Headline: max 8 words.
- Write for Indian buyers: aspirational, family-oriented, value-conscious, mobile-first
- Do NOT copy the original. Use it only as inspiration.
- Keep the same CTA type: GET_QUOTE (lead gen form)

ANGLES (one per variation):
1. FOMO        — limited time offer, slots filling up, price going up soon
2. SOCIAL PROOF — "X families already transformed their home", testimonial feel
3. DIRECT BENEFIT — lead with the single strongest benefit (warranty / price / quality)
4. QUESTION HOOK  — open with a question the audience is already asking themselves
5. STORY / EMOTION — relatable scenario, aspiration, "imagine coming home to..."

Return ONLY a valid JSON array of exactly 5 objects:
[
  {{
    "angle": "FOMO",
    "primary_text": "...",
    "carousel_headlines": ["Slide 1 headline", "Slide 2 headline", "Slide 3 headline"],
    "cta": "Get Quote",
    "reasoning": "<one sentence: why this angle could beat the original>"
  }},
  ...
]"""


SCORE_PROMPT = """You are a Meta Ads creative director for Indian lead gen campaigns — home interiors and real estate.

Score this ad creative on 5 dimensions (0–10 each):

1. Hook Strength    — Does the opening line stop the scroll? Power words, bold claim, curiosity
2. Offer Clarity    — Is the value proposition crystal clear in one read?
3. Specificity      — Concrete numbers, prices, timeframes (e.g. "starting ₹10L" > "affordable")
4. CTA Urgency      — Is the call-to-action specific and action-driving?
5. Audience Fit     — Does it match Indian home buyer psychology? Aspiration + value + family

Return ONLY valid JSON:
{{
  "hook": <0-10>,
  "clarity": <0-10>,
  "specificity": <0-10>,
  "cta_urgency": <0-10>,
  "audience_fit": <0-10>,
  "total": <sum of all 5>,
  "verdict": "<one sentence: strongest point and weakest point>"
}}"""


class CreativeAgent:
    def __init__(self):
        self.generator = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.8,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        self.scorer = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    def fetch_best_ads(self, days: int = 30) -> list:
        print("  [Creative] Fetching ad-level performance...")

        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        until = datetime.now().strftime("%Y-%m-%d")

        resp = requests.get(
            f"https://graph.facebook.com/v18.0/{AD_ACCOUNT_ID}/insights",
            params={
                "fields": "ad_id,ad_name,spend,ctr,cpm,cpc,actions",
                "time_range": f'{{"since":"{since}","until":"{until}"}}',
                "level": "ad",
                "access_token": ACCESS_TOKEN,
                "limit": 50,
            },
            timeout=30,
        )
        ads_data = resp.json().get("data", [])

        ads = []
        for ad in ads_data:
            spend = float(ad.get("spend", 0))
            if spend == 0:
                continue
            leads = sum(int(a["value"]) for a in ad.get("actions", []) if a.get("action_type") == "lead")
            cpl   = spend / leads if leads > 0 else float("inf")
            ads.append({
                "id":    ad.get("ad_id"),
                "name":  ad.get("ad_name"),
                "spend": spend,
                "ctr":   float(ad.get("ctr", 0)),
                "cpm":   float(ad.get("cpm", 0)),
                "cpc":   float(ad.get("cpc", 0)),
                "leads": leads,
                "cpl":   cpl,
            })

        ads_with_leads = sorted([a for a in ads if a["leads"] > 0], key=lambda x: x["cpl"])

        if not ads_with_leads:
            print("  [Creative] No ads with leads found.")
            return []

        top = ads_with_leads[:3]
        print(f"  [Creative] Top {len(top)} ads by CPL found. Fetching creative copy...")

        for ad in top:
            try:
                r = requests.get(
                    f"https://graph.facebook.com/v18.0/{ad['id']}",
                    params={
                        "fields": "creative{object_story_spec}",
                        "access_token": ACCESS_TOKEN,
                    },
                    timeout=15,
                )
                spec      = r.json().get("creative", {}).get("object_story_spec", {})
                link_data = spec.get("link_data", {})

                ad["primary_text"] = link_data.get("message", "")
                ad["carousel_headlines"] = [
                    c.get("name", "") for c in link_data.get("child_attachments", [])
                ]
            except Exception:
                ad["primary_text"]       = ""
                ad["carousel_headlines"] = []

        return top

    def generate_variations(self, best_ads: list) -> list:
        print("  [Creative] Generating 5 new variations...")

        if not best_ads:
            return []

        best = best_ads[0]
        slides = "\n".join(f"  - {h}" for h in best.get("carousel_headlines", [])[:5])
        best_ad_block = (
            f"Ad Name     : {best['name']}\n"
            f"CPL         : ₹{best['cpl']:.0f} | CTR: {best['ctr']:.2f}% | CPM: ₹{best['cpm']:.0f} | Leads: {best['leads']}\n"
            f"Primary Text: {best.get('primary_text', 'N/A')}\n"
            f"Carousel Slides (first 5):\n{slides}"
        )

        response = self.generator.invoke([
            HumanMessage(content=GENERATE_PROMPT.format(best_ad_block=best_ad_block))
        ])

        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        try:
            variations = json.loads(content)
            print(f"  [Creative] {len(variations)} variations generated")
            return variations
        except json.JSONDecodeError:
            print("  [Creative] Warning: JSON parse failed")
            return []

    def score_variations(self, variations: list) -> list:
        print("  [Creative] Scoring all 5 variations...")

        scored = []
        for i, var in enumerate(variations):
            creative_text = (
                f"Primary Text: {var.get('primary_text', '')}\n"
                f"Carousel Headlines: {', '.join(var.get('carousel_headlines', []))}\n"
                f"CTA: {var.get('cta', '')}"
            )

            response = self.scorer.invoke([
                SystemMessage(content=SCORE_PROMPT),
                HumanMessage(content=creative_text),
            ])

            content = response.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            try:
                scores = json.loads(content)
            except json.JSONDecodeError:
                scores = {"total": 0, "verdict": "parse error"}

            var["scores"]      = scores
            var["total_score"] = scores.get("total", 0)
            scored.append(var)
            print(f"    #{i+1} [{var.get('angle')}]: {var['total_score']}/50")

        return sorted(scored, key=lambda x: x["total_score"], reverse=True)

    def run(self, days: int = 30) -> tuple:
        print("\n" + "━" * 54)
        print("  CREATIVE AGENT — Generating new ad variations")
        print("━" * 54 + "\n")

        best_ads = self.fetch_best_ads(days=days)
        if not best_ads:
            return [], [], {}

        variations = self.generate_variations(best_ads)
        if not variations:
            return [], [], best_ads[0]

        scored  = self.score_variations(variations)
        top_2   = scored[:2]

        print(f"\n  [Creative] Done — top 2 flagged for launch\n")
        return scored, top_2, best_ads[0]
