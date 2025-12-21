from datetime import datetime
from dateutil.relativedelta import relativedelta
from utils.db import conn, execute_write

def get_setting(key: str, default: str = "0") -> str:
    df = conn.query("SELECT value FROM settings WHERE key = :setting LIMIT 1", params={"setting": key}, ttl=10)
    return df["value"].iloc[0] if not df.empty else default

def set_setting(key: str, value: str):
    execute_write(
        "INSERT INTO settings (key, value) VALUES ( %s , %s ) "
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

def load_categories():
    try:
        df = conn.query("SELECT name FROM categories ORDER BY name")
        if not df.empty:
            return ["Uncategorized"] + sorted(df["name"].tolist())
    except:
        pass
    return ["Uncategorized", "Choices", "Explorations", "Alignment", "Displacement", "Inequality", "Meta"]

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
