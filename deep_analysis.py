"""
deep_analysis.py — Period-over-period deep dive
Pulls campaign → adset → ad level data for current vs previous period
and highlights what changed for Wedezine_Leadgen 18 june iphone & android
"""

import os, requests, json
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TOKEN    = os.getenv("META_ACCESS_TOKEN")
ACCOUNT  = os.getenv("META_AD_ACCOUNT_ID")
BASE     = "https://graph.facebook.com/v18.0"

TODAY      = datetime.now()
CUR_END    = TODAY.strftime("%Y-%m-%d")
CUR_START  = (TODAY - timedelta(days=7)).strftime("%Y-%m-%d")
PREV_END   = (TODAY - timedelta(days=8)).strftime("%Y-%m-%d")
PREV_START = (TODAY - timedelta(days=30)).strftime("%Y-%m-%d")


def get(url, params):
    params["access_token"] = TOKEN
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_insights(level, since, until, extra_fields=""):
    fields = f"campaign_name,campaign_id,adset_name,adset_id,ad_name,ad_id,spend,impressions,reach,frequency,clicks,ctr,cpm,cpc,actions,action_values{extra_fields}"
    data = get(f"{BASE}/{ACCOUNT}/insights", {
        "fields": fields,
        "time_range": json.dumps({"since": since, "until": until}),
        "level": level,
        "limit": 100,
    })
    return data.get("data", [])


def leads(row):
    return sum(int(a["value"]) for a in row.get("actions", []) if a.get("action_type") == "lead")


def cpl(row):
    l = leads(row)
    s = float(row.get("spend", 0))
    return s / l if l > 0 else float("inf")


def pct(new, old):
    if old == 0 or old == float("inf"):
        return "N/A"
    change = ((new - old) / old) * 100
    arrow = "▲" if change > 0 else "▼"
    return f"{arrow}{abs(change):.1f}%"


def fmt_cpl(v):
    return f"₹{v:.0f}" if v != float("inf") else "∞"


def section(title):
    print(f"\n{'═'*62}")
    print(f"  {title}")
    print(f"{'═'*62}")


def divider():
    print(f"{'─'*62}")


# ── CAMPAIGN LEVEL ────────────────────────────────────────────────
section("1. CAMPAIGN LEVEL — Current (last 7d) vs Previous (8–30d)")

cur_camps  = fetch_insights("campaign", CUR_START,  CUR_END)
prev_camps = fetch_insights("campaign", PREV_START, PREV_END)

prev_map = {r["campaign_name"]: r for r in prev_camps}

for c in cur_camps:
    name = c.get("campaign_name", "")
    p    = prev_map.get(name, {})

    c_spend = float(c.get("spend", 0))
    c_ctr   = float(c.get("ctr", 0))
    c_cpm   = float(c.get("cpm", 0))
    c_cpc   = float(c.get("cpc", 0))
    c_freq  = float(c.get("frequency", 0))
    c_reach = int(c.get("reach", 0))
    c_leads = leads(c)
    c_cpl   = cpl(c)

    p_spend = float(p.get("spend", 0))
    p_ctr   = float(p.get("ctr", 0))
    p_cpm   = float(p.get("cpm", 0))
    p_cpc   = float(p.get("cpc", 0))
    p_freq  = float(p.get("frequency", 0))
    p_reach = int(p.get("reach", 0))
    p_leads = leads(p)
    p_cpl   = cpl(p)

    print(f"\n  Campaign : {name}")
    divider()
    print(f"  {'Metric':<18} {'Current (7d)':>14} {'Previous (22d)':>16} {'Change':>10}")
    divider()
    print(f"  {'Spend':<18} {'₹'+str(int(c_spend)):>14} {'₹'+str(int(p_spend)):>16} {pct(c_spend, p_spend):>10}")
    print(f"  {'CPM':<18} {'₹'+f'{c_cpm:.0f}':>14} {'₹'+f'{p_cpm:.0f}':>16} {pct(c_cpm, p_cpm):>10}")
    print(f"  {'CPC':<18} {'₹'+f'{c_cpc:.0f}':>14} {'₹'+f'{p_cpc:.0f}':>16} {pct(c_cpc, p_cpc):>10}")
    print(f"  {'CTR':<18} {f'{c_ctr:.2f}%':>14} {f'{p_ctr:.2f}%':>16} {pct(c_ctr, p_ctr):>10}")
    print(f"  {'Reach':<18} {str(c_reach):>14} {str(p_reach):>16} {pct(c_reach, p_reach):>10}")
    print(f"  {'Frequency':<18} {f'{c_freq:.2f}x':>14} {f'{p_freq:.2f}x':>16} {pct(c_freq, p_freq):>10}")
    print(f"  {'Leads':<18} {str(c_leads):>14} {str(p_leads):>16} {pct(c_leads, p_leads):>10}")
    print(f"  {'CPL':<18} {fmt_cpl(c_cpl):>14} {fmt_cpl(p_cpl):>16} {pct(c_cpl, p_cpl):>10}")


