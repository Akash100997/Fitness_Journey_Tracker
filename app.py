import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
import io
import time
from PIL import Image

# Setup page config for mobile-first responsive layout
st.set_page_config(
    page_title="Robur Fit Companion",
    page_icon="🏃‍♂️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Custom Styling for Gym Theme & Mobile Cards
st.markdown("""
<style>
    /* Metric Card Styling */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-left: 5px solid #ff4b4b;
        color: #f8fafc;
        padding: 16px;
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2), 0 2px 4px -2px rgba(0,0,0,0.2);
        margin-bottom: 15px;
    }
    .metric-card h4 {
        margin: 0 0 8px 0;
        font-size: 0.95rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-card h2 {
        margin: 0 0 6px 0;
        font-size: 1.75rem;
        font-weight: 700;
        color: #ffffff;
    }
    .metric-card p {
        margin: 0;
        font-size: 0.9rem;
        color: #cbd5e1;
    }
    .kpi-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 600;
        background-color: #334155;
        color: #38bdf8;
    }
    .exercise-header {
        background-color: #1e293b;
        color: white;
        padding: 10px 14px;
        border-radius: 6px;
        margin-top: 15px;
        font-weight: bold;
    }
    /* Mobile Touch Tweaks */
    div.stButton > button:first-child {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ─── DATABASE SERVICES (Supports Local SQLite & Turso Cloud Serverless SQLite) ───
DB_FILE = "robur_fit.db"

class TursoCompatCursor:
    def __init__(self, client):
        self.client = client
        self._result = None
        self._row_idx = 0

    def execute(self, sql, params=None):
        if params is None:
            self._result = self.client.execute(sql)
        else:
            p = list(params) if isinstance(params, (list, tuple)) else params
            self._result = self.client.execute(sql, p)
        self._row_idx = 0
        return self

    def fetchone(self):
        if not self._result or not self._result.rows or self._row_idx >= len(self._result.rows):
            return None
        row = self._result.rows[self._row_idx]
        self._row_idx += 1
        return row

    def fetchall(self):
        if not self._result or not self._result.rows:
            return []
        rows = self._result.rows[self._row_idx:]
        self._row_idx = len(self._result.rows)
        return rows

    def close(self):
        pass

    @property
    def description(self):
        if not self._result or not self._result.columns:
            return None
        return [(col, None, None, None, None, None, None) for col in self._result.columns]

class TursoCompatConnection:
    def __init__(self, client):
        self.client = client

    def cursor(self):
        return TursoCompatCursor(self.client)

    def execute(self, sql, params=None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self):
        pass

    def close(self):
        self.client.close()

def get_db_connection():
    # If Turso Cloud database credentials exist in secrets or environment, connect to Turso
    turso_url = os.environ.get("TURSO_DATABASE_URL", "")
    turso_token = os.environ.get("TURSO_AUTH_TOKEN", "")
    try:
        if hasattr(st, "secrets"):
            turso_url = st.secrets.get("TURSO_DATABASE_URL", turso_url)
            turso_token = st.secrets.get("TURSO_AUTH_TOKEN", turso_token)
    except Exception:
        pass

    if turso_url and turso_token:
        try:
            import libsql_client
            clean_url = turso_url.strip()
            if clean_url.startswith("libsql://"):
                clean_url = "https://" + clean_url[len("libsql://"):]
            client = libsql_client.create_client_sync(url=clean_url, auth_token=turso_token.strip())
            return TursoCompatConnection(client)
        except Exception as e:
            st.error(f"Turso Cloud connection warning: {e}. Falling back to local SQLite.")

    # Local SQLite fallback
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Profile Baselines (Accuniq details hardcoded as default profile)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profile (
        id INTEGER PRIMARY KEY,
        actual_age INTEGER DEFAULT 28,
        target_weight REAL DEFAULT 66.9,
        starting_weight REAL DEFAULT 77.8,
        bmr_kcal REAL DEFAULT 1562.0,
        tdee_kcal REAL DEFAULT 2405.0,
        target_calories REAL DEFAULT 1850.0,
        target_protein REAL DEFAULT 110.0,
        water_target_liters REAL DEFAULT 3.8,
        muscle_mass_kg REAL DEFAULT 30.4,
        starting_fat_kg REAL DEFAULT 22.6,
        target_fat_loss_kg REAL DEFAULT 10.9
    )""")
    
    cursor.execute("SELECT COUNT(*) FROM profile")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO profile (id) VALUES (1)")
        
    # 2. Daily Weight logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS weight_logs (
        date TEXT PRIMARY KEY,
        weight REAL NOT NULL
    )""")
    
    # 3. Workout logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workout_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        day_type TEXT NOT NULL,
        exercise_name TEXT NOT NULL,
        set_number INTEGER NOT NULL,
        weight_kg REAL NOT NULL,
        reps INTEGER NOT NULL
    )""")
    
    # 4. Nutrition logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nutrition_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        meal_type TEXT NOT NULL,
        food_description TEXT NOT NULL,
        calories REAL NOT NULL,
        protein REAL NOT NULL,
        carbs REAL NOT NULL,
        fat REAL NOT NULL
    )""")
    
    # 5. Water intake logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS water_logs (
        date TEXT PRIMARY KEY,
        water_ml INTEGER DEFAULT 0
    )""")
    
    # Seed initial weight log to show trend if empty
    cursor.execute("SELECT COUNT(*) FROM weight_logs")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR REPLACE INTO weight_logs (date, weight) VALUES (?, ?)", ("2026-04-01", 77.1))
        cursor.execute("INSERT OR REPLACE INTO weight_logs (date, weight) VALUES (?, ?)", ("2026-09-03", 77.8))

    conn.commit()
    conn.close()

def get_water_log(date_str):
    conn = get_db_connection()
    row = conn.execute("SELECT water_ml FROM water_logs WHERE date = ?", (date_str,)).fetchone()
    conn.close()
    return int(row['water_ml']) if row else 0

def update_water_log(date_str, delta_ml):
    conn = get_db_connection()
    current = conn.execute("SELECT water_ml FROM water_logs WHERE date = ?", (date_str,)).fetchone()
    current_val = int(current['water_ml']) if current else 0
    new_val = max(0, current_val + delta_ml)
    conn.execute("INSERT OR REPLACE INTO water_logs (date, water_ml) VALUES (?, ?)", (date_str, new_val))
    conn.commit()
    conn.close()
    return new_val

init_db()

# ─── GEMINI AI NUTRITION SERVICE ───
CURATED_MODELS = [
    "gemini-3.5-flash-lite (Ultra Fast & High Quota — Recommended)",
    "gemini-3.5-flash (Balanced & Detailed)",
    "gemini-flash-lite-latest (Fast Lite)",
    "gemini-3.8-flash (Preview — Low Daily Quota)",
    "gemini-3.7-flash (Alternative Flash)"
]

