"""
lead_notifier_once.py — single poll, run by GitHub Actions every 5 min
State (seen lead IDs + last timestamp) stored in seen_leads.json via Actions cache
"""

import os, json, requests
from datetime import datetime, timezone, timedelta

META_TOKEN   = os.environ["META_ACCESS_TOKEN"]
TG_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
BASE         = "https://graph.facebook.com/v18.0"
STATE_FILE   = "seen_leads.json"
LOOKBACK     = 10   # minutes — check leads from last 10 min


# ── state ─────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen_ids": [], "last_ts": int((datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK)).timestamp())}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ── Meta ──────────────────────────────────────────────────────────────
def meta_get(path, params=None):
    p = dict(params or {})
    p["access_token"] = META_TOKEN
    r = requests.get(f"{BASE}/{path}", params=p, timeout=30)
    return r.json()

def get_pages():
    return meta_get("me/accounts", {"fields": "id,name,access_token"}).get("data", [])

def get_forms(page_token, page_id):
    return requests.get(f"{BASE}/{page_id}/leadgen_forms", params={
        "access_token": page_token, "fields": "id,name", "limit": 50
    }, timeout=30).json().get("data", [])

def get_leads(page_token, form_id, since_ts):
    return requests.get(f"{BASE}/{form_id}/leads", params={
        "access_token": page_token,
        "fields": "id,field_data,created_time,ad_name,adset_name,campaign_name",
        "limit": 20,
        "filtering": json.dumps([
            {"field": "time_created", "operator": "GREATER_THAN", "value": since_ts}
        ]),
    }, timeout=30).json().get("data", [])


# ── Telegram ──────────────────────────────────────────────────────────
def send(msg):
    requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                  json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)

def format_lead(lead, form_name):
    fd = {f["name"]: (f["values"][0] if f.get("values") else "")
          for f in lead.get("field_data", [])}
    name  = fd.get("full_name") or fd.get("name") or "—"
    phone = fd.get("phone_number", "—")
    ist   = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %I:%M %p IST")

    lines = ["🎯 New Lead!", "", f"👤 Name: {name}", f"📱 Phone: {phone}"]
    skip  = {"full_name", "name", "phone_number"}
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


# ── main ──────────────────────────────────────────────────────────────
def main():
    state    = load_state()
    seen_ids = set(state["seen_ids"])
    since_ts = state["last_ts"]
    found    = 0

    pages = get_pages()
    if not pages:
        print("No pages — check META_ACCESS_TOKEN")
        return

    for page in pages:
        for form in get_forms(page["access_token"], page["id"]):
            for lead in get_leads(page["access_token"], form["id"], since_ts):
                lid = lead.get("id")
                if lid in seen_ids:
                    continue
                seen_ids.add(lid)
                send(format_lead(lead, form.get("name", "")))
                print(f"Notified lead {lid}")
                found += 1

    print(f"Done. {found} new lead(s).")
    save_state({
        "seen_ids": list(seen_ids)[-500:],   # keep last 500 to avoid file bloat
        "last_ts":  int(datetime.now(timezone.utc).timestamp()),
    })

if __name__ == "__main__":
    main()