# ── ADSET LEVEL ───────────────────────────────────────────────────
section("2. AD SET LEVEL — Current 7d")

cur_adsets  = fetch_insights("adset", CUR_START,  CUR_END)
prev_adsets = fetch_insights("adset", PREV_START, PREV_END)
prev_adset_map = {r["adset_name"]: r for r in prev_adsets}

# group by campaign
from collections import defaultdict
camp_adsets = defaultdict(list)
for a in cur_adsets:
    camp_adsets[a.get("campaign_name", "")].append(a)

for camp_name, adsets in camp_adsets.items():
    print(f"\n  [{camp_name}]")
    divider()
    for a in sorted(adsets, key=lambda x: float(x.get("spend", 0)), reverse=True):
        p = prev_adset_map.get(a["adset_name"], {})
        a_leads = leads(a)
        a_cpl   = cpl(a)
        p_leads = leads(p)
        p_cpl   = cpl(p)
        print(f"  AdSet : {a.get('adset_name','')}")
        print(f"    Spend ₹{float(a.get('spend',0)):.0f}  |  CPM ₹{float(a.get('cpm',0)):.0f}  |  CTR {float(a.get('ctr',0)):.2f}%  |  Freq {float(a.get('frequency',0)):.2f}x")
        print(f"    Leads {a_leads}  |  CPL {fmt_cpl(a_cpl)}  |  Reach {int(a.get('reach',0)):,}")
        if p:
            print(f"    vs prev → CPL {fmt_cpl(p_cpl)} ({pct(a_cpl, p_cpl)})  |  CTR {float(p.get('ctr',0)):.2f}% ({pct(float(a.get('ctr',0)), float(p.get('ctr',0)))})")
        print()


# ── AD LEVEL ─────────────────────────────────────────────────────
section("3. AD LEVEL — Current 7d (sorted by CPL)")

cur_ads  = fetch_insights("ad", CUR_START,  CUR_END)
prev_ads = fetch_insights("ad", PREV_START, PREV_END)
prev_ad_map = {r["ad_name"]: r for r in prev_ads}

camp_ads = defaultdict(list)
for a in cur_ads:
    camp_ads[a.get("campaign_name", "")].append(a)

for camp_name, ads in camp_ads.items():
    print(f"\n  [{camp_name}]")
    divider()
    sorted_ads = sorted(ads, key=lambda x: cpl(x))
    for a in sorted_ads:
        p = prev_ad_map.get(a.get("ad_name", ""), {})
        a_leads = leads(a)
        a_cpl   = cpl(a)
        p_leads = leads(p)
        p_cpl   = cpl(p)
        status = "✅" if a_leads > 0 else "❌"
        print(f"  {status} Ad : {a.get('ad_name','')}")
        print(f"     Spend ₹{float(a.get('spend',0)):.0f}  |  CPM ₹{float(a.get('cpm',0)):.0f}  |  CTR {float(a.get('ctr',0)):.2f}%  |  CPC ₹{float(a.get('cpc',0)):.0f}")
        print(f"     Leads {a_leads}  |  CPL {fmt_cpl(a_cpl)}  |  Impressions {int(a.get('impressions',0)):,}")
        if p:
            print(f"     vs prev → CPL {fmt_cpl(p_cpl)} ({pct(a_cpl, p_cpl)})  |  Leads prev: {p_leads}")
        print()


