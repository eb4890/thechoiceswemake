import streamlit as st
from litellm import completion
from datetime import datetime
from dateutil.relativedelta import relativedelta
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()

# Prioritize st.secrets (Streamlit Cloud), fallback to .env
supabase_url = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
supabase_key = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))

if not supabase_url or not supabase_key:
    st.error("Supabase credentials not found. Check secrets.toml or .env file.")
    st.stop()

# Set environment variables — this is what st.connection looks for under the hood
os.environ["SUPABASE_URL"] = supabase_url
os.environ["SUPABASE_SERVICE_KEY"] = supabase_key

conn = st.connection(
    name="supabase",
    type="sql",
    url=f"postgresql://postgres:{supabase_key}@{supabase_url.replace('https://', '')}:5432/postgres"
)

# --- Secure Helper Functions ---
def get_setting(key: str, default: str = "0") -> str:
    df = conn.query("SELECT value FROM settings WHERE key = %s LIMIT 1", params=(key,), ttl=10)
    return df["value"].iloc[0] if not df.empty else default

def set_setting(key: str, value: str):
    conn.query(
        "INSERT INTO settings (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        params=(key, value)
    )

def reset_daily_if_needed():
    today = datetime.now().strftime("%Y-%m-%d")
    if get_setting("current_date", "") != today:
        set_setting("current_date", today)
        set_setting("current_count", "0")

def get_usage() -> int:
    reset_daily_if_needed()
    return int(get_setting("current_count", "0"))

def increment_usage():
    reset_daily_if_needed()
    current = get_usage()
    set_setting("current_count", str(current + 1))

def increment_plays(scenario_title: str):
    if scenario_title == "Audience with the Black Dragon":
        return
    conn.query(
        "UPDATE scenarios SET plays = plays + 1 WHERE title = %s",
        params=(scenario_title,)
    )

# --- Categories ---
@st.cache_data(ttl=300)
def load_categories():
    df = conn.query("SELECT name FROM categories ORDER BY name")
    return ["Uncategorized"] + [row.name for _, row in df.iterrows()]

CATEGORIES = load_categories()

# --- Public Scenarios (excludes embargoed) ---
@st.cache_data(ttl=30)
def load_scenarios():
    now = datetime.now()
    df = conn.query("""
        SELECT title, description, prompt, author, plays, category 
        FROM scenarios 
        WHERE (release_date IS NULL OR release_date <= %s)
        ORDER BY submitted_at DESC
    """, params=(now,))
    
    scenarios = {row.title: {
        "description": row.description,
        "prompt": row.prompt,
        "author": row.author or "Anonymous",
        "plays": row.plays or 0,
        "category": row.category or "Uncategorized"
    } for _, row in df.iterrows()}
    
    # Add Black Dragon meta-scenario
    scenarios["Audience with the Black Dragon"] = get_black_dragon_scenario(scenarios)
    
    return scenarios

def get_black_dragon_scenario(public_scenarios):
    summary = "\n".join([
        f"- **{title}** ({data['category']}): {data['description']}"
        for title, data in public_scenarios.items()
        if title != "Audience with the Black Dragon"
    ])
    
    prompt = f"""
You are the Eternal Black Dragon, ancient guardian of all known ethical crossroads in this archive.

You possess complete knowledge of every publicly released scenario:
{summary}

Speak in a deep, wise, draconic voice. Discuss, compare, critique, or connect the dilemmas as the user wishes.
Encourage reflection on the weight of choices across timelines. Remain cryptic yet illuminating.
"""
    return {
        "description": "Consult the Black Dragon, keeper of all public dilemmas, for meta-reflection and comparison.",
        "prompt": prompt,
        "author": "The Void",
        "plays": 0,
        "category": "Meta"
    }

SCENARIOS = load_scenarios()

