"""
lead_notifier.py — polls Meta Lead Ads every 2 min, sends WhatsApp on new leads
Deploy on Railway as a background worker: railway up
"""

import os, time, json, requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv("/Users/ankitshukla/Downloads/meta_agent/.env")

META_TOKEN    = os.getenv("META_ACCESS_TOKEN")
WA_PHONE_ID   = os.getenv("WA_PHONE_NUMBER_ID", "1126680890521533")
NOTIFY_TO     = os.getenv("NOTIFY_WHATSAPP",    "919035481300")   # always 91 prefix, no +
BASE          = "https://graph.facebook.com/v18.0"
POLL_INTERVAL = 120  # seconds

seen_ids  = set()
last_ts   = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp())


# ── Meta helpers ──────────────────────────────────────────────────────
def meta_get(path, params=None):
    p = dict(params or {})
    p["access_token"] = META_TOKEN
    return requests.get(f"{BASE}/{path}", params=p, timeout=30).json()


def get_pages():
    return meta_get("me/accounts", {"fields": "id,name,access_token"}).get("data", [])


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


# ── WhatsApp sender ───────────────────────────────────────────────────
def send_whatsapp(to: str, message: str) -> dict:
    return requests.post(
        f"{BASE}/{WA_PHONE_ID}/messages",
        headers={
            "Authorization": f"Bearer {META_TOKEN}",
            "Content-Type":  "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "text",
            "text":              {"preview_url": False, "body": message},
        },
        timeout=30,
    ).json()


def format_message(lead: dict, form_name: str) -> str:
    fd = {
        f["name"]: (f["values"][0] if f.get("values") else "")
        for f in lead.get("field_data", [])
    }
    name  = fd.get("full_name") or fd.get("name") or "—"
    phone = fd.get("phone_number", "—")

    ist = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST")

    return (
        f"🎯 *New Lead!*\n\n"
        f"👤 {name}\n"
        f"📱 {phone}\n"
        f"📣 Campaign: {lead.get('campaign_name','—')}\n"
        f"📂 Ad Set: {lead.get('adset_name','—')}\n"
        f"🎨 Ad: {lead.get('ad_name','—')}\n"
        f"📋 Form: {form_name}\n"
        f"🕐 {ist}"
    )


# ── poll loop ─────────────────────────────────────────────────────────
def poll():
    global last_ts
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking leads since ts={last_ts}…")
    new_count = 0

    pages = get_pages()
    if not pages:
        print("  No pages found — check token permissions.")
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

                msg    = format_message(lead, form.get("name", ""))
                result = send_whatsapp(NOTIFY_TO, msg)

                if "messages" in result:
                    print(f"  ✅ WhatsApp sent for lead {lid}")
                    new_count += 1
                else:
                    print(f"  ❌ WhatsApp error: {result.get('error', result)}")

    last_ts = int(datetime.now(timezone.utc).timestamp())
    print(f"  Done. {new_count} new lead(s) notified.\n")


if __name__ == "__main__":
    print("🚀 Lead notifier started — polling every 2 minutes.")
    print(f"   Sending alerts to: +{NOTIFY_TO}\n")
    while True:
        try:
            poll()
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
        time.sleep(POLL_INTERVAL)