def analyze_meal_image(api_key, image, model_name="gemini-3.5-flash-lite"):
    prompt = """
    You are an expert sports nutritionist AI. Analyze this meal photo.
    Estimate the macronutrient breakdown. The user is a Hindu eggetarian (no meat/fish, skips eggs on Saturday, relies on lentils, paneer, tofu, soya chunks, eggs on weekdays, curd, roti, rice).
    
    Output ONLY a valid JSON object matching this schema:
    {
      "food_description": "Brief description of the food items",
      "calories": 450.0,
      "protein": 25.5,
      "carbs": 45.0,
      "fat": 12.0
    }
    Output numeric values only. Be realistic with portion sizes.
    """
    
    clean_model = model_name.split(" ")[0].replace("models/", "").strip()
    
    # ── SPEED OPTIMIZATION 1: Local Image Downscaling ──
    # High-res phone photos (10MB+) cause long upload delays.
    # Downscaling to 1024px preserves full AI accuracy while reducing payload to ~150KB (10x faster network transfer).
    img_optimized = image.copy()
    if hasattr(img_optimized, "mode") and img_optimized.mode in ("RGBA", "P"):
        img_optimized = img_optimized.convert("RGB")
        
    max_dimension = 1024
    if max(img_optimized.size) > max_dimension:
        img_optimized.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        
    # Priority order of models to try
    candidates = [clean_model]
    for m in [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-3.7-flash"
    ]:
        if m not in candidates:
            candidates.append(m)
            
    last_err = None
    for cand in candidates:
        try:
            text_response = None
            # 1. Try modern official google-genai SDK
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                
                # Direct Low-Latency Token Generation with ample token budget
                response = client.models.generate_content(
                    model=cand,
                    contents=[img_optimized, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=1000,
                        temperature=0.2
                    )
                )
                text_response = response.text.strip()
            except Exception as e_genai:
                err_str = str(e_genai)
                # If 429 quota exhausted on this model, skip legacy retry for same model
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    last_err = e_genai
                    continue
                    
                # 2. Fallback to legacy google.generativeai SDK
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=api_key)
                model = legacy_genai.GenerativeModel(
                    cand,
                    generation_config={
                        "response_mime_type": "application/json",
                        "max_output_tokens": 1000,
                        "temperature": 0.2
                    }
                )
                response = model.generate_content([prompt, img_optimized])
                text_response = response.text.strip()
                
            if not text_response:
                continue
                
            if text_response.startswith("```"):
                text_response = text_response.split("```")[1]
                if text_response.startswith("json"):
                    text_response = text_response[4:]
                    
            parsed_data = json.loads(text_response.strip())
            parsed_data["model_used"] = cand
            return parsed_data
        except Exception as e:
            last_err = e
            continue
            
    raise RuntimeError(f"Could not analyze meal. Last error: {last_err}")

def analyze_meal_text(api_key, food_text, model_name="gemini-3.5-flash-lite"):
    prompt = f"""
    You are an expert sports nutritionist AI. Analyze this meal or food item description:
    "{food_text}"
    
    Estimate the macronutrient breakdown. The user is a Hindu eggetarian (no meat/fish, skips eggs on Saturday, relies on lentils, paneer, tofu, soya chunks, eggs on weekdays, curd, roti, rice).
    
    Output ONLY a valid JSON object matching this schema:
    {{
      "food_description": "Clean, descriptive name of the food item or meal with portions (e.g. One Cup of Coffee with Light Sugar)",
      "calories": 45.0,
      "protein": 1.5,
      "carbs": 7.0,
      "fat": 1.0
    }}
    Output numeric values only. Be realistic with ingredients, preparation styles, and portion sizes implied by the user's description.
    """
    
    clean_model = model_name.split(" ")[0].replace("models/", "").strip()
    
    # Priority order of models to try
    candidates = [clean_model]
    for m in [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-3.7-flash"
    ]:
        if m not in candidates:
            candidates.append(m)
            
    last_err = None
    for cand in candidates:
        try:
            text_response = None
            # 1. Try modern official google-genai SDK
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                
                response = client.models.generate_content(
                    model=cand,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=1000,
                        temperature=0.2
                    )
                )
                text_response = response.text.strip()
            except Exception as e_genai:
                err_str = str(e_genai)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    last_err = e_genai
                    continue
                    
                # 2. Fallback to legacy google.generativeai SDK
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=api_key)
                model = legacy_genai.GenerativeModel(
                    cand,
                    generation_config={
                        "response_mime_type": "application/json",
                        "max_output_tokens": 1000,
                        "temperature": 0.2
                    }
                )
                response = model.generate_content(prompt)
                text_response = response.text.strip()
                
            if not text_response:
                continue
                
            if text_response.startswith("```"):
                text_response = text_response.split("```")[1]
                if text_response.startswith("json"):
                    text_response = text_response[4:]
                    
            parsed_data = json.loads(text_response.strip())
            parsed_data["model_used"] = cand
            return parsed_data
        except Exception as e:
            last_err = e
            continue
            
    raise RuntimeError(f"Could not analyze meal text. Last error: {last_err}")


# ─── APP SIDEBAR (Settings & AI Key) ───
st.sidebar.title("⚙️ App Settings")

# Check for environment key or secret fallback
default_key = os.environ.get("GEMINI_API_KEY", "")
try:
    if not default_key and hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        default_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    pass

api_key = st.sidebar.text_input("Gemini API Key", value=default_key, type="password", help="Get free key from Google AI Studio (aistudio.google.com)")

model_choice = st.sidebar.selectbox("Gemini AI Model", CURATED_MODELS, index=0)

if api_key:
    st.sidebar.success(f"API Key Ready ({model_choice.split(' ')[0]})")
else:
    st.sidebar.warning("Enter Gemini API Key to enable AI Meal Scanning.")

# Profile settings expander
with st.sidebar.expander("👤 Edit Profile Baselines"):
    conn = get_db_connection()
    prof_data = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    conn.close()
    
    new_cal_target = st.number_input("Target Calories (kcal)", value=float(prof_data['target_calories']), step=50.0)
    new_prot_target = st.number_input("Target Protein (g)", value=float(prof_data['target_protein']), step=5.0)
    new_weight_target = st.number_input("Target Weight (kg)", value=float(prof_data['target_weight']), step=0.1)
    
    if st.button("Save Profile Settings"):
        conn = get_db_connection()
        conn.execute(
            "UPDATE profile SET target_calories = ?, target_protein = ?, target_weight = ? WHERE id = 1",
            (new_cal_target, new_prot_target, new_weight_target)
        )
        conn.commit()
        conn.close()
        st.success("Profile targets updated!")
        st.rerun()


# ─── MAIN APP TABS ───
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "⚖️ Weight Tracker", "🏋️ Workout Log", "🥗 AI Nutrition"])