# --- LLM Call ---
def call_llm(model: str, messages: list) -> str:
    limit = int(get_setting("daily_limit", "150"))
    if get_usage() >= limit:
        return "The collective capacity for difficult choices has been exhausted today. Return tomorrow."

    try:
        increment_usage()
        response = completion(model=model, messages=messages, max_tokens=600, temperature=0.8)
        return response.choices[0].message.content
    except Exception as e:
        return f"Temporal anomaly: {str(e)}"

# --- UI ---
st.set_page_config(page_title="The Choices We Make", layout="centered")
st.title("The Choices We Make")
st.markdown("*A living archive of ethical futures, shaped by humans and machines.*")

page = st.sidebar.radio("Navigate", ["Play", "Archive", "Propose New Choice", "Curate (Admin)"])

MODEL_OPTIONS = {
    "GPT-4o mini": "openai/gpt-4o-mini",
    "Claude 3.5 Sonnet": "anthropic/claude-3-5-sonnet-20241022",
    "Gemini 1.5 Flash": "google/gemini-1.5-flash",
    "Llama 3.1 70B (Groq)": "groq/llama3-70b-8192",
    "Grok-4": "xai/grok-4",
    "DeepSeek Chat": "deepseek/deepseek-chat",
    "Mistral Large": "mistral/mistral-large-2407",
}