# ── DIAGNOSIS ─────────────────────────────────────────────────────
section("4. DIAGNOSIS — Why did performance drop?")

target_camp = next((c for c in cur_camps if "18 june" in c.get("campaign_name","").lower()), None)
target_prev = next((p for p in prev_camps if "18 june" in p.get("campaign_name","").lower()), None)

if target_camp and target_prev:
    c_cpl_v  = cpl(target_camp)
    p_cpl_v  = cpl(target_prev)
    c_ctr_v  = float(target_camp.get("ctr", 0))
    p_ctr_v  = float(target_prev.get("ctr", 0))
    c_cpm_v  = float(target_camp.get("cpm", 0))
    p_cpm_v  = float(target_prev.get("cpm", 0))
    c_freq_v = float(target_camp.get("frequency", 0))
    p_freq_v = float(target_prev.get("frequency", 0))
    c_reach_v = int(target_camp.get("reach", 0))
    p_reach_v = int(target_prev.get("reach", 0))

    print(f"\n  Wedezine_Leadgen 18 june — Root Cause Signals:\n")

    # CPM check
    if c_cpm_v > p_cpm_v * 1.2:
        print(f"  🔴 CPM SPIKE: ₹{p_cpm_v:.0f} → ₹{c_cpm_v:.0f} (+{((c_cpm_v/p_cpm_v)-1)*100:.0f}%)")
        print(f"     → Auction competition increased. Meta is charging more per 1000 impressions.")
    else:
        print(f"  🟢 CPM stable: ₹{p_cpm_v:.0f} → ₹{c_cpm_v:.0f}")

    # CTR check
    if c_ctr_v < p_ctr_v * 0.85:
        print(f"  🔴 CTR DROP: {p_ctr_v:.2f}% → {c_ctr_v:.2f}% ({pct(c_ctr_v, p_ctr_v)})")
        print(f"     → Creative fatigue. Audience has seen this ad too many times.")
    else:
        print(f"  🟢 CTR holding: {p_ctr_v:.2f}% → {c_ctr_v:.2f}%")

    # Frequency check
    if c_freq_v > 2.5:
        print(f"  🔴 HIGH FREQUENCY: {p_freq_v:.2f}x → {c_freq_v:.2f}x")
        print(f"     → Same people seeing the ad repeatedly. Audience is saturated.")
    elif c_freq_v > p_freq_v * 1.3:
        print(f"  🟡 FREQUENCY RISING: {p_freq_v:.2f}x → {c_freq_v:.2f}x")
        print(f"     → Approaching saturation. New creatives needed soon.")
    else:
        print(f"  🟢 Frequency OK: {p_freq_v:.2f}x → {c_freq_v:.2f}x")

    # Reach check
    if c_reach_v < p_reach_v * 0.7:
        print(f"  🔴 REACH SHRINKING: {p_reach_v:,} → {c_reach_v:,}")
        print(f"     → Audience pool exhausted or budget reduced.")

    # CPL vs CTR divergence
    if c_ctr_v >= p_ctr_v * 0.9 and c_cpl_v > p_cpl_v * 1.3:
        print(f"  🔴 LANDING PAGE / FORM ISSUE:")
        print(f"     CTR is OK but CPL rose sharply — people click but don't convert.")
        print(f"     → Check: Meta lead form load speed, form questions, thank-you page.")

    print(f"\n  CPL summary: {fmt_cpl(p_cpl_v)} (prev 22d) → {fmt_cpl(c_cpl_v)} (last 7d)  [{pct(c_cpl_v, p_cpl_v)}]")

print(f"\n{'═'*62}")
print(f"  Analysis complete.")
print(f"{'═'*62}\n")
