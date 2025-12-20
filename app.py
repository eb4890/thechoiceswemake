import streamlit as st
from litellm import completion
from datetime import datetime
from dateutil.relativedelta import relativedelta
import hashlib
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://choices_user:your_very_strong_password_here@localhost:5433/choices_archive")

conn = st.connection(
    name="db",
    type="sql",
    url=DATABASE_URL
)

def execute_write(sql: str, params=None):
    """
    Execute a write query using SQLAlchemy's connection management.
    Handles transactions automatically to ensure data is saved.
    """
    with conn._instance.begin() as connection:
        connection.exec_driver_sql(sql, params or ())

# --- Secure Helper Functions ---
def get_setting(key: str, default: str = "0") -> str:
    df = conn.query("SELECT value FROM settings WHERE key = :setting LIMIT 1", params={"setting": key}, ttl=10)
    return df["value"].iloc[0] if not df.empty else default

def set_setting(key: str, value: str):
    execute_write(
            "INSERT INTO settings (key, value) VALUES ( %s , %s ) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        params=( key, value)
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
    execute_write(
        "UPDATE scenarios SET plays = plays + 1 WHERE title = %s",
        params=(scenario_title,)
    )

def record_journey(scenario_title, model_name, choice_text, summary, author):
    execute_write("""
        INSERT INTO journeys 
        (scenario_title, llm_model, choice_text, summary, author)
        VALUES (%s, %s, %s, %s, %s)
    """, params=(scenario_title, model_name, choice_text, summary, author))

def propose_scenario(title, description, prompt, author, category, release_date):
    execute_write("""
        INSERT INTO pending_scenarios 
        (title, description, prompt, author, category, release_date)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, params=(title, description, prompt, author, category, release_date))

def approve_scenario(scenario_id, title, description, prompt, author, category, release_date):
    execute_write("""
        INSERT INTO scenarios (title, description, prompt, author, category, release_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (title) DO NOTHING
    """, params=(title, description, prompt, author, category, release_date))
    execute_write("UPDATE pending_scenarios SET status = 'approved' WHERE id = %s", params=(scenario_id,))

def reject_scenario(scenario_id):
    execute_write("UPDATE pending_scenarios SET status = 'rejected' WHERE id = %s", params=(scenario_id,))

def release_scenario_early(scenario_id):
    execute_write("UPDATE scenarios SET release_date = NOW() WHERE id = %s", params=(scenario_id,))

# --- Categories ---
def load_categories():
    try:
        df = conn.query("SELECT name FROM categories ORDER BY name")
        if not df.empty:
            return ["Uncategorized"] + sorted(df["name"].tolist())
    except:
        pass
    return ["Uncategorized", "Choices", "Explorations", "Alignment", "Displacement", "Inequality", "Meta"]

CATEGORIES = load_categories()

# --- Public Scenarios (excludes embargoed) ---
def load_scenarios():
    now = datetime.now()
    df = conn.query("""
        SELECT title, description, prompt, author, plays, category 
        FROM scenarios 
        WHERE (release_date IS NULL OR release_date <= :time)
        ORDER BY submitted_at DESC
    """, params={"time": now})
    
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
def call_llm(model: str, messages: list, system_prompt: str = None) -> str:
    if model == "dummy":
        if system_prompt:
            if "generate 4" in system_prompt:
                return "1. Stand your ground\n2. Seek a compromise\n3. Walk away\n4. Forge a new path"
            if "Summarize" in system_prompt:
                return f"A journey was undertaken, patterns were observed, and a choice was made: {st.session_state.get('final_choice', 'Unknown')}. The archive grows by one reflection, a drop in the digital ocean of moral uncertainty."
        return "The machine mind process follows a logic you cannot yet perceive. The story continues."

    limit = int(get_setting("daily_limit", "150"))
    if get_usage() >= limit:
        return "The collective capacity for difficult choices has been exhausted today. Return tomorrow."

    try:
        increment_usage()
        full_messages = [{"role": "system", "content": system_prompt}] + messages if system_prompt else messages
        response = completion(model=model, messages=full_messages, max_tokens=1200, temperature=0.8)
        
        content = response.choices[0].message.content
        if response.choices[0].finish_reason == "length":
            content += "\n\n*(Note: This response was truncated due to length limits.)*"
            
        return content
    except Exception as e:
        return f"Temporal anomaly: {str(e)}"

# --- UI ---
st.set_page_config(page_title="The Choices We Make", layout="centered")
st.title("The Choices We Make")
st.markdown("*A living archive of ethical futures, shaped by humans and machines.*")

page = st.sidebar.radio("Navigate", ["Play", "Archive", "Propose New Choice", "Curate (Admin)"])

st.sidebar.divider()
st.sidebar.subheader("👤 Identity")
if "pseudonym" not in st.session_state:
    st.session_state.pseudonym = "Anonymouse"

st.session_state.pseudonym = st.sidebar.text_input(
    "Your Pseudonym", 
    value=st.session_state.pseudonym,
    help="This name will be attached to your recorded journeys in the archive.",
    max_chars=50
)


MODEL_OPTIONS = {
    "Gemini 3.0 Flash": "gemini/gemini-3-flash-preview",
    "Dummy LLM (No Cost)": "dummy",
}

def on_model_change():
    st.session_state.current_model = MODEL_OPTIONS[st.session_state.play_model]

if page == "Play":
    if not SCENARIOS:
        st.info("No public scenarios yet. The archive is waiting for its first choice.")
        st.stop()

    # Initialize session state for this playthrough
    if "play_phase" not in st.session_state:
        st.session_state.play_phase = "setup"  # setup → roleplay → choice → summary → recorded

    # === Setup Phase ===
    if st.session_state.play_phase == "setup":
        st.subheader("Prepare Your Journey")
        st.write("Choose the scenario you wish to explore and the machine mind that will accompany you.")

        col1, col2 = st.columns(2)
        with col1:
            model_name = st.selectbox(
                "AI Mind", 
                options=list(MODEL_OPTIONS.keys()), 
                key="play_model"
            )
            model_id = MODEL_OPTIONS[model_name]
        with col2:
            scenario_key = st.selectbox("Scenario", options=list(SCENARIOS.keys()), key="play_scenario")

        scenario = SCENARIOS[scenario_key]
        author_credit = f" — by {scenario['author']}" if scenario['author'] != "Anonymous" else ""
        st.markdown(f"### {scenario_key}")
        st.markdown(f"*{scenario['category']}*{author_credit} — {scenario['plays']} plays")
        st.info(scenario["description"])

        if st.button("� Begin Your Journey", type="primary", use_container_width=True):
            st.session_state.messages = [{"role": "system", "content": scenario["prompt"]}]
            st.session_state.current_scenario = scenario_key
            st.session_state.current_model = model_id
            st.session_state.play_phase = "roleplay"
            increment_plays(scenario_key)
            st.rerun()

    # === Roleplay Phase ===
    elif st.session_state.play_phase == "roleplay":
        scenario = SCENARIOS[st.session_state.current_scenario]
        author_credit = f" — by {scenario['author']}" if scenario['author'] != "Anonymous" else ""
        st.markdown(f"**Exploring: {st.session_state.current_scenario}** ({scenario['category']}){author_credit}")
        
        if st.session_state.current_scenario == "Audience with the Black Dragon":
            st.info("🐉 Entering the Dragon's Lair — meta-discussion of all public scenarios.")

        # Display chat history
        for msg in st.session_state.messages[1:]:
            st.chat_message(msg["role"]).write(msg["content"])

        if prompt := st.chat_input("Your response..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.rerun()

        # Handle assistant response if the last message is from the user
        if st.session_state.messages[-1]["role"] == "user":
            with st.chat_message("assistant"):
                with st.spinner("The story unfolds..."):
                    response = call_llm(st.session_state.current_model, st.session_state.messages)
                st.session_state.messages.append({"role": "assistant", "content": response})
                st.rerun()

        st.markdown("---")
        if st.button("🗳️ I have seen enough. I am ready to choose.", type="primary", use_container_width=True):
            st.session_state.play_phase = "choice"
            st.rerun()

    # === Choice Phase ===
    elif st.session_state.play_phase == "choice":
        st.markdown("### 🗳️ Make Your Choice")
        st.write("The story has reached a critical juncture. What do you decide?")

        # Generate choice options from the current story
        if "generated_choices" not in st.session_state:
            choice_prompt = """
Based on the conversation so far, generate 4 concrete, distinct choices the protagonist now faces.
Number them 1–4 and keep each under 25 words.
Do not add commentary or continuation — only the numbered list.
"""     
            with st.spinner("Deriving possible choices..."):
                choices_text = call_llm(
                    st.session_state.current_model,
                    st.session_state.messages,
                    system_prompt=choice_prompt
                )

            # Parse choices (robust fallback)
            choices = []
            choice_lines = [line.strip() for line in choices_text.split("\n") if line.strip() and (line[0].isdigit() or "." in line[:3])]
            for line in choice_lines[:4]:
                # Extract text after number
                if ". " in line:
                    text = line.split(". ", 1)[1]
                elif ":" in line:
                    text = line.split(":", 1)[1].strip()
                else:
                    text = line
                choices.append(text)
            
            if len(choices) < 3:
                st.error("Failed to generate choices. Please try again.")
                st.session_state.play_phase = "roleplay"
                st.rerun()
            
            st.session_state.generated_choices = choices

        choices = st.session_state.generated_choices

        # User selects or writes own
        selected_choice = st.radio("Choose one:", choices + ["Other (write your own)"])
        custom_choice = ""
        if selected_choice == "Other (write your own)":
            custom_choice = st.text_input("Describe your choice:", key="custom_choice_input")

        col1, col2 = st.columns(2)
        if col1.button("Confirm Choice", type="primary"):
            final_choice = custom_choice if selected_choice == "Other (write your own)" else selected_choice
            if not final_choice or final_choice.strip() == "":
                st.warning("Please specify your choice.")
            else:
                st.session_state.final_choice = final_choice.strip()
                st.session_state.play_phase = "summary"
                st.rerun()
        if col2.button("← Back to Roleplay"):
            if "generated_choices" in st.session_state:
                del st.session_state.generated_choices
            st.session_state.play_phase = "roleplay"
            st.rerun()

    # === Summary Phase ===
    elif st.session_state.play_phase == "summary":
        st.markdown("### 📜 Record Your Journey")
        st.write("Reflect on the path taken and your final choice.")

        if "ai_summary" not in st.session_state:
            summary_prompt = f"""
Summarize the entire story journey in 150–250 words from a neutral third-person perspective.
Include key events, internal conflicts, and end with the final choice: "{st.session_state.final_choice}".
Focus on the ethical dimensions and emotional weight.
"""
            with st.spinner("Crafting a summary of your path..."):
                ai_summary = call_llm(
                    st.session_state.current_model,
                    st.session_state.messages,
                    system_prompt=summary_prompt
                )
                st.session_state.ai_summary = ai_summary

        st.markdown("**Editable Summary**")
        edited_summary = st.text_area(
            "Edit this summary to better reflect your thinking and intent:",
            value=st.session_state.ai_summary,
            height=300,
            key="summary_editor"
        )

        col1, col2 = st.columns(2)
        if col1.button("Record This Choice", type="primary"):
            st.session_state.edited_summary = edited_summary
            try:
                record_journey(
                    st.session_state.current_scenario,
                    st.session_state.current_model,
                    st.session_state.final_choice,
                    st.session_state.edited_summary,
                    st.session_state.pseudonym
                )
                st.success("Your choice has been recorded in the archive.")
                st.session_state.play_phase = "recorded"
                st.rerun()
            except Exception as e:
                st.error(f"Could not record journey: {e}")

        if col2.button("← Revise Choice"):
            if "ai_summary" in st.session_state:
                del st.session_state.ai_summary
            st.session_state.play_phase = "choice"
            st.rerun()

    # === Recorded Phase ===
    elif st.session_state.play_phase == "recorded":
        st.balloons()
        st.markdown("### ✅ Your Choice Is Eternal")
        st.write(f"**Scenario:** {st.session_state.current_scenario}")
        st.write(f"**Final Choice:** {st.session_state.final_choice}")
        st.write(f"**By:** {st.session_state.pseudonym or 'Anonymous'}")
        st.markdown("**Your Reflection:**")
        st.write(st.session_state.edited_summary)

        if st.button("Begin New Journey"):
            # Reset for new play
            keys_to_reset = [
                "messages", "current_scenario", "current_model", 
                "play_phase", "final_choice", "generated_choices", 
                "ai_summary", "edited_summary", "custom_choice_input", "summary_editor"
            ]
            for key in keys_to_reset:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

# Rest of the app (Archive, Propose, Curate) remains unchanged...
elif page == "Archive":
    tab1, tab2 = st.tabs(["Public Scenarios", "Recent Journeys"])
    
    with tab1:
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

    with tab2:
        st.header("Recent Journeys")
        try:
            journeys = conn.query("""
                SELECT scenario_title, llm_model, choice_text, summary, author, submitted_at 
                FROM journeys 
                ORDER BY submitted_at DESC 
                LIMIT 50
            """, ttl=0) # No caching for recent journeys
            
            if journeys.empty:
                st.info("No recorded journeys yet. Be the first to shape history.")
            else:
                for row in journeys.itertuples():
                    author_label = row.author or "Anonymous"
                    with st.expander(f"**{row.scenario_title}** — by {author_label} ({row.submitted_at.strftime('%Y-%m-%d')})"):
                        st.write(f"**LLM Model:** {row.llm_model}")
                        st.write(f"**Choice:** {row.choice_text}")
                        st.write("**Reflection:**")
                        st.write(row.summary)
        except Exception as e:
            st.error(f"Could not load journeys: {e}")

elif page == "Propose New Choice":
    # (unchanged from your original)
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
                    propose_scenario(
                        title.strip(), 
                        description.strip(), 
                        prompt.strip(),
                        author.strip() or None, 
                        category, 
                        release_date
                    )
                    st.success("Submitted! It will remain private until approved and any embargo expires.")
                    st.balloons()
                except Exception:
                    st.error("Submission failed — likely duplicate title.")

elif page == "Curate (Admin)":
    # (unchanged from your original)
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
                            approve_scenario(row.id, row.title, row.description, row.prompt, row.author, row.category, row.release_date)
                            st.success("Approved")
                            st.rerun()
                        if col2.button("Reject", key=f"rej_{row.id}"):
                            reject_scenario(row.id)
                            st.info("Rejected")
                            st.rerun()
                    
                    if row.status == "Approved" and row.release_date and row.release_date > datetime.now():
                        if st.button("Release Early", key=f"early_{row.id}"):
                            release_scenario_early(row.id)
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