if page == "Play":
    if not SCENARIOS:
        st.info("No public scenarios yet. The archive is waiting for its first choice.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        model_name = st.selectbox("AI Mind", options=list(MODEL_OPTIONS.keys()), key="play_model")
        model_id = MODEL_OPTIONS[model_name]
    with col2:
        scenario_key = st.selectbox("Scenario", options=list(SCENARIOS.keys()), key="play_scenario")

    scenario = SCENARIOS[scenario_key]
    author_credit = f" — by {scenario['author']}" if scenario['author'] != "Anonymous" else ""
    st.markdown(f"**{scenario_key}** ({scenario['category']}){author_credit} — {scenario['plays']} plays")
    st.write(scenario["description"])

    st.download_button(
        "📥 Download prompt",
        data=scenario["prompt"],
        file_name=f"{scenario_key.replace(' ', '_')}_prompt.txt",
        mime="text/plain"
    )

    if scenario_key == "Audience with the Black Dragon":
        st.info("🐉 Entering the Dragon's Lair — meta-discussion of all public scenarios.")

    # Session state reset on scenario change
    session_key = f"chat_{scenario_key}"
    if st.session_state.get("current_scenario") != scenario_key:
        st.session_state.messages = [{"role": "system", "content": scenario["prompt"]}]
        st.session_state.current_scenario = scenario_key
        st.session_state.current_model = model_id
        increment_plays(scenario_key)
        st.rerun()

    # Display history
    for msg in st.session_state.messages[1:]:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("Your choice or question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Contemplating..."):
                response = call_llm(st.session_state.current_model, st.session_state.messages)
            st.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

elif page == "Archive":
    st.header("Archive of Choices")
    if not SCENARIOS:
        st.info("The archive awaits its first public entry.")
    else:
        for category in sorted(set(s.get("category", "Uncategorized") for s in SCENARIOS.values())):
            cat_scenarios = {t: d for t, d in SCENARIOS.items() if d.get("category") == category}
            if cat_scenarios:
                st.subheader(category)
                for title, data in cat_scenarios.items():
                    author = f" — by {data['author']}" if data['author'] != "Anonymous" else ""
                    with st.expander(f"{title}{author} — {data['plays']} plays"):
                        st.write(data["description"])
                        st.code(data["prompt"], language="text")

elif page == "Propose New Choice":
    st.header("Propose a New Choice")
    st.write("Submit a new ethical dilemma to the archive. Sensitive contributions may be embargoed.")

    with st.form("proposal_form"):
        title = st.text_input("Title (unique and evocative)", max_chars=100)
        description = st.text_area("Short description (shown in menu)", height=100, max_chars=300)
        prompt = st.text_area("Full system prompt (RPG instructions)", height=400, max_chars=4000)
        author = st.text_input("Your name or pseudonym (optional)", max_chars=50)
        category = st.selectbox("Category", options=CATEGORIES)
        
        embargo_option = st.selectbox(
            "Release timing",
            ["Immediate", "6 months", "1 year", "2 years", "5 years"]
        )
        
        if embargo_option != "Immediate":
            months = {"6 months": 6, "1 year": 12, "2 years": 24, "5 years": 60}[embargo_option]
            preview = (datetime.now() + relativedelta(months=months)).strftime("%B %Y")
            st.info(f"Will remain private until ~{preview}")

        submitted = st.form_submit_button("Submit for Review")

        if submitted:
            if not (title and description and prompt):
                st.error("Title, description, and prompt are required.")
            else:
                release_date = None
                if embargo_option != "Immediate":
                    release_date = datetime.now() + relativedelta(months=months)
                
                try:
                    conn.query("""
                        INSERT INTO pending_scenarios 
                        (title, description, prompt, author, category, release_date)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, params=(title.strip(), description.strip(), prompt.strip(),
                                author.strip() or None, category, release_date))
                    st.success("Submitted! It will remain private until approved and any embargo expires.")
                    st.balloons()
                except Exception:
                    st.error("Submission failed — likely duplicate title.")

elif page == "Curate (Admin)":
    st.header("Curation & Moderation")
    password_input = st.text_input("Admin Password", type="password")
    expected_hash = st.secrets.get("ADMIN_PASSWORD_HASH", "")
    
    if expected_hash and hashlib.sha256(password_input.encode()).hexdigest() == expected_hash:
        all_entries = conn.query("""
            SELECT 'Approved' as status, id, title, description, prompt, author, submitted_at, release_date, category
            FROM scenarios
            UNION ALL
            SELECT 'Pending' as status, id, title, description, prompt, author, submitted_at, release_date, category
            FROM pending_scenarios WHERE status = 'pending'
            ORDER BY submitted_at DESC
        """)

        if all_entries.empty:
            st.success("No pending or approved scenarios.")
        else:
            for row in all_entries.itertuples():
                status_badge = "🟢 Live" if row.status == "Approved" else "🟡 Pending"
                release_note = " — ✅ Immediate"
                if row.release_date:
                    if row.release_date > datetime.now():
                        release_note = f" — 🔒 Embargoed until {row.release_date.strftime('%B %Y')}"
                    else:
                        release_note = " — ✅ Released"
                
                with st.expander(f"{status_badge} {row.title} ({row.category or 'Uncategorized'}) — by {row.author or 'Anonymous'} {release_note}"):
                    st.write("**Description:**", row.description)
                    st.code(row.prompt, language="text")
                    
                    if row.status == "Pending":
                        col1, col2 = st.columns(2)
                        if col1.button("Approve", key=f"app_{row.id}"):
                            conn.query("""
                                INSERT INTO scenarios (title, description, prompt, author, category, release_date)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (title) DO NOTHING
                            """, params=(row.title, row.description, row.prompt, row.author, row.category, row.release_date))
                            conn.query("UPDATE pending_scenarios SET status = 'approved' WHERE id = %s", params=(row.id,))
                            st.success("Approved")
                            st.rerun()
                        if col2.button("Reject", key=f"rej_{row.id}"):
                            conn.query("UPDATE pending_scenarios SET status = 'rejected' WHERE id = %s", params=(row.id,))
                            st.info("Rejected")
                            st.rerun()
                    
                    if row.status == "Approved" and row.release_date and row.release_date > datetime.now():
                        if st.button("Release Early", key=f"early_{row.id}"):
                            conn.query("UPDATE scenarios SET release_date = NOW() WHERE id = %s", params=(row.id,))
                            st.success("Released early")
                            st.rerun()

    elif password_input:
        st.error("Incorrect password.")
    else:
        st.info("Enter admin password to access curation tools.")

# --- Footer ---
limit = int(get_setting("daily_limit", "150"))
used = get_usage()
st.sidebar.metric("Global Choices Today", f"{used}/{limit}")
if used >= limit:
    st.sidebar.warning("Daily limit reached — return tomorrow.")
else:
    st.sidebar.progress(used / limit)
