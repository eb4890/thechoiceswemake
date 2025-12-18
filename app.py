import streamlit as st
from litellm import completion
from datetime import datetime
import hashlib

# --- Supabase Connection ---
conn = st.connection("supabase", type="sql")

# --- Secure Settings Functions ---
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
    conn.query(
        "UPDATE scenarios SET plays = plays + 1 WHERE title = %s",
        params=(scenario_title,)
    )

# --- Secure Scenario Loading ---
@st.cache_data(ttl=30)  # Refresh every 30 seconds
def load_scenarios():
    df = conn.query(
        "SELECT title, description, prompt, author, plays FROM scenarios ORDER BY submitted_at DESC"
    )
    return {row.title: {
        "description": row.description,
        "prompt": row.prompt,
        "author": row.author or "Anonymous",
        "plays": row.plays or 0
    } for _, row in df.iterrows()}

# --- LLM Call (unchanged logic) ---
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

SCENARIOS = load_scenarios()

if page == "Play":
    if not SCENARIOS:
        st.info("No approved scenarios yet. Submit one via 'Propose New Choice'!")
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        model_name = st.selectbox("AI Mind", options=list(MODEL_OPTIONS.keys()), key="play_model")
        model_id = MODEL_OPTIONS[model_name]
    with col2:
        scenario_key = st.selectbox("Scenario", options=list(SCENARIOS.keys()), key="play_scenario")

    scenario = SCENARIOS[scenario_key]
    author_credit = f" — by {scenario['author']}" if scenario['author'] != "Anonymous" else ""
    st.markdown(f"**{scenario_key}{author_credit}** ({scenario['plays']} plays)")
    st.write(scenario["description"])

    st.download_button(
        "📥 Download prompt",
        data=scenario["prompt"],
        file_name=f"{scenario_key.replace(' ', '_')}_prompt.txt",
        mime="text/plain"
    )

    # Reset session if scenario changes
    if "current_scenario" not in st.session_state or st.session_state.current_scenario != scenario_key:
        st.session_state.messages = [{"role": "system", "content": scenario["prompt"]}]
        st.session_state.current_scenario = scenario_key
        st.session_state.current_model = model_id
        increment_plays(scenario_key)
        st.rerun()

    # Display chat
    for msg in st.session_state.messages[1:]:
        st.chat_message(msg["role"]).write(msg["content"])

    if prompt := st.chat_input("Your choice or response..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Contemplating the future..."):
                response = call_llm(st.session_state.current_model, st.session_state.messages)
            st.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})

elif page == "Archive":
    st.header("Archive of Choices")
    if not SCENARIOS:
        st.info("Archive is empty.")
    for title, data in SCENARIOS.items():
        author = f" — by {data['author']}" if data['author'] != "Anonymous" else ""
        with st.expander(f"{title}{author} — {data['plays']} plays"):
            st.write(data["description"])
            st.code(data["prompt"], language="text")

elif page == "Propose New Choice":
    st.header("Propose a New Choice")
    st.write("Submit a new ethical dilemma. All submissions are reviewed before appearing.")

    with st.form("proposal_form"):
        title = st.text_input("Title (unique, clear, compelling)", max_chars=100)
        description = st.text_area("Short description (shown in menu)", height=100, max_chars=300)
        prompt = st.text_area("Full system prompt (RPG narrator instructions)", height=400, max_chars=4000)
        author = st.text_input("Your name or pseudonym (optional)", max_chars=50)
        submitted = st.form_submit_button("Submit for Review")

        if submitted:
            if not (title and description and prompt):
                st.error("Title, description, and prompt are required.")
            elif len(title) < 5 or len(description) < 20 or len(prompt) < 100:
                st.error("Inputs are too short — please provide meaningful content.")
            else:
                try:
                    conn.query("""
                        INSERT INTO pending_scenarios (title, description, prompt, author)
                        VALUES (%s, %s, %s, %s)
                    """, params=(title.strip(), description.strip(), prompt.strip(), author.strip() or None))
                    st.success("Thank you! Your scenario is now pending moderation.")
                    st.balloons()
                except Exception as e:
                    if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                        st.error("A scenario with this title already exists or is pending.")
                    else:
                        st.error("Submission failed — try again.")

elif page == "Curate (Admin)":
    st.header("Curation Queue")
    password_input = st.text_input("Admin Password", type="password")
    # Secure check — never store plaintext, but since it's in secrets, we hash the input to compare
    expected_hash = st.secrets.get("ADMIN_PASSWORD_HASH", "")
    
    if expected_hash and hashlib.sha256(password_input.encode()).hexdigest() == expected_hash:
        pending = conn.query("""
            SELECT id, title, description, prompt, author, submitted_at 
            FROM pending_scenarios 
            WHERE status = 'pending' 
            ORDER BY submitted_at DESC
        """)

        if pending.empty:
            st.success("No pending submissions.")
        else:
            for row in pending.itertuples():
                author = row.author or "Anonymous"
                with st.expander(f"{row.title} — by {author} — {row.submitted_at.date()}"):
                    st.write("**Description:**")
                    st.write(row.description)
                    st.write("**Prompt:**")
                    st.code(row.prompt, language="text")

                    col1, col2 = st.columns(2)
                    if col1.button("✅ Approve", key=f"approve_{row.id}"):
                        try:
                            conn.query("""
                                INSERT INTO scenarios (title, description, prompt, author)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (title) DO NOTHING
                            """, params=(row.title, row.description, row.prompt, row.author))
                            conn.query(
                                "UPDATE pending_scenarios SET status = 'approved' WHERE id = %s",
                                params=(row.id,)
                            )
                            st.success(f"Approved: {row.title}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

                    if col2.button("❌ Reject", key=f"reject_{row.id}"):
                        conn.query(
                            "UPDATE pending_scenarios SET status = 'rejected' WHERE id = %s",
                            params=(row.id,)
                        )
                        st.info(f"Rejected: {row.title}")
                        st.rerun()

    elif password_input:
        st.error("Incorrect password.")
    else:
        st.info("Enter the admin password to access curation.")

# --- Footer ---
limit = int(get_setting("daily_limit", "150"))
used = get_usage()
remaining = limit - used
st.sidebar.metric("Global Choices Today", f"{used}/{limit}")
if remaining <= 0:
    st.sidebar.warning("Daily limit reached")
else:
    st.sidebar.progress(used / limit)
