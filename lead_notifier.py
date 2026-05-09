"""
lead_notifier.py — polls Meta Lead Ads every 2 min, sends Telegram on new leads
Deploy on Railway as a background worker
"""

import os, time, json, requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv("/Users/ankitshukla/Downloads/meta_agent/.env")

META_TOKEN   = os.getenv("META_ACCESS_TOKEN")
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8734256243:AAEFMWGo7Gf1viaS-pcK6UN_hTg4fVPRlhA")
TG_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "8662698670")
BASE         = "https://graph.facebook.com/v18.0"
POLL_SECS    = 120

seen_ids = set()
last_ts  = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())


# ── Meta ──────────────────────────────────────────────────────────────
def meta(path, params=None):
    p = dict(params or {})
    p["access_token"] = META_TOKEN
    return requests.get(f"{BASE}/{path}", params=p, timeout=30).json()


def get_pages():
    return meta("me/accounts", {"fields": "id,name,access_token"}).get("data", [])


def get_forms(page_token, page_id):
    r = requests.get(f"{BASE}/{page_id}/leadgen_forms", params={
        "access_token": page_token, "fields": "id,name", "limit": 50
    }, timeout=30).json()
    return r.get("data", [])


def get_new_leads(page_token, form_id, since_ts):
    r = requests.get(f"{BASE}/{form_id}/leads", params={
        "access_token": page_token,
        "fields": "id,field_data,created_time,ad_name,adset_name,campaign_name",
        "limit": 20,
        "filtering": json.dumps([
            {"field": "time_created", "operator": "GREATER_THAN", "value": since_ts}
        ]),
    }, timeout=30).json()
    return r.get("data", [])


# ── Telegram ──────────────────────────────────────────────────────────
def send_telegram(message: str):
    requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": message},
        timeout=10,
    )


def format_message(lead: dict, form_name: str) -> str:
    fd = {f["name"]: (f["values"][0] if f.get("values") else "")
          for f in lead.get("field_data", [])}
    name  = fd.get("full_name") or fd.get("name") or "—"
    phone = fd.get("phone_number", "—")
    ist   = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST")

    lines = [
        "🎯 New Lead!",
        "",
        f"👤 Name: {name}",
        f"📱 Phone: {phone}",
    ]
    # append any extra form fields
    skip = {"full_name", "name", "phone_number"}
    for k, v in fd.items():
        if k not in skip and v:
            lines.append(f"📝 {k.replace('_',' ').title()}: {v}")

    lines += [
        f"📣 Campaign: {lead.get('campaign_name','—')}",
        f"📂 Ad Set: {lead.get('adset_name','—')}",
        f"🎨 Ad: {lead.get('ad_name','—')}",
        f"📋 Form: {form_name}",
        f"🕐 {ist}",
    ]
    return "\n".join(lines)


# ── poll loop ─────────────────────────────────────────────────────────
def poll():
    global last_ts
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Polling since ts={last_ts}…")
    new_count = 0

    pages = get_pages()
    if not pages:
        print("  No pages — check META_ACCESS_TOKEN permissions.")
        return

    for page in pages:
        forms = get_forms(page["access_token"], page["id"])
        for form in forms:
            leads = get_new_leads(page["access_token"], form["id"], last_ts)
            for lead in leads:
                lid = lead.get("id")
                if lid in seen_ids:
                    continue
                seen_ids.add(lid)
                msg = format_message(lead, form.get("name", ""))
                send_telegram(msg)
                print(f"  ✅ Notified: lead {lid}")
                new_count += 1

    last_ts = int(datetime.now(timezone.utc).timestamp())
    print(f"  Done — {new_count} new lead(s).\n")


if __name__ == "__main__":
    print("🚀 Lead notifier started — polling every 2 min.")
    send_telegram("✅ Meta Ads Lead Notifier is live! You will get instant alerts here for every new lead.")
    while True:
        try:
            poll()
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(POLL_SECS)
