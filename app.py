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
from utils.ui import (
    render_landing_page, render_play_page, render_archive_page,
    render_propose_page, render_curate_page, MODEL_OPTIONS,
    render_cat_game
)


CATEGORIES = load_categories()
SCENARIOS = load_scenarios()

# --- UI ---
st.set_page_config(page_title="The Choices We Make", layout="centered")
st.title("The Choices We Make")
st.markdown("*A social experiment in recording choices for difficult problems*")

# Navigation State Management
nav_options = ["How it Works", "Play", "Archive", "Propose New Choice", "Curate (Admin)"]

if "current_page" not in st.session_state:
    st.session_state.current_page = "How it Works"

def on_nav_change():
    st.session_state.current_page = st.session_state.nav_radio

# Sidebar Navigation
st.sidebar.subheader("👤 Navigation")
st.sidebar.radio(
    "Go to", 
    nav_options, 
    index=nav_options.index(st.session_state.current_page) if st.session_state.current_page in nav_options else 0,
    key="nav_radio",
    on_change=on_nav_change
)

def on_model_change():
    st.session_state.current_model = MODEL_OPTIONS[st.session_state.play_model]

# Routing
# Secret pages first
if st.session_state.current_page == "CatGame":
    render_cat_game()

# Main pages
elif st.session_state.current_page == "How it Works":
    render_landing_page()

elif st.session_state.current_page == "Play":
    render_play_page(SCENARIOS)

elif st.session_state.current_page == "Archive":
    render_archive_page()

elif st.session_state.current_page == "Propose New Choice":
    render_propose_page(CATEGORIES)

elif st.session_state.current_page == "Curate (Admin)":
    render_curate_page(CATEGORIES)
