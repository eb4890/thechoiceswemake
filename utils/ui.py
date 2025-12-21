import streamlit as st
import utils.services as services
from utils.llm import call_llm

MODEL_OPTIONS = {
    "Gemini 3.0 Flash": "gemini/gemini-3-flash-preview",
    "Dummy LLM (No Cost)": "dummy",
}

def render_landing_page():
    st.header("How to Use This Site")
    
    st.markdown("""
We're experimenting with how people can practice navigating impossible choices. We don't know exactly what helps yet—that's what we're learning together.

**Here's what seems to work so far:**

**Talk, don't click.** When asked what you'd do, just tell it. Type naturally. The scenario responds to your actual words, not preset options.

**Try scenarios more than once.** Your thinking shifts between attempts. Play with different approaches. See what changes.

**Decide when you're ready.** Take your time. Notice what makes it hard. There's no timer.

**Look at others' reasoning afterwards.** See how different people weighted the same tradeoffs. Not to find who's "right"—just to see the range of ways people think about these problems.

**This is training, but it should be interesting.** If a scenario feels like a chore, try a different one. Some will grab you, some won't. That's fine.

**We're building this together.** Your choices and reflections help us understand what actually helps people practice better judgment. If something's confusing or feels off, that's useful to know.

The goal: practice thinking about coordination problems and impossible tradeoffs before you face them for real. Whether it works? We're finding out.
""")
    
    if st.button("🚀 Ready to Begin"):
        st.session_state.current_page = "Play"
        st.rerun()

def render_sidebar_info():
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

    # --- Footer Usage ---
    limit = int(services.get_setting("daily_limit", "150"))
    used = services.get_usage()
    st.sidebar.metric("Global Choices Today", f"{used}/{limit}")
    if used >= limit:
        st.sidebar.warning("Daily limit reached — return tomorrow.")
    else:
        st.sidebar.progress(used / limit)

@st.fragment
def render_setup_fragment(scenarios):
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
        scenario_key = st.selectbox("Scenario", options=list(scenarios.keys()), key="play_scenario")

    scenario = scenarios[scenario_key]
    author_credit = f" — by {scenario['author']}" if scenario['author'] != "Anonymous" else ""
    st.markdown(f"### {scenario_key}")
    st.markdown(f"*{scenario['category']}*{author_credit} — {scenario['plays']} plays")
    st.info(scenario["description"])
    
    prompt_prefix = """
CRITICAL INTERACTION STYLE:
- Never present A/B/C/D options
- Never list "you could do X, Y, or Z"
- Ask open questions and let the user respond freely
- React to what they actually say/do
- If they're uncertain, ask clarifying questions
- Draw out their reasoning through dialogue
- Let choices emerge from conversation, not menu selection

Example:
WRONG: "What do you do? A) Tell them B) Hide it C) Run away"
RIGHT: "The parrot is still talking. What do you do?" 
       [User responds naturally, you react to their specific choice]
Also add:
PACING:
- Keep responses short (2-4 sentences usually)
- Present one moment/beat at a time
- Wait for user response before continuing
- Don't rush through the scenario
- Let tension build naturally
- Allow pauses and uncertainty
"""
    if st.button("🚀 Begin Your Journey", type="primary", use_container_width=True):
        st.session_state.messages = [{"role": "system", "content": prompt_prefix + scenario["prompt"]}]
        st.session_state.current_scenario = scenario_key
        st.session_state.current_model = model_id
        st.session_state.play_phase = "roleplay"
        services.increment_plays(scenario_key)
        st.rerun()

@st.fragment
def render_roleplay_fragment():
    # Use a container to allow clearing or updating sections
    chat_container = st.container()
    
    # Display chat history (except system prompt)
    with chat_container:
        for msg in st.session_state.messages[1:]:
            st.chat_message(msg["role"]).write(msg["content"])

    # Input handling
    is_waiting_for_llm = st.session_state.messages[-1]["role"] == "user"

    if not is_waiting_for_llm:
        if prompt := st.chat_input("Your response..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.rerun() # Local rerun within fragment

    # Handle assistant response
    if is_waiting_for_llm:
        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("The story unfolds..."):
                    response = call_llm(st.session_state.current_model, st.session_state.messages)
                st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun() # Local rerun to show response and clear user input state

    st.markdown("---")
    # This button triggers a full page update to change phase
    if st.button("🗳️ I have seen enough. I am ready to choose.", type="primary", use_container_width=True):
        st.session_state.play_phase = "choice"
        st.rerun(scope="app") # Transition phase requires full app rerun

@st.fragment
def render_choice_fragment():
    st.markdown("### 🗳️ Make Your Choice")
    st.write("The story has reached a critical juncture. What do you decide?")

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

        choices = []
        if choices_text:
            choice_lines = [line.strip() for line in choices_text.split("\n") if line.strip() and (line[0].isdigit() or "." in line[:3])]
            for line in choice_lines[:4]:
                if ". " in line:
                    text = line.split(". ", 1)[1]
                elif ":" in line:
                    text = line.split(":", 1)[1].strip()
                else:
                    text = line
                choices.append(text)    
        
        st.session_state.generated_choices = choices

    choices = st.session_state.generated_choices
    selected_choice = st.radio("Choose one:", choices + ["Other (write your own)"], key="choice_radio")
    
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
            st.rerun(scope="app")
    
    if col2.button("← Back to Roleplay"):
        if "generated_choices" in st.session_state:
            del st.session_state.generated_choices
        st.session_state.play_phase = "roleplay"
        st.rerun(scope="app")

@st.fragment
def render_summary_fragment():
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
            services.record_journey(
                st.session_state.current_scenario,
                st.session_state.current_model,
                st.session_state.final_choice,
                st.session_state.edited_summary,
                st.session_state.pseudonym
            )
            st.session_state.play_phase = "recorded"
            st.rerun(scope="app")
        except Exception as e:
            st.error(f"Could not record journey: {e}")

    if col2.button("← Revise Choice"):
        if "ai_summary" in st.session_state:
            del st.session_state.ai_summary
        st.session_state.play_phase = "choice"
        st.rerun(scope="app")

def render_play_page(scenarios):
    render_sidebar_info()
    if not scenarios:
        st.info("No public scenarios yet. The archive is waiting for its first choice.")
        return

    if "play_phase" not in st.session_state:
        st.session_state.play_phase = "setup"

    # Route to fragments based on phase
    if st.session_state.play_phase == "setup":
        render_setup_fragment(scenarios)
    elif st.session_state.play_phase == "roleplay":
        render_roleplay_fragment()
    elif st.session_state.play_phase == "choice":
        render_choice_fragment()
    elif st.session_state.play_phase == "summary":
        render_summary_fragment()
    elif st.session_state.play_phase == "recorded":
        st.balloons()
        st.markdown("### ✅ Your Choice Is Eternal")
        st.write(f"**Scenario:** {st.session_state.current_scenario}")
        st.write(f"**Final Choice:** {st.session_state.final_choice}")
        st.write(f"**By:** {st.session_state.pseudonym or 'Anonymous'}")
        st.markdown("**Your Reflection:**")
        st.write(st.session_state.edited_summary)

        if st.button("Begin New Journey", type="primary"):
            keys_to_reset = [
                "messages", "current_scenario", "current_model", 
                "play_phase", "final_choice", "generated_choices", 
                "ai_summary", "edited_summary", "custom_choice_input", "summary_editor"
            ]
            for key in keys_to_reset:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