# ──────────────────────────────────────────
# TAB 1: DASHBOARD OVERVIEW
# ──────────────────────────────────────────
with tab1:
    st.title("🏃‍♂️ Robur Fit Dashboard")
    
    conn = get_db_connection()
    profile = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    nutrition_today = conn.execute(
        "SELECT COALESCE(SUM(calories), 0) as cal, COALESCE(SUM(protein), 0) as prot, COALESCE(SUM(carbs), 0) as carbs, COALESCE(SUM(fat), 0) as fat FROM nutrition_logs WHERE date = ?", 
        (today_str,)
    ).fetchone()
    
    latest_weight_row = conn.execute("SELECT weight, date FROM weight_logs ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    
    cal_eaten = float(nutrition_today['cal'])
    prot_eaten = float(nutrition_today['prot'])
    carbs_eaten = float(nutrition_today['carbs'])
    fat_eaten = float(nutrition_today['fat'])
    
    target_cal = float(profile['target_calories'])
    target_prot = float(profile['target_protein'])
    tdee = float(profile['tdee_kcal'])
    net_deficit = tdee - cal_eaten
    target_deficit = tdee - target_cal
    
    # Core Baseline Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        current_w = f"{latest_weight_row['weight']} kg" if latest_weight_row else "77.8 kg"
        st.metric("Current Weight", current_w, delta=f"Goal: {profile['target_weight']} kg")
    with col2:
        st.metric("Muscle Mass", f"{profile['muscle_mass_kg']} kg", delta="Accuniq Baseline")
    with col3:
        st.metric("Fat Loss Target", f"-{profile['target_fat_loss_kg']} kg", delta="Target")
        
    st.write("---")
    
    # ─── ENERGY BALANCE & NET DEFICIT ───
    st.subheader("🔥 Fat Loss Energy Balance & Net Deficit")
    col_def1, col_def2 = st.columns([1.5, 1])
    with col_def1:
        deficit_color = "#22c55e" if net_deficit >= 400 else ("#f59e0b" if net_deficit > 0 else "#ef4444")
        deficit_status = "🔥 Optimal Fat Burning Zone" if net_deficit >= 400 else ("⚠️ Modest Deficit" if net_deficit > 0 else "🚨 In Calorie Surplus")
        st.markdown(f"""
        <div class="metric-card" style="border-left-color: {deficit_color};">
            <h4>Live Net Deficit (TDEE: {tdee:.0f} kcal)</h4>
            <h2 style="color: {deficit_color};">{net_deficit:+.0f} kcal</h2>
            <p><strong>{deficit_status}</strong> (Target Deficit: ~{target_deficit:.0f} kcal/day)</p>
        </div>
        """, unsafe_allow_html=True)
    with col_def2:
        st.markdown(f"""
        <div style="background-color: #1e293b; padding: 16px; border-radius: 8px; color: white; height: 100%; display: flex; flex-direction: column; justify-content: center;">
            <p style="margin: 0 0 6px 0; color: #94a3b8; font-size: 0.85rem; font-weight: bold;">CALORIC BREAKDOWN</p>
            <div style="font-size: 0.95rem; line-height: 1.6;">
                • <strong>Eaten:</strong> {cal_eaten:.0f} kcal<br>
                • <strong>Target:</strong> {target_cal:.0f} kcal<br>
                • <strong>Remaining:</strong> {max(0.0, target_cal - cal_eaten):.0f} kcal
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Daily Progress Indicators
    st.subheader("🎯 Today's Targets")
    col_c, col_p = st.columns(2)
    with col_c:
        cal_left = max(0.0, profile['target_calories'] - cal_eaten)
        cal_pct = min(1.0, cal_eaten / max(1.0, profile['target_calories']))
        st.markdown(f"""
        <div class="metric-card">
            <h4>Calories Budget</h4>
            <h2>{cal_eaten:.0f} / {profile['target_calories']:.0f} kcal</h2>
            <p><strong>{cal_left:.0f} kcal</strong> remaining</p>
        </div>
        """, unsafe_allow_html=True)
        st.progress(cal_pct)
        
    with col_p:
        prot_left = max(0.0, profile['target_protein'] - prot_eaten)
        prot_pct = min(1.0, prot_eaten / max(1.0, profile['target_protein']))
        st.markdown(f"""
        <div class="metric-card">
            <h4>Protein Target</h4>
            <h2>{prot_eaten:.1f} / {profile['target_protein']:.0f} g</h2>
            <p><strong>{prot_left:.1f} g</strong> remaining</p>
        </div>
        """, unsafe_allow_html=True)
        st.progress(prot_pct)

    # Carbs & Fats Row
    col_carb_card, col_fat_card = st.columns(2)
    with col_carb_card:
        st.markdown(f"""
        <div style="background-color: #1e293b; border-left: 5px solid #fbbf24; padding: 14px; border-radius: 8px; color: white;">
            <span style="color: #94a3b8; font-size: 0.85rem; text-transform: uppercase;">Carbohydrates Logged</span>
            <h3 style="margin: 4px 0; color: #fbbf24; font-size: 1.5rem;">{carbs_eaten:.1f} g</h3>
            <p style="margin: 0; color: #cbd5e1; font-size: 0.85rem;">Energy supply ({carbs_eaten * 4:.0f} kcal)</p>
        </div>
        """, unsafe_allow_html=True)
    with col_fat_card:
        st.markdown(f"""
        <div style="background-color: #1e293b; border-left: 5px solid #f43f5e; padding: 14px; border-radius: 8px; color: white;">
            <span style="color: #94a3b8; font-size: 0.85rem; text-transform: uppercase;">Dietary Fats Logged</span>
            <h3 style="margin: 4px 0; color: #f43f5e; font-size: 1.5rem;">{fat_eaten:.1f} g</h3>
            <p style="margin: 0; color: #cbd5e1; font-size: 0.85rem;">Hormone balance ({fat_eaten * 9:.0f} kcal)</p>
        </div>
        """, unsafe_allow_html=True)

    # Macro Split Percentage Bar if food logged
    total_macro_cals = (prot_eaten * 4) + (carbs_eaten * 4) + (fat_eaten * 9)
    if total_macro_cals > 0:
        pct_p = (prot_eaten * 4) / total_macro_cals * 100
        pct_c = (carbs_eaten * 4) / total_macro_cals * 100
        pct_f = (fat_eaten * 9) / total_macro_cals * 100
        st.write("")
        st.markdown(f"""
        <div style="display: flex; gap: 8px; align-items: center; justify-content: space-around; background: #0f172a; padding: 10px; border-radius: 8px; font-size: 0.85rem; border: 1px solid #334155;">
            <span style="color: #38bdf8; font-weight: 600;">🥩 Protein: {pct_p:.0f}%</span>
            <span style="color: #fbbf24; font-weight: 600;">🍞 Carbs: {pct_c:.0f}%</span>
            <span style="color: #f43f5e; font-weight: 600;">🥑 Fat: {pct_f:.0f}%</span>
        </div>
        """, unsafe_allow_html=True)

    # ─── INTERACTIVE WATER INTAKE TRACKER ───
    st.write("---")
    st.subheader("💧 Daily Water Intake Tracker")
    target_water_ml = int(profile['water_target_liters'] * 1000)
    water_today = get_water_log(today_str)
    water_pct = min(1.0, water_today / max(1, target_water_ml))
    water_remaining_ml = max(0, target_water_ml - water_today)
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #0c4a6e 0%, #082f49 100%); border-left: 5px solid #38bdf8; padding: 16px; border-radius: 8px; color: white; margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h4 style="margin: 0; color: #7dd3fc; text-transform: uppercase; font-size: 0.9rem;">Hydration Goal</h4>
                <h2 style="margin: 4px 0; font-size: 1.8rem; font-weight: 700;">{water_today:,} / {target_water_ml:,} ml</h2>
            </div>
            <div style="text-align: right;">
                <span style="background: #0369a1; padding: 6px 12px; border-radius: 9999px; font-size: 0.9rem; font-weight: 700;">
                    {water_pct * 100:.0f}%
                </span>
                <p style="margin: 6px 0 0 0; font-size: 0.85rem; color: #bae6fd;">{water_remaining_ml:,} ml remaining</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.progress(water_pct)
    
    # Quick Tap Water Buttons
    col_w250, col_w500, col_w1000, col_wundo = st.columns(4)
    with col_w250:
        if st.button("💧 +250ml", key="btn_w250", help="Glass of water"):
            new_w = update_water_log(today_str, 250)
            st.toast(f"Logged +250ml water! ({new_w:,} ml total) 💧")
            st.rerun()
    with col_w500:
        if st.button("🍶 +500ml", key="btn_w500", help="Water bottle"):
            new_w = update_water_log(today_str, 500)
            st.toast(f"Logged +500ml water! ({new_w:,} ml total) 🍶")
            st.rerun()
    with col_w1000:
        if st.button("🧊 +1.0L", key="btn_w1000", help="Large shaker"):
            new_w = update_water_log(today_str, 1000)
            st.toast(f"Logged +1,000ml water! ({new_w:,} ml total) 🧊")
            st.rerun()
    with col_wundo:
        if st.button("↩️ -250ml", key="btn_wundo", help="Undo / remove 250ml"):
            new_w = update_water_log(today_str, -250)
            st.toast(f"Removed 250ml water. ({new_w:,} ml total)")
            st.rerun()

    # 12-Week Countdown
    st.write("---")
    start_date = datetime(2026, 9, 3)
    today_dt = datetime.now()
    days_passed = max(0, (today_dt - start_date).days)
    weeks_passed = days_passed // 7
    weeks_remaining = max(0, 12 - weeks_passed)
    
    st.info(f"📆 **12-Week Metabolic Reset Countdown**: You are in **Week {weeks_passed + 1}** (Day {days_passed + 1}). **{weeks_remaining} weeks** remaining to hit your 66.9 kg target!")
    
    # Quick Action Summary Cards
    is_sat = datetime.now().weekday() == 5
    sat_msg = "🕉️ **Saturday Egg-Free Mode active** (Prioritize soya, paneer, tofu & lentils)." if is_sat else "🍳 **Egg-friendly Weekday active** (Boiled eggs, omelettes, paneer to reach 110g protein)."
    st.markdown(f"""
    <div style="background-color: #1e293b; padding: 12px; border-radius: 8px; color: white; border: 1px solid #334155;">
        <strong>🥗 Diet Protocol:</strong> {sat_msg}<br>
        <strong>🎯 Accuniq Baseline Targets:</strong> BMR: {profile['bmr_kcal']:.0f} kcal | TDEE: {tdee:.0f} kcal | Fat Control: 22.6 kg → 11.7 kg
    </div>
    """, unsafe_allow_html=True)


# ──────────────────────────────────────────
# TAB 2: WEIGHT LOG & ROLLING WEEKLY AVERAGES
# ──────────────────────────────────────────
with tab2:
    st.title("⚖️ Weight & Rolling Averages")
    
    with st.form("weight_form", clear_on_submit=True):
        col_d, col_w = st.columns([1, 1])
        with col_d:
            weight_date = st.date_input("Weigh-in Date", datetime.today())
        with col_w:
            weight_val = st.number_input("Morning Weight (kg)", min_value=40.0, max_value=150.0, value=77.8, step=0.1)
        submit_weight = st.form_submit_button("💾 Log Daily Weight")
        
        if submit_weight:
            conn = get_db_connection()
            conn.execute(
                "INSERT OR REPLACE INTO weight_logs (date, weight) VALUES (?, ?)", 
                (weight_date.strftime("%Y-%m-%d"), weight_val)
            )
            conn.commit()
            conn.close()
            st.success(f"Weight logged: {weight_val} kg on {weight_date.strftime('%Y-%m-%d')}!")
            st.rerun()
            
    # Load weight logs and calculate moving average
    conn = get_db_connection()
    weights_df = pd.read_sql_query("SELECT * FROM weight_logs ORDER BY date ASC", conn)
    conn.close()
    
    if not weights_df.empty:
        weights_df['date'] = pd.to_datetime(weights_df['date'])
        # Sort & remove duplicates if any
        weights_df = weights_df.drop_duplicates(subset=['date']).sort_values('date')
        
        # Calculate moving average across available logged days
        weights_df_interp = weights_df.set_index('date').resample('D').mean().interpolate()
        weights_df_interp['Weekly_Average'] = weights_df_interp['weight'].rolling(window=7, min_periods=1).mean()
        weights_df_interp = weights_df_interp.reset_index()
        
        latest_avg = weights_df_interp['Weekly_Average'].iloc[-1]
        st.metric("Current 7-Day Rolling Average", f"{latest_avg:.2f} kg", delta=f"{latest_avg - 77.8:.2f} kg from baseline")
        
        # Plot weight trend
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=weights_df['date'], 
            y=weights_df['weight'], 
            name="Daily Weight", 
            mode="markers", 
            marker=dict(color="#ffa0a0", size=9)
        ))
        fig.add_trace(go.Scatter(
            x=weights_df_interp['date'], 
            y=weights_df_interp['Weekly_Average'], 
            name="7-Day Rolling Avg (Zone 2 Baseline)", 
            line=dict(color="#ff4b4b", width=3)
        ))
        # Add target line
        fig.add_hline(y=66.9, line_dash="dash", line_color="#22c55e", annotation_text="Target: 66.9 kg", annotation_position="bottom right")
        
        fig.update_layout(
            title="Weight Loss Progression & Rolling Trend", 
            xaxis_title="Date", 
            yaxis_title="Weight (kg)",
            template="plotly_dark",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, width="stretch")
        
        with st.expander("📋 View / Manage Weight Log History"):
            display_weights = weights_df.copy()
            display_weights['date'] = display_weights['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display_weights.sort_values('date', ascending=False), width="stretch")
            
            st.write("---")
            st.markdown("##### 🗑️ Delete an Incorrect Weight Entry")
            all_weight_dates = display_weights['date'].tolist()
            if all_weight_dates:
                col_w_del, col_w_btn = st.columns([2, 1])
                with col_w_del:
                    del_date = st.selectbox("Select Date to Delete", all_weight_dates, key="del_weight_date")
                with col_w_btn:
                    st.write("")
                    st.write("")
                    if st.button("Delete Entry", key="btn_del_weight"):
                        conn = get_db_connection()
                        conn.execute("DELETE FROM weight_logs WHERE date = ?", (del_date,))
                        conn.commit()
                        conn.close()
                        st.success(f"Deleted weight log for {del_date}!")
                        st.rerun()


# ──────────────────────────────────────────
# TAB 3: WORKOUT PROGRESSION & GYM LOGGER (HEVY/STRONG STYLE)
# ──────────────────────────────────────────
with tab3:
    st.title("🏋️ Workout Routine & Progression")
    
    workout_routines = {
        "Day 1: Push Focus (Chest, Shoulders, Triceps)": [
            "Chest Press Machine (Wide grip)", "Shoulder Press (Dumbbell)", "Chest Fly (Machine)", 
            "Lateral Raise (Machine)", "Triceps Pushdown (Cable)", "Crunch (Machine)"
        ],
        "Day 2: Pull Focus (Back, Biceps)": [
            "Lat Pulldown (Cable)", "Seated Cable Row (V Grip)", "Bent Over Row (Barbell)", 
            "Bicep Curl (Barbell)", "Hammer Curl (Dumbbell)"
        ],
        "Day 3: Legs Focus": [
            "Leg Press Horizontal (Machine)", "Leg Extension (Machine)", "Lying Leg Curl (Machine)", 
            "Sumo Squat (Dumbbell)", "Seated Calf Raise", "Plank"
        ],
        "Day 4: Upper Body Focus (Compounds & Arms)": [
            "Chest Press Machine (Close grip)", "Reverse Grip Lat Pulldown (Cable)", "Front Raise (Dumbbell)", 
            "Rear Delt Reverse Fly (Machine)", "Overhead Triceps Extension (Dumbbell)", "Preacher Curl (Machine)"
        ],
        "Day 5: Lower Body & Core Focus": [
            "Squat (Bodyweight / Dumbbell)", "Hip Abduction (Machine)", "Leg Press Horizontal (Machine)", 
            "Lying Leg Curl (Machine)", "Crunch (Machine)"
        ]
    }
    
    exercise_muscles = {
        "Chest Press Machine (Wide grip)": "Chest & Triceps",
        "Shoulder Press (Dumbbell)": "Shoulders",
        "Chest Fly (Machine)": "Chest",
        "Lateral Raise (Machine)": "Side Delts",
        "Triceps Pushdown (Cable)": "Triceps",
        "Crunch (Machine)": "Abs / Core",
        "Lat Pulldown (Cable)": "Lats & Upper Back",
        "Seated Cable Row (V Grip)": "Mid Back & Lats",
        "Bent Over Row (Barbell)": "Upper Back & Lats",
        "Bent Over Row (Dumbbell)": "Upper Back",
        "Bicep Curl (Barbell)": "Biceps",
        "Hammer Curl (Dumbbell)": "Brachialis & Forearms",
        "Leg Press Horizontal (Machine)": "Quads & Glutes",
        "Leg Extension (Machine)": "Quads",
        "Lying Leg Curl (Machine)": "Hamstrings",
        "Sumo Squat (Dumbbell)": "Inner Thighs & Glutes",
        "Seated Calf Raise": "Calves",
        "Plank": "Core Stability",
        "Chest Press Machine (Close grip)": "Triceps & Chest",
        "Reverse Grip Lat Pulldown (Cable)": "Lats & Biceps",
        "Front Raise (Dumbbell)": "Front Delts",
        "Rear Delt Reverse Fly (Machine)": "Rear Delts",
        "Overhead Triceps Extension (Dumbbell)": "Triceps Long Head",
        "Preacher Curl (Machine)": "Biceps Peak",
        "Squat (Bodyweight / Dumbbell)": "Quads & Glutes",
        "Hip Abduction (Machine)": "Gluteus Medius"
    }
    
    cardio_finisher = {
        "Day 1": "Zone 2 Treadmill Walk (Incline 12-15%, Speed 5.0-5.5 km/h) for 20 mins (HR 115-135 BPM)",
        "Day 2": "Zone 2 Elliptical Trainer for 20 minutes",
        "Day 3": "Zone 2 Stationary/Recumbent Cycling for 20 minutes",
        "Day 4": "Zone 2 Rowing Machine for 20 minutes (Targets trunk fat)",
        "Day 5": "Zone 2 Treadmill Walk (Incline 12-15%, Speed 5.0-5.5 km/h) for 20 mins"
    }
    
    # Workout Date & Routine Selectors
    col_day_sel, col_date_sel = st.columns([2, 1])
    with col_day_sel:
        selected_day = st.selectbox("Select Workout Routine", list(workout_routines.keys()))
    with col_date_sel:
        workout_date = st.date_input("Date", datetime.today())
    
    date_str = workout_date.strftime("%Y-%m-%d")
    day_key = selected_day.split(":")[0].strip()
    st.warning(f"🏃‍♂️ **Cardio Finisher**: {cardio_finisher.get(day_key, '20 mins Zone 2 Cardio')}")
    
    routine_exercises = list(workout_routines[selected_day])
    
    # Check what exercises in this routine already have logged sets today
    conn = get_db_connection()
    today_all_logs = pd.read_sql_query(
        "SELECT id, exercise_name, set_number, weight_kg, reps FROM workout_logs WHERE date = ?",
        conn, params=(date_str,)
    )
    conn.close()
    
    completed_counts = today_all_logs.groupby('exercise_name')['set_number'].count().to_dict() if not today_all_logs.empty else {}
    
    # Exercise Library / Picker with completion badges
    exercise_display_labels = []
    for ex in routine_exercises:
        c = completed_counts.get(ex, 0)
        badge = f" ({c} sets ✅)" if c > 0 else ""
        exercise_display_labels.append(f"{ex}{badge}")
        
    exercise_display_labels.append("➕ Custom / Other Exercise...")
    
    col_ex_pick, col_custom = st.columns([3, 1])
    with col_ex_pick:
        picked_label = st.selectbox("Select Exercise to Log", exercise_display_labels)
    
    if picked_label == "➕ Custom / Other Exercise...":
        with col_custom:
            selected_exercise = st.text_input("Enter Exercise Name", value="Bent Over Row (Dumbbell)")
    else:
        # Strip the completion badge to get clean exercise name
        selected_exercise = picked_label.split(" (")[0]
        
    muscle_group = exercise_muscles.get(selected_exercise, "Strength / Hypertrophy")
    
    st.write("---")
    
    # Fetch existing logged sets for this exercise on this date
    conn = get_db_connection()
    current_ex_sets = pd.read_sql_query(
        "SELECT id, set_number, weight_kg, reps FROM workout_logs WHERE date = ? AND exercise_name = ? ORDER BY set_number ASC",
        conn, params=(date_str, selected_exercise)
    )
    
    # Fetch previous session sets for this exercise (before current date)
    prev_session_sets = pd.read_sql_query(
        """
        SELECT set_number, weight_kg, reps, date FROM workout_logs 
        WHERE exercise_name = ? AND date < ? 
        AND date = (SELECT MAX(date) FROM workout_logs WHERE exercise_name = ? AND date < ?)
        ORDER BY set_number ASC
        """,
        conn, params=(selected_exercise, date_str, selected_exercise, date_str)
    )
    conn.close()
    
    existing_sets_dict = {row['set_number']: row for _, row in current_ex_sets.iterrows()}
    prev_sets_dict = {row['set_number']: row for _, row in prev_session_sets.iterrows()}
    prev_date_str = prev_session_sets['date'].iloc[0] if not prev_session_sets.empty else None
    
    prev_badge = f"<span style='color: #a7f3d0; font-size: 0.8rem; margin-left: 8px;'>📅 Last: {prev_date_str}</span>" if prev_date_str else ""
    
    # ─── INTERACTIVE HEVY-STYLE EXERCISE CARD ───
    st.markdown(f"""
    <div style="background: #1e293b; border-radius: 12px; padding: 16px; border: 1px solid #334155; margin-bottom: 15px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h3 style="margin: 0; color: #ffffff; font-size: 1.3rem;">🏋️‍♂️ {selected_exercise}</h3>
                <span style="color: #38bdf8; font-size: 0.85rem; font-weight: 600;">{muscle_group}</span>{prev_badge}
            </div>
            <span style="background: #334155; color: #cbd5e1; padding: 4px 10px; border-radius: 12px; font-size: 0.8rem;">
                {date_str}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col_note, col_timer = st.columns([2, 1])
    with col_note:
        st.text_input("Note", placeholder="Add pinned note (e.g. felt light, form cues)", key=f"note_{selected_exercise}_{date_str}", label_visibility="collapsed")
    with col_timer:
        rest_choice = st.selectbox("Rest Timer", ["Rest: Off", "Rest: 30s", "Rest: 60s", "Rest: 90s", "Rest: 120s", "Rest: 180s"], index=2, key=f"rest_{selected_exercise}", label_visibility="collapsed")
    
    # Maintain number of set rows in session_state
    state_key_count = f"num_sets_{selected_exercise}_{date_str}"
    if state_key_count not in st.session_state:
        max_logged = max(existing_sets_dict.keys()) if existing_sets_dict else 3
        max_prev = max(prev_sets_dict.keys()) if prev_sets_dict else 3
        st.session_state[state_key_count] = max(3, max_logged, max_prev)
        
    num_rows = st.session_state[state_key_count]
    
    # Set Table Headers (5 columns: SET, PREV, KG, REPS, ACTION)
    col_h_set, col_h_prev, col_h_kg, col_h_reps, col_h_act = st.columns([1, 2.2, 2.2, 2.2, 1.8])
    with col_h_set:
        st.markdown("<p style='text-align:center; font-weight:bold; color:#94a3b8; font-size:0.8rem; margin:0;'>SET</p>", unsafe_allow_html=True)
    with col_h_prev:
        st.markdown("<p style='text-align:center; font-weight:bold; color:#38bdf8; font-size:0.8rem; margin:0;'>PREVIOUS</p>", unsafe_allow_html=True)
    with col_h_kg:
        st.markdown("<p style='text-align:center; font-weight:bold; color:#94a3b8; font-size:0.8rem; margin:0;'>KG</p>", unsafe_allow_html=True)
    with col_h_reps:
        st.markdown("<p style='text-align:center; font-weight:bold; color:#94a3b8; font-size:0.8rem; margin:0;'>REPS</p>", unsafe_allow_html=True)
    with col_h_act:
        st.markdown("<p style='text-align:center; font-weight:bold; color:#94a3b8; font-size:0.8rem; margin:0;'>ACTION</p>", unsafe_allow_html=True)
        
    # Render Interactive Set Rows
    for s_idx in range(1, num_rows + 1):
        is_saved = s_idx in existing_sets_dict
        saved_row = existing_sets_dict.get(s_idx, None)
        prev_row = prev_sets_dict.get(s_idx, None)
        
        # Intelligent defaults from previous session or previous set
        if is_saved:
            default_kg = float(saved_row['weight_kg'])
            default_reps = int(saved_row['reps'])
        elif prev_row is not None:
            default_kg = float(prev_row['weight_kg'])
            default_reps = int(prev_row['reps'])
        elif (s_idx - 1) in existing_sets_dict:
            default_kg = float(existing_sets_dict[s_idx - 1]['weight_kg'])
            default_reps = int(existing_sets_dict[s_idx - 1]['reps'])
        else:
            default_kg = 10.0
            default_reps = 12
        
        c_set, c_prev, c_kg, c_reps, c_act = st.columns([1, 2.2, 2.2, 2.2, 1.8])
        
        with c_set:
            badge_bg = "#22c55e" if is_saved else "#334155"
            badge_text = "white"
            st.markdown(
                f"<div style='background:{badge_bg}; color:{badge_text}; font-weight:bold; text-align:center; border-radius:8px; padding:6px 0; margin-top:2px;'>{s_idx}</div>",
                unsafe_allow_html=True
            )
            
        with c_prev:
            if prev_row is not None:
                p_text = f"{prev_row['weight_kg']}k × {prev_row['reps']}"
                st.markdown(
                    f"<div style='background:#0f172a; border:1px solid #334155; color:#cbd5e1; font-weight:600; text-align:center; border-radius:8px; padding:6px 2px; font-size:0.75rem; margin-top:2px;' title='Last session load'>{p_text}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    "<div style='color:#475569; text-align:center; padding:6px 0; font-size:0.85rem; margin-top:2px;'>—</div>",
                    unsafe_allow_html=True
                )
            
        with c_kg:
            val_kg = st.number_input(
                f"KG {s_idx}", 
                min_value=0.0, 
                max_value=500.0, 
                value=default_kg, 
                step=0.5, 
                key=f"input_kg_{selected_exercise}_{date_str}_{s_idx}", 
                label_visibility="collapsed"
            )
            
        with c_reps:
            val_reps = st.number_input(
                f"Reps {s_idx}", 
                min_value=1, 
                max_value=100, 
                value=default_reps, 
                step=1, 
                key=f"input_reps_{selected_exercise}_{date_str}_{s_idx}", 
                label_visibility="collapsed"
            )
            
        with c_act:
            sub_col_tick, sub_col_del = st.columns([1, 1])
            with sub_col_tick:
                tick_icon = "✅" if is_saved else "✔️"
                tick_help = "Completed! Click to update" if is_saved else "Click tick to complete set"
                if st.button(tick_icon, key=f"btn_tick_{selected_exercise}_{date_str}_{s_idx}", help=tick_help):
                    conn = get_db_connection()
                    if is_saved:
                        conn.execute(
                            "UPDATE workout_logs SET weight_kg = ?, reps = ?, day_type = ? WHERE id = ?",
                            (val_kg, val_reps, selected_day, saved_row['id'])
                        )
                        st.toast(f"Set {s_idx} updated: {val_kg} kg × {val_reps} reps! 🔄")
                    else:
                        conn.execute(
                            "INSERT INTO workout_logs (date, day_type, exercise_name, set_number, weight_kg, reps) VALUES (?, ?, ?, ?, ?, ?)",
                            (date_str, selected_day, selected_exercise, s_idx, val_kg, val_reps)
                        )
                        st.toast(f"Set {s_idx} completed: {val_kg} kg × {val_reps} reps! ✅")
                    conn.commit()
                    conn.close()
                    st.rerun()
                    
            with sub_col_del:
                if st.button("❌", key=f"btn_del_{selected_exercise}_{date_str}_{s_idx}", help="Remove set"):
                    if is_saved:
                        conn = get_db_connection()
                        conn.execute("DELETE FROM workout_logs WHERE id = ?", (saved_row['id'],))
                        conn.commit()
                        conn.close()
                        st.toast(f"Set {s_idx} deleted from database! 🗑️")
                    else:
                        st.toast(f"Set {s_idx} removed!")
                    
                    if s_idx == num_rows and num_rows > 1:
                        st.session_state[state_key_count] = num_rows - 1
                    st.rerun()
                    
    # + Add Set Button
    st.write("")
    if st.button("➕ Add Set", key=f"btn_add_set_{selected_exercise}_{date_str}", width="stretch"):
        st.session_state[state_key_count] = num_rows + 1
        st.rerun()
        
    # Rest Timer Notification if set
    if rest_choice != "Rest: Off":
        st.info(f"⏱️ **{rest_choice}**: Rest timer active! Take deep breaths before next set.")
        
    st.write("---")
    
    # ─── TODAY'S WORKOUT SUMMARY ───
    if not today_all_logs.empty:
        total_sets_done = len(today_all_logs)
        total_volume = (today_all_logs['weight_kg'] * today_all_logs['reps']).sum()
        
        st.markdown(f"#### 📊 Session Summary for {date_str}")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Total Sets Completed", f"{total_sets_done} sets")
        with col_m2:
            st.metric("Total Lift Volume", f"{total_volume:,.0f} kg")
            
        with st.expander(f"📋 View All Logged Sets for {date_str}"):
            st.dataframe(today_all_logs[['exercise_name', 'set_number', 'weight_kg', 'reps', 'day_type']], width="stretch")
            if st.button(f"⚠️ Delete ALL Sets for {date_str}", key="btn_del_all_today"):
                conn = get_db_connection()
                conn.execute("DELETE FROM workout_logs WHERE date = ?", (date_str,))
                conn.commit()
                conn.close()
                st.warning(f"All sets for {date_str} cleared!")
                st.rerun()
                
    # ─── EXERCISE PROGRESSION HISTORY CHART ───
    st.write("---")
    st.subheader(f"📈 Double Progression Trend: {selected_exercise}")
    
    conn = get_db_connection()
    history_df = pd.read_sql_query(
        "SELECT id, date, set_number, weight_kg, reps FROM workout_logs WHERE exercise_name = ? ORDER BY date ASC, set_number ASC",
        conn, params=(selected_exercise,)
    )
    conn.close()
    
    if not history_df.empty:
        max_lifts = history_df.groupby('date')['weight_kg'].max().reset_index()
        fig = px.line(max_lifts, x='date', y='weight_kg', title=f"Max Weight Lifted Trend — {selected_exercise}", markers=True)
        fig.update_traces(line_color="#38bdf8", marker=dict(size=9, color="#ff4b4b"))
        fig.update_layout(template="plotly_dark", yaxis_title="Max Load (kg)", xaxis_title="Date")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info(f"No previous workouts logged for {selected_exercise}. Complete sets above to start tracking your strength curve!")


# ──────────────────────────────────────────
# TAB 4: AI NUTRITION CAMERA LOGGER
# ──────────────────────────────────────────
with tab4:
    st.title("🥗 AI Food Scanner & Logger")
    
    is_saturday = datetime.now().weekday() == 5
    if is_saturday:
        st.error("🕉️ **Today is Saturday (Egg-Free Focus Day)**. Skip eggs! Focus on soya chunks, tofu, paneer, sprouts, and curd to hit 110g protein.")
    else:
        st.success("🍳 **Weekday Nutrition**: Ensure you meet your 110g protein target using boiled eggs, omelettes, paneer, and whole-food sources.")
        
    st.subheader("🍽️ Log Meal with AI")
    
    input_method = st.radio(
        "Choose Input Method",
        ["📝 Describe Meal (Text)", "📁 Upload Image", "📷 Use Camera"],
        horizontal=True
    )
    
    if input_method == "📝 Describe Meal (Text)":
        st.markdown("<p style='color: #94a3b8; font-size: 0.9rem; margin-bottom: 6px;'>Type what you ate or drank (e.g. portions, ingredients, preparation):</p>", unsafe_allow_html=True)
        
        # Sample prompt chips for quick logging
        st.caption("💡 Quick Suggestions:")
        chip_col1, chip_col2, chip_col3, chip_col4 = st.columns(4)
        with chip_col1:
            if st.button("☕ Coffee w/ Sugar", key="chip_coffee"):
                st.session_state['meal_text_input_val'] = "One Cup of Coffee with Light Sugar"
                st.rerun()
        with chip_col2:
            if st.button("🥚 2 Eggs & Toast", key="chip_eggs"):
                st.session_state['meal_text_input_val'] = "2 Boiled Eggs with 1 slice whole wheat toast"
                st.rerun()
        with chip_col3:
            if st.button("🥣 Dal & 2 Rotis", key="chip_roti"):
                st.session_state['meal_text_input_val'] = "2 Phulkas / Rotis with 1 medium bowl Moong Dal and salad"
                st.rerun()
        with chip_col4:
            if st.button("🥤 Whey in Water", key="chip_whey"):
                st.session_state['meal_text_input_val'] = "1 Scoop Whey Protein Isolate mixed in 300ml water"
                st.rerun()
                
        meal_text = st.text_area(
            "Meal Description",
            value=st.session_state.get('meal_text_input_val', ''),
            placeholder="e.g. One Cup of Coffee with Light Sugar\nor: 150g Paneer tikka with green chutney and salad",
            height=85,
            key="input_meal_text",
            label_visibility="collapsed"
        )
        
        if st.button("🔍 Analyze Nutrition with Gemini", key="btn_analyze_text"):
            if not api_key:
                st.error("Please provide a valid Gemini API Key in the sidebar.")
            elif not meal_text.strip():
                st.warning("Please enter what you ate or drank first.")
            else:
                with st.spinner(f"Analyzing nutrition for '{meal_text.strip()}' with {model_choice}..."):
                    try:
                        start_time = time.time()
                        meal_macros = analyze_meal_text(api_key, meal_text.strip(), model_name=model_choice)
                        duration = time.time() - start_time
                        
                        st.session_state['ai_base_calories'] = float(meal_macros.get("calories", 0.0))
                        st.session_state['ai_base_protein'] = float(meal_macros.get("protein", 0.0))
                        st.session_state['ai_base_carbs'] = float(meal_macros.get("carbs", 0.0))
                        st.session_state['ai_base_fat'] = float(meal_macros.get("fat", 0.0))
                        st.session_state['ai_portion'] = 1.0
                        
                        st.session_state['ai_description'] = str(meal_macros.get("food_description", meal_text.strip()))
                        st.session_state['ai_calories'] = st.session_state['ai_base_calories']
                        st.session_state['ai_protein'] = st.session_state['ai_base_protein']
                        st.session_state['ai_carbs'] = st.session_state['ai_base_carbs']
                        st.session_state['ai_fat'] = st.session_state['ai_base_fat']
                        model_used_name = meal_macros.get("model_used", model_choice.split(" ")[0])
                        st.session_state['scan_success_msg'] = f"⚡ Nutrition Analyzed in {duration:.1f}s ({model_used_name})! Verify details below."
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to analyze meal: {e}")
                        
    else:
        uploaded_file = None
        if input_method == "📷 Use Camera":
            uploaded_file = st.camera_input("Take a photo of your meal")
        else:
            uploaded_file = st.file_uploader("Upload meal photo", type=["jpg", "jpeg", "png"])
        
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Meal Photo Ready for Scan", width="stretch")
            
            if st.button("🔍 Scan & Calculate Macros with Gemini", key="btn_scan_image"):
                if not api_key:
                    st.error("Please provide a valid Gemini API Key in the sidebar.")
                else:
                    with st.spinner(f"Analyzing meal ingredients with {model_choice}..."):
                        try:
                            start_time = time.time()
                            meal_macros = analyze_meal_image(api_key, image, model_name=model_choice)
                            duration = time.time() - start_time
                            
                            st.session_state['ai_base_calories'] = float(meal_macros.get("calories", 0.0))
                            st.session_state['ai_base_protein'] = float(meal_macros.get("protein", 0.0))
                            st.session_state['ai_base_carbs'] = float(meal_macros.get("carbs", 0.0))
                            st.session_state['ai_base_fat'] = float(meal_macros.get("fat", 0.0))
                            st.session_state['ai_portion'] = 1.0
                            
                            st.session_state['ai_description'] = str(meal_macros.get("food_description", "Meal"))
                            st.session_state['ai_calories'] = st.session_state['ai_base_calories']
                            st.session_state['ai_protein'] = st.session_state['ai_base_protein']
                            st.session_state['ai_carbs'] = st.session_state['ai_base_carbs']
                            st.session_state['ai_fat'] = st.session_state['ai_base_fat']
                            model_used_name = meal_macros.get("model_used", model_choice.split(" ")[0])
                            st.session_state['scan_success_msg'] = f"⚡ Meal Analyzed in {duration:.1f}s ({model_used_name})! Verify details below."
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to analyze image: {e}")
                        
    st.write("---")
    st.subheader("📝 Verify & Save to Food Log")
    if 'scan_success_msg' in st.session_state:
        st.success(st.session_state['scan_success_msg'])
    
    # ─── QUICK PORTION MULTIPLIER ───
    if 'ai_base_calories' in st.session_state:
        st.markdown("<p style='margin: 8px 0 4px 0; font-weight: 600; color: #94a3b8; font-size: 0.9rem;'>🍽️ PORTION SIZE MULTIPLIER</p>", unsafe_allow_html=True)
        col_p05, col_p10, col_p15, col_p20 = st.columns(4)
        current_mult = st.session_state.get('ai_portion', 1.0)
        
        with col_p05:
            p05_label = "✅ 0.5x" if current_mult == 0.5 else "0.5x (Half)"
            if st.button(p05_label, key="btn_portion_05"):
                st.session_state['ai_portion'] = 0.5
                st.session_state['ai_calories'] = round(st.session_state['ai_base_calories'] * 0.5, 1)
                st.session_state['ai_protein'] = round(st.session_state['ai_base_protein'] * 0.5, 1)
                st.session_state['ai_carbs'] = round(st.session_state['ai_base_carbs'] * 0.5, 1)
                st.session_state['ai_fat'] = round(st.session_state['ai_base_fat'] * 0.5, 1)
                st.rerun()
        with col_p10:
            p10_label = "✅ 1.0x" if current_mult == 1.0 else "1.0x (Regular)"
            if st.button(p10_label, key="btn_portion_10"):
                st.session_state['ai_portion'] = 1.0
                st.session_state['ai_calories'] = st.session_state['ai_base_calories']
                st.session_state['ai_protein'] = st.session_state['ai_base_protein']
                st.session_state['ai_carbs'] = st.session_state['ai_base_carbs']
                st.session_state['ai_fat'] = st.session_state['ai_base_fat']
                st.rerun()
        with col_p15:
            p15_label = "✅ 1.5x" if current_mult == 1.5 else "1.5x (Large)"
            if st.button(p15_label, key="btn_portion_15"):
                st.session_state['ai_portion'] = 1.5
                st.session_state['ai_calories'] = round(st.session_state['ai_base_calories'] * 1.5, 1)
                st.session_state['ai_protein'] = round(st.session_state['ai_base_protein'] * 1.5, 1)
                st.session_state['ai_carbs'] = round(st.session_state['ai_base_carbs'] * 1.5, 1)
                st.session_state['ai_fat'] = round(st.session_state['ai_base_fat'] * 1.5, 1)
                st.rerun()
        with col_p20:
            p20_label = "✅ 2.0x" if current_mult == 2.0 else "2.0x (Double)"
            if st.button(p20_label, key="btn_portion_20"):
                st.session_state['ai_portion'] = 2.0
                st.session_state['ai_calories'] = round(st.session_state['ai_base_calories'] * 2.0, 1)
                st.session_state['ai_protein'] = round(st.session_state['ai_base_protein'] * 2.0, 1)
                st.session_state['ai_carbs'] = round(st.session_state['ai_base_carbs'] * 2.0, 1)
                st.session_state['ai_fat'] = round(st.session_state['ai_base_fat'] * 2.0, 1)
                st.rerun()
                
    desc = st.text_input("Food Description", value=st.session_state.get('ai_description', ''))
    col_cal, col_p = st.columns(2)
    with col_cal:
        cals = st.number_input("Calories (kcal)", min_value=0.0, max_value=4000.0, value=float(st.session_state.get('ai_calories', 0.0)), step=10.0)
    with col_p:
        prots = st.number_input("Protein (g)", min_value=0.0, max_value=300.0, value=float(st.session_state.get('ai_protein', 0.0)), step=1.0)
        
    col_c, col_f = st.columns(2)
    with col_c:
        carbs = st.number_input("Carbohydrates (g)", min_value=0.0, max_value=500.0, value=float(st.session_state.get('ai_carbs', 0.0)), step=1.0)
    with col_f:
        fats = st.number_input("Fats (g)", min_value=0.0, max_value=300.0, value=float(st.session_state.get('ai_fat', 0.0)), step=1.0)
        
    col_cat, col_btn = st.columns([1, 1])
    with col_cat:
        meal_type = st.selectbox("Meal Category", ["Breakfast", "Lunch", "Dinner", "Snack"])
    with col_btn:
        st.write("")
        st.write("")
        save_meal = st.button("💾 Save Meal Log")
        
    if save_meal:
        if not desc:
            st.error("Please enter a food description.")
        else:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO nutrition_logs (date, meal_type, food_description, calories, protein, carbs, fat) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().strftime("%Y-%m-%d"), meal_type, desc, cals, prots, carbs, fats)
            )
            conn.commit()
            conn.close()
            st.success(f"Saved: {desc} ({cals:.0f} kcal, {prots:.1f}g protein) logged!")
            
            for key in ['ai_description', 'ai_calories', 'ai_protein', 'ai_carbs', 'ai_fat', 'scan_success_msg', 'ai_base_calories', 'ai_base_protein', 'ai_base_carbs', 'ai_base_fat', 'ai_portion', 'meal_text_input_val']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    # Display today's meals table
    st.write("---")
    st.subheader("📅 Today's Food Logs")
    conn = get_db_connection()
    today_logs_df = pd.read_sql_query(
        "SELECT id, meal_type, food_description, calories, protein, carbs, fat FROM nutrition_logs WHERE date = ? ORDER BY id DESC",
        conn, params=(datetime.now().strftime("%Y-%m-%d"),)
    )
    conn.close()
    
    if not today_logs_df.empty:
        st.dataframe(today_logs_df[['meal_type', 'food_description', 'calories', 'protein', 'carbs', 'fat']], width="stretch")
        
        # Meal deletion option
        with st.expander("🗑️ Delete a Logged Meal"):
            meal_to_delete = st.selectbox("Select Meal ID to Delete", today_logs_df['id'].tolist(), format_func=lambda x: f"ID {x}: {today_logs_df[today_logs_df['id'] == x]['food_description'].values[0]}")
            if st.button("Delete Selected Entry"):
                conn = get_db_connection()
                conn.execute("DELETE FROM nutrition_logs WHERE id = ?", (meal_to_delete,))
                conn.commit()
                conn.close()
                st.success("Entry removed!")
                st.rerun()
    else:
        st.info("No meals logged yet for today. Capture a photo above or enter values manually!")
