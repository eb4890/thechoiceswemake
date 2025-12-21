import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import hashlib

from utils.db import conn
from utils.services import (
    get_usage, increment_usage, increment_plays, record_journey,
    propose_scenario, approve_scenario, reject_scenario,
    release_scenario_early, load_categories, load_scenarios,
    get_setting
)
from utils.llm import call_llm
from utils.ui import render_landing_page, render_play_page, MODEL_OPTIONS


CATEGORIES = load_categories()
SCENARIOS = load_scenarios()

# --- UI ---
st.set_page_config(page_title="The Choices We Make", layout="centered")
st.title("The Choices We Make")
st.markdown("*Practicing on challenging problems for individual and social improvement*")

# Navigation
nav_options = ["How it Works", "Play", "Archive", "Propose New Choice", "Curate (Admin)"]

if "current_page" not in st.session_state:
    st.session_state.current_page = "How it Works"

try:
    default_index = nav_options.index(st.session_state.current_page)
except ValueError:
    default_index = 0

page = st.sidebar.radio("Navigate", nav_options, index=default_index)
st.session_state.current_page = page

st.sidebar.subheader("👤 Navigation")
# Moved Identity and Usage status to Play-only page logic in utils/ui.py


def on_model_change():
    st.session_state.current_model = MODEL_OPTIONS[st.session_state.play_model]

if page == "How it Works":
    render_landing_page()

elif page == "Play":
    render_play_page(SCENARIOS)

# Rest of the app (Archive, Propose, Curate) remains unchanged...
elif page == "Archive":
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

# --- Footer Moved to render_sidebar_info in utils/ui.py ---
