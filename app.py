import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import json
import io
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

# ─── DATABASE SERVICES ───
DB_FILE = "robur_fit.db"

def get_db_connection():
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
    
    # Seed initial weight log to show trend if empty
    cursor.execute("SELECT COUNT(*) FROM weight_logs")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT OR REPLACE INTO weight_logs (date, weight) VALUES (?, ?)", ("2026-04-01", 77.1))
        cursor.execute("INSERT OR REPLACE INTO weight_logs (date, weight) VALUES (?, ?)", ("2026-09-03", 77.8))

    conn.commit()
    conn.close()

init_db()

# ─── GEMINI AI NUTRITION SERVICE ───
def analyze_meal_image(api_key, image_bytes, image_mime, model_name="gemini-1.5-flash"):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    
    model = genai.GenerativeModel(
        model_name,
        generation_config={"response_mime_type": "application/json"}
    )
    
    prompt = """
    You are an expert sports nutritionist AI. Analyze this image of a meal.
    Calculate and estimate the macronutrient breakdown.
    Keep in mind the user is a Hindu eggetarian (no meat/fish, skips eggs on Saturday, relies on lentils, paneer, tofu, soya chunks, eggs on weekdays, curd, roti, rice).
    
    Output ONLY a valid JSON object matching this schema:
    {
      "food_description": "A brief summary of what the foods are",
      "calories": 450.0,
      "protein": 25.5,
      "carbs": 45.0,
      "fat": 12.0
    }
    Ensure all nutritional values are numeric. Be as accurate as possible with portion estimates.
    """
    
    image_parts = [{"mime_type": image_mime, "data": image_bytes}]
    response = model.generate_content([prompt, image_parts[0]])
    text_response = response.text.strip()
    
    # Clean possible markdown wrap if model returned it despite mime type
    if text_response.startswith("```"):
        text_response = text_response.split("```")[1]
        if text_response.startswith("json"):
            text_response = text_response[4:]
    return json.loads(text_response.strip())


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
model_choice = st.sidebar.selectbox("Gemini Vision Model", ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"], index=0)

if api_key:
    st.sidebar.success(f"API Key Ready ({model_choice})")
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
        "SELECT COALESCE(SUM(calories), 0) as cal, COALESCE(SUM(protein), 0) as prot FROM nutrition_logs WHERE date = ?", 
        (today_str,)
    ).fetchone()
    
    latest_weight_row = conn.execute("SELECT weight, date FROM weight_logs ORDER BY date DESC LIMIT 1").fetchone()
    conn.close()
    
    cal_eaten = float(nutrition_today['cal'])
    prot_eaten = float(nutrition_today['prot'])
    
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

    # 12-Week Countdown
    st.write("---")
    start_date = datetime(2026, 9, 3)
    today_dt = datetime.now()
    days_passed = max(0, (today_dt - start_date).days)
    weeks_passed = days_passed // 7
    weeks_remaining = max(0, 12 - weeks_passed)
    
    st.info(f"📆 **12-Week Metabolic Reset Countdown**: You are in **Week {weeks_passed + 1}** (Day {days_passed + 1}). **{weeks_remaining} weeks** remaining to hit your 66.9 kg target!")
    
    # Quick Action Summary Cards
    col_w_info, col_m_info = st.columns(2)
    with col_w_info:
        st.markdown(f"""
        <div style="background-color: #1e293b; padding: 12px; border-radius: 8px; color: white;">
            <strong>💧 Daily Water Target:</strong> {profile['water_target_liters']} Liters<br>
            <strong>🔥 Resting BMR:</strong> {profile['bmr_kcal']:.0f} kcal | <strong>TDEE:</strong> {profile['tdee_kcal']:.0f} kcal
        </div>
        """, unsafe_allow_html=True)
    with col_m_info:
        is_sat = datetime.now().weekday() == 5
        sat_msg = "🕉️ **Saturday Egg-Free Mode** active!" if is_sat else "🍳 **Egg-friendly Weekday** active."
        st.markdown(f"""
        <div style="background-color: #1e293b; padding: 12px; border-radius: 8px; color: white;">
            <strong>🥗 Diet Status:</strong> {sat_msg}<br>
            <strong>🎯 Fat Control Goal:</strong> 22.6 kg → 11.7 kg Fat
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
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📋 View / Manage Weight Log History"):
            display_weights = weights_df.copy()
            display_weights['date'] = display_weights['date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display_weights.sort_values('date', ascending=False), use_container_width=True)


# ──────────────────────────────────────────
# TAB 3: WORKOUT PROGRESSION & GYM LOGGER
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
    
    cardio_finisher = {
        "Day 1": "Zone 2 Treadmill Walk (Incline 12-15%, Speed 5.0-5.5 km/h) for 20 mins (HR 115-135 BPM)",
        "Day 2": "Zone 2 Elliptical Trainer for 20 minutes",
        "Day 3": "Zone 2 Stationary/Recumbent Cycling for 20 minutes",
        "Day 4": "Zone 2 Rowing Machine for 20 minutes (Targets trunk fat - 11.96 kg)",
        "Day 5": "Zone 2 Treadmill Walk (Incline 12-15%, Speed 5.0-5.5 km/h) for 20 mins"
    }
    
    selected_day = st.selectbox("Select Workout Routine", list(workout_routines.keys()))
    exercises = workout_routines[selected_day]
    day_key = selected_day.split(":")[0].strip()
    
    st.warning(f"🏃‍♂️ **Cardio Finisher**: {cardio_finisher.get(day_key, '20 mins Zone 2 Cardio')}")
    
    st.write("---")
    st.subheader("Log Your Active Lift")
    
    with st.form("workout_form", clear_on_submit=False):
        col_d, col_e = st.columns([1, 2])
        with col_d:
            log_date = st.date_input("Workout Date", datetime.today())
        with col_e:
            logged_exercise = st.selectbox("Select Exercise", exercises)
        
        col_s, col_w, col_r = st.columns(3)
        with col_s:
            set_num = st.number_input("Set Number", min_value=1, max_value=8, value=1)
        with col_w:
            weight_val = st.number_input("Weight (kg)", min_value=0.0, max_value=400.0, value=10.0, step=0.5)
        with col_r:
            reps_val = st.number_input("Reps", min_value=1, max_value=60, value=12)
            
        submit_workout = st.form_submit_button("⚡ Log Set Details")
        
        if submit_workout:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO workout_logs (date, day_type, exercise_name, set_number, weight_kg, reps) VALUES (?, ?, ?, ?, ?, ?)",
                (log_date.strftime("%Y-%m-%d"), selected_day, logged_exercise, set_num, weight_val, reps_val)
            )
            conn.commit()
            conn.close()
            st.success(f"Logged: Set {set_num} ({weight_val} kg × {reps_val} reps) for {logged_exercise}!")
            
    # Exercise Progression History
    st.write("---")
    st.subheader("📈 Exercise Progression (Double Progression)")
    conn = get_db_connection()
    all_exercises_logged = pd.read_sql_query("SELECT DISTINCT exercise_name FROM workout_logs", conn)
    conn.close()
    
    if not all_exercises_logged.empty:
        exercise_list = all_exercises_logged['exercise_name'].tolist()
        default_idx = exercise_list.index(logged_exercise) if logged_exercise in exercise_list else 0
        history_exercise = st.selectbox("Choose Exercise to View Progression", exercise_list, index=default_idx)
        
        conn = get_db_connection()
        history_df = pd.read_sql_query(
            "SELECT id, date, set_number, weight_kg, reps FROM workout_logs WHERE exercise_name = ? ORDER BY date ASC, set_number ASC",
            conn, params=(history_exercise,)
        )
        conn.close()
        
        if not history_df.empty:
            max_lifts = history_df.groupby('date')['weight_kg'].max().reset_index()
            fig = px.line(max_lifts, x='date', y='weight_kg', title=f"Max Weight Lifted Trend — {history_exercise}", markers=True)
            fig.update_traces(line_color="#38bdf8", marker=dict(size=9, color="#ff4b4b"))
            fig.update_layout(template="plotly_dark", yaxis_title="Max Weight (kg)", xaxis_title="Date")
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander(f"📋 View Logged Sets for {history_exercise}"):
                st.dataframe(history_df[['date', 'set_number', 'weight_kg', 'reps']], use_container_width=True)
        else:
            st.info("No progression history logged yet for this exercise.")
    else:
        st.info("Start logging sets above to see your exercise progression charts!")


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
        
    st.subheader("📷 Capture or Upload Meal Image")
    
    input_method = st.radio("Choose Input Method", ["Upload Image", "Use Camera"], horizontal=True)
    uploaded_file = None
    if input_method == "Use Camera":
        uploaded_file = st.camera_input("Take a photo of your meal")
    else:
        uploaded_file = st.file_uploader("Upload meal photo", type=["jpg", "jpeg", "png"])
    
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption="Meal Photo Ready for Scan", use_container_width=True)
        
        if st.button("🔍 Scan & Calculate Macros with Gemini"):
            if not api_key:
                st.error("Please provide a valid Gemini API Key in the sidebar.")
            else:
                with st.spinner(f"Analyzing meal ingredients with {model_choice}..."):
                    try:
                        img_byte_arr = io.BytesIO()
                        # Convert RGBA to RGB if png
                        if image.mode in ("RGBA", "P"):
                            image = image.convert("RGB")
                        image.save(img_byte_arr, format='JPEG')
                        img_bytes = img_byte_arr.getvalue()
                        
                        meal_macros = analyze_meal_image(api_key, img_bytes, "image/jpeg", model_name=model_choice)
                        
                        st.session_state['ai_description'] = str(meal_macros.get("food_description", "Meal"))
                        st.session_state['ai_calories'] = float(meal_macros.get("calories", 0.0))
                        st.session_state['ai_protein'] = float(meal_macros.get("protein", 0.0))
                        st.session_state['ai_carbs'] = float(meal_macros.get("carbs", 0.0))
                        st.session_state['ai_fat'] = float(meal_macros.get("fat", 0.0))
                        st.success("Meal Scan Analysis Completed! Verify details below.")
                    except Exception as e:
                        st.error(f"Failed to analyze image: {e}")
                        
    st.write("---")
    st.subheader("📝 Verify & Save to Food Log")
    
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
            
            for key in ['ai_description', 'ai_calories', 'ai_protein', 'ai_carbs', 'ai_fat']:
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
        st.dataframe(today_logs_df[['meal_type', 'food_description', 'calories', 'protein', 'carbs', 'fat']], use_container_width=True)
        
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
