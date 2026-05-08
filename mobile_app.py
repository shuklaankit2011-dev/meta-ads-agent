"""
Meta Ads Mobile Agent — Streamlit App
Local:  streamlit run mobile_app.py  →  http://192.168.1.17:8501
Cloud:  deploy to share.streamlit.io, set secrets in dashboard
"""

import streamlit as st
import os, requests, json
from datetime import datetime, timedelta, timezone

# ── set_page_config MUST be the very first Streamlit call ────────────
st.set_page_config(
    page_title="Meta Ads Agent",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── credentials: Streamlit Cloud secrets first, .env fallback ────────
def _secret(key):
    try:
        return st.secrets[key]
    except Exception:
        pass
    try:
        from dotenv import load_dotenv
        load_dotenv("/Users/ankitshukla/Downloads/meta_agent/.env")
    except Exception:
        pass
    return os.getenv(key)

APP_PASSWORD = _secret("APP_PASSWORD") or "wedezine2024"
TOKEN        = _secret("META_ACCESS_TOKEN")
BASE         = "https://graph.facebook.com/v18.0"

ACCOUNTS = {
    "WeDezine Studio  (1151039113402293)": "act_1151039113402293",
    "WeDezine Unnamed (386459926600152)":  "act_386459926600152",
    "YOHO             (1911713625671421)": "act_1911713625671421",
}

WDEZINE_PAGE_ID = "111879133966646"

# ── simple password gate ──────────────────────────────────────────────
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.title("🔒 Meta Ads Agent")
    pwd = st.text_input("Password", type="password", placeholder="Enter team password")
    if st.button("Login", use_container_width=True):
        if pwd == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Wrong password.")
    st.stop()

# ── CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .main .block-container { padding: 1rem 1rem 2rem; max-width: 480px; margin: auto; }
  h1 { font-size: 1.4rem !important; }
  h2 { font-size: 1.1rem !important; }
  .stButton>button { width: 100%; border-radius: 10px; height: 3rem; font-size: 1rem; }
  .green { color: #4ade80; } .red { color: #f87171; }
</style>
""", unsafe_allow_html=True)


# ── helpers ──────────────────────────────────────────────────────────
def api(url, params=None):
    p = dict(params or {})
    p["access_token"] = TOKEN
    r = requests.get(url, params=p, timeout=30)
    return r.json()


def leads_count(row):
    return sum(int(a["value"]) for a in row.get("actions", [])
               if a.get("action_type") == "lead")


def cpl(row):
    l = leads_count(row)
    s = float(row.get("spend", 0))
    return s / l if l > 0 else None


def fmt_inr(v):
    if v is None: return "—"
    return f"₹{v:,.0f}"


def pct_change(new, old):
    if not old: return ""
    c = ((new - old) / old) * 100
    arrow = "▲" if c > 0 else "▼"
    color = "green" if c < 0 else "red"
    return f'<span class="{color}">{arrow}{abs(c):.1f}%</span>'


def pct_change_higher_better(new, old):
    if not old: return ""
    c = ((new - old) / old) * 100
    arrow = "▲" if c > 0 else "▼"
    color = "green" if c > 0 else "red"
    return f'<span class="{color}">{arrow}{abs(c):.1f}%</span>'


def fetch_insights(account, since, until, level="campaign", limit=50):
    fields = "campaign_name,adset_name,ad_name,spend,impressions,reach,frequency,clicks,ctr,cpm,cpc,actions"
    r = api(f"{BASE}/{account}/insights", {
        "fields": fields,
        "time_range": json.dumps({"since": since, "until": until}),
        "level": level, "limit": limit,
    })
    if "error" in r:
        st.error(f"Meta API error: {r['error'].get('message', r['error'])}")
        return []
    return r.get("data", [])


@st.cache_data(ttl=300)
def fetch_pages():
    r = api(f"{BASE}/me/accounts", {"fields": "id,name,access_token"})
    return r.get("data", [])


# ── account switcher ──────────────────────────────────────────────────
st.title("📊 Meta Ads Agent")

selected_label = st.selectbox(
    "Ad Account",
    list(ACCOUNTS.keys()),
    key="account_switcher",
    label_visibility="collapsed",
)
ACCOUNT = ACCOUNTS[selected_label]
st.caption(f"`{ACCOUNT}`")
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Lead Lookup", "Deep Dive", "Interests"])


# ══════════════════════════════════════════════════════════════════════
# TAB 1 — Dashboard
# ══════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Campaign Overview")

    if st.button("🔌 Test Connection", key="test_conn"):
        with st.spinner("Checking token & account…"):
            me = api(f"{BASE}/me", {"fields": "id,name"})
            acct = api(f"{BASE}/{ACCOUNT}", {"fields": "id,name,account_status"})
        if "error" in me:
            st.error(f"Token invalid: {me['error']['message']}")
        else:
            st.success(f"Token OK — logged in as: {me.get('name')} ({me.get('id')})")
        if "error" in acct:
            st.error(f"Account error: {acct['error']['message']}")
        else:
            status = {1:"Active",2:"Disabled",3:"Unsettled",9:"In Grace Period"}.get(acct.get("account_status"),str(acct.get("account_status")))
            st.success(f"Account: {acct.get('name','—')} | Status: {status}")

    period = st.selectbox("Period", ["Last 7 days", "Last 14 days", "Last 30 days", "This month"], key="dash_period")
    period_map = {"Last 7 days": 7, "Last 14 days": 14, "Last 30 days": 30, "This month": None}

    if st.button("Fetch Campaigns", key="fetch_camps"):
        with st.spinner("Fetching…"):
            today = datetime.now()
            if period_map[period]:
                since = (today - timedelta(days=period_map[period])).strftime("%Y-%m-%d")
            else:
                since = today.replace(day=1).strftime("%Y-%m-%d")
            until = today.strftime("%Y-%m-%d")
            rows = fetch_insights(ACCOUNT, since, until, level="campaign")

        if not rows:
            st.warning("No data returned for this account.")
        else:
            total_spend = sum(float(r.get("spend", 0)) for r in rows)
            total_leads = sum(leads_count(r) for r in rows)
            avg_cpl     = total_spend / total_leads if total_leads else None

            c1, c2, c3 = st.columns(3)
            c1.metric("Spend", fmt_inr(total_spend))
            c2.metric("Leads", str(total_leads))
            c3.metric("CPL",   fmt_inr(avg_cpl))

            st.divider()
            for r in sorted(rows, key=lambda x: float(x.get("spend", 0)), reverse=True):
                with st.expander(r.get("campaign_name", "—")[:50]):
                    col1, col2 = st.columns(2)
                    col1.metric("Spend", fmt_inr(float(r.get("spend", 0))))
                    col2.metric("Leads", str(leads_count(r)))
                    col1.metric("CPL",   fmt_inr(cpl(r)))
                    col2.metric("CTR",   f"{float(r.get('ctr',0)):.2f}%")
                    col1.metric("CPM",   fmt_inr(float(r.get("cpm", 0))))
                    col2.metric("Freq",  f"{float(r.get('frequency',0)):.2f}x")


# ══════════════════════════════════════════════════════════════════════
# TAB 2 — Lead Lookup
# ══════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Lead Lookup by Phone")

    if st.button("Load Pages", key="load_pages"):
        with st.spinner("Fetching your Facebook pages…"):
            st.session_state.pages = fetch_pages()

    pages = st.session_state.get("pages", [])
    if pages:
        page_options = {f"{p['name']} ({p['id']})": p for p in pages}
        selected_page_label = st.selectbox("Facebook Page", list(page_options.keys()), key="page_picker")
        selected_page       = page_options[selected_page_label]
        selected_page_id    = selected_page["id"]
        selected_page_token = selected_page["access_token"]
    else:
        st.info("Tap 'Load Pages' first to select the Facebook page to search leads from.")
        selected_page_id    = None
        selected_page_token = None

    phone_raw   = st.text_input("Mobile number", placeholder="9XXXXXXXXX or +919XXXXXXXX", key="phone_input")
    date_filter = st.date_input("Date", value=datetime.now().date(), key="lead_date")

    if st.button("Search Lead", key="search_lead"):
        if not selected_page_id:
            st.error("Load pages first.")
        else:
            phone = phone_raw.strip().lstrip("+").lstrip("91") if phone_raw else ""
            if len(phone) != 10:
                st.error("Enter a valid 10-digit Indian mobile number.")
            else:
                with st.spinner("Loading forms…"):
                    forms_r = api(f"{BASE}/{selected_page_id}/leadgen_forms", {
                        "access_token": selected_page_token,
                        "fields": "id,name",
                        "limit": 50,
                    })
                    forms = forms_r.get("data", [])

                found    = False
                progress = st.progress(0, text="Searching forms…")

                ist       = timezone(timedelta(hours=5, minutes=30))
                day_start = datetime(date_filter.year, date_filter.month, date_filter.day, 0, 0, 0, tzinfo=ist)
                day_end   = day_start + timedelta(days=1)
                ts_start  = int(day_start.timestamp())
                ts_end    = int(day_end.timestamp())

                for idx, form in enumerate(forms):
                    fid   = form["id"]
                    fname = form.get("name", fid)
                    progress.progress((idx + 1) / max(len(forms), 1), text=f"Checking: {fname[:30]}")

                    r = api(f"{BASE}/{fid}/leads", {
                        "access_token": selected_page_token,
                        "fields": "field_data,created_time,ad_name,adset_name,campaign_name",
                        "limit": 200,
                        "filtering": json.dumps([
                            {"field": "time_created", "operator": "GREATER_THAN", "value": ts_start},
                            {"field": "time_created", "operator": "LESS_THAN",    "value": ts_end},
                        ]),
                    })

                    for lead in r.get("data", []):
                        fields_data = {f["name"]: (f["values"][0] if f.get("values") else "")
                                       for f in lead.get("field_data", [])}
                        lead_phone = fields_data.get("phone_number", "").strip().lstrip("+").lstrip("91")
                        if lead_phone == phone:
                            found = True
                            progress.empty()
                            st.success("Lead found!")
                            st.markdown(f"**Form:** {fname}")
                            st.markdown(f"**Campaign:** {lead.get('campaign_name','—')}")
                            st.markdown(f"**Ad Set:** {lead.get('adset_name','—')}")
                            st.markdown(f"**Ad:** {lead.get('ad_name','—')}")
                            st.markdown(f"**Created:** {lead.get('created_time','—')}")
                            st.divider()
                            for k, v in fields_data.items():
                                st.markdown(f"- **{k}:** {v}")
                            break
                    if found:
                        break

                progress.empty()
                if not found:
                    st.warning(f"No lead found for {phone} on {date_filter}.")


# ══════════════════════════════════════════════════════════════════════
# TAB 3 — Deep Dive
# ══════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Period Comparison")

    col1, col2 = st.columns(2)
    with col1:
        cur_days  = st.number_input("Current (days)", value=7,  min_value=1, max_value=90, key="cur_days")
    with col2:
        prev_days = st.number_input("Previous (days)", value=22, min_value=1, max_value=90, key="prev_days")

    level = st.selectbox("Level", ["campaign", "adset", "ad"], key="deep_level")

    if st.button("Run Comparison", key="run_deep"):
        with st.spinner("Fetching…"):
            today      = datetime.now()
            cur_end    = today.strftime("%Y-%m-%d")
            cur_start  = (today - timedelta(days=int(cur_days))).strftime("%Y-%m-%d")
            prev_end   = (today - timedelta(days=int(cur_days)+1)).strftime("%Y-%m-%d")
            prev_start = (today - timedelta(days=int(cur_days)+int(prev_days))).strftime("%Y-%m-%d")

            cur_rows  = fetch_insights(ACCOUNT, cur_start, cur_end, level=level)
            prev_rows = fetch_insights(ACCOUNT, prev_start, prev_end, level=level)

        if not cur_rows:
            st.warning("No data returned for this account.")
        else:
            name_key = {"campaign": "campaign_name", "adset": "adset_name", "ad": "ad_name"}[level]
            prev_map = {r[name_key]: r for r in prev_rows}

            for row in sorted(cur_rows, key=lambda x: float(x.get("spend", 0)), reverse=True):
                name    = row.get(name_key, "—")
                prev    = prev_map.get(name, {})
                c_spend = float(row.get("spend", 0))
                c_cpl_v = cpl(row)
                c_leads = leads_count(row)
                c_ctr   = float(row.get("ctr", 0))
                c_cpm   = float(row.get("cpm", 0))
                c_freq  = float(row.get("frequency", 0))
                p_cpl_v = cpl(prev)
                p_leads = leads_count(prev)
                p_ctr   = float(prev.get("ctr", 0))
                p_cpm   = float(prev.get("cpm", 0))

                with st.expander(f"{name[:45]}  —  ₹{c_spend:,.0f}"):
                    cpl_html = pct_change(c_cpl_v, p_cpl_v) if (p_cpl_v and c_cpl_v) else ""
                    st.markdown(f"""
                    <table width="100%">
                      <tr><th align="left">Metric</th><th>Now</th><th>Prev</th><th>Δ</th></tr>
                      <tr><td>Spend</td><td>{fmt_inr(c_spend)}</td><td>{fmt_inr(float(prev.get('spend',0)))}</td><td></td></tr>
                      <tr><td>Leads</td><td>{c_leads}</td><td>{p_leads}</td><td>{pct_change_higher_better(c_leads, p_leads)}</td></tr>
                      <tr><td>CPL</td><td>{fmt_inr(c_cpl_v)}</td><td>{fmt_inr(p_cpl_v)}</td><td>{cpl_html}</td></tr>
                      <tr><td>CTR</td><td>{c_ctr:.2f}%</td><td>{p_ctr:.2f}%</td><td>{pct_change_higher_better(c_ctr, p_ctr)}</td></tr>
                      <tr><td>CPM</td><td>{fmt_inr(c_cpm)}</td><td>{fmt_inr(p_cpm)}</td><td>{pct_change(c_cpm, p_cpm)}</td></tr>
                      <tr><td>Freq</td><td>{c_freq:.2f}x</td><td>{float(prev.get('frequency',0)):.2f}x</td><td></td></tr>
                    </table>
                    """, unsafe_allow_html=True)

                    issues = []
                    if p_cpm and c_cpm > p_cpm * 1.2:
                        issues.append(f"🔴 CPM spike: {fmt_inr(p_cpm)} → {fmt_inr(c_cpm)}")
                    if p_ctr and c_ctr < p_ctr * 0.85:
                        issues.append(f"🔴 CTR dropped: {p_ctr:.2f}% → {c_ctr:.2f}% — creative fatigue")
                    if c_freq > 2.5:
                        issues.append(f"🔴 High frequency {c_freq:.2f}x — audience saturated")
                    if p_cpl_v and c_cpl_v and c_ctr >= (p_ctr * 0.9 if p_ctr else 0) and c_cpl_v > p_cpl_v * 1.3:
                        issues.append("🔴 CTR OK but CPL rose — check lead form / landing page")
                    if issues:
                        st.divider()
                        for i in issues:
                            st.markdown(i)


# ══════════════════════════════════════════════════════════════════════
# TAB 4 — Interest Research
# ══════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Facebook Interest Search")

    query = st.text_input("Search interests", placeholder="home interior, real estate…", key="interest_q")

    if st.button("Search Interests", key="search_int") and query:
        with st.spinner("Fetching…"):
            r = api(f"{BASE}/search", {"type": "adinterest", "q": query, "limit": 30})
            interests = r.get("data", [])

        if not interests:
            st.warning("No interests found.")
        else:
            interests_sorted = sorted(
                [i for i in interests if i.get("audience_size_upper_bound")],
                key=lambda x: x.get("audience_size_upper_bound", 0),
                reverse=True,
            )
            for i in interests_sorted:
                name = i.get("name", "")
                ub   = i.get("audience_size_upper_bound", 0)
                lb   = i.get("audience_size_lower_bound", 0)
                path = " › ".join(i.get("path", []))

                if ub > 50_000_000:   size_tag = "🟡 Very broad"
                elif ub > 10_000_000: size_tag = "🟢 Good"
                elif ub > 1_000_000:  size_tag = "🟢 Niche-good"
                else:                 size_tag = "🔵 Very niche"

                with st.expander(f"{name}  —  {size_tag}"):
                    st.markdown(f"**Audience:** {lb:,} – {ub:,}")
                    if path:
                        st.markdown(f"**Category:** {path}")
                    st.code(f'"{name}"', language=None)
