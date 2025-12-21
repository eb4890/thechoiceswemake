from litellm import completion
import streamlit as st
from utils.services import get_setting, increment_usage

def call_llm(model: str, messages: list, system_prompt: str = None) -> str:
    if model == "dummy":
        if system_prompt:
            if "generate 4" in system_prompt:
                return "1. Stand your ground\n2. Seek a compromise\n3. Walk away\n4. Forge a new path"
            if "Summarize" in system_prompt:
                return f"A journey was undertaken, patterns were observed, and a choice was made: {st.session_state.get('final_choice', 'Unknown')}. The archive grows by one reflection, a drop in the digital ocean of moral uncertainty."
        return "The machine mind process follows a logic you cannot yet perceive. The story continues."

    limit = int(get_setting("daily_limit", "150"))
    if int(get_setting("current_count", "0")) >= limit: # Double check usage directly to avoid circular reset if needed, but services.get_usage() is safer usually.
        # However, to avoid circular imports if services uses llm, we should be careful.
        # Actually, services doesn't use llm. llm uses services.
        pass

    import utils.services as services
    if services.get_usage() >= limit:
        return "The collective capacity for difficult choices has been exhausted today. Return tomorrow."

    try:
        services.increment_usage()
        full_messages = [{"role": "system", "content": system_prompt}] + messages if system_prompt else messages
        response = completion(model=model, messages=full_messages, max_tokens=1200, temperature=0.8)
        
        content = response.choices[0].message.content
        if response.choices[0].finish_reason == "length":
            content += "\n\n*(Note: This response was truncated due to length limits.)*"
            
        return content
    except Exception as e:
        return f"Temporal anomaly: {str(e)}"
