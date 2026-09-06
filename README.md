# 🏃‍♂️ Robur Fit: Metabolic Companion

A mobile-first, responsive personal metabolic, training, and AI nutrition tracking web application built with **Python**, **Streamlit**, **SQLite**, and **Google Generative AI (Gemini)**.

Designed for structured metabolic resets, strength progression, and body recomposition journeys.

---

## 🌟 Key Features

### 1. 📊 Dashboard Overview
* **Body Composition Baselines**: Tracks starting weight, target weight, muscle mass, and fat loss goals.
* **Daily Budget Cards**: Real-time progress bars for daily calorie budgets and protein targets.
* **Metabolic Countdown**: Live countdown and week tracker towards your target recomposition milestone.
* **Hydration & Energy Expenditure**: Visual indicators for resting BMR, TDEE, and daily water targets.

### 2. ⚖️ Weight Tracker & Rolling Trend
* Daily morning weigh-in logging.
* Automatic **7-day rolling moving average** calculation with interpolation to filter out daily water and glycogen fluctuations.
* Interactive **Plotly** visualization with trend curves and target reference lines.

### 3. 🏋️ Workout Routine & Double Progression Logger
* **5-Day Split Routines**:
  - **Day 1**: Push Focus (Chest, Shoulders, Triceps)
  - **Day 2**: Pull Focus (Back, Biceps)
  - **Day 3**: Legs Focus
  - **Day 4**: Upper Body Focus (Compounds & Arms)
  - **Day 5**: Lower Body & Core Focus
* **Zone 2 Cardio Finishers**: Tailored daily post-lift aerobic sessions (Incline walking, Elliptical, Cycling, Rowing).
* **Set-by-Set Logging**: Track set numbers, loads (kg), and rep counts.
* **Exercise Progression Charts**: Double-progression analytics displaying max load trends over time for each movement.

### 4. 🥗 AI Food Scanner & Macro Tracker
* **Gemini Vision Integration**: Snap a photo or upload meal images to estimate calories, protein, carbs, and fat in seconds.
* **Flexible Model Selection**: Seamlessly toggle between `gemini-1.5-flash`, `gemini-2.0-flash`, and `gemini-1.5-pro`.
* **Smart Dietary Awareness**: Vegetarian/eggetarian macro recognition, with optional reminder modes for egg-free days.
* **Daily Nutrition Logs**: Easily review, modify, and manage logged meals throughout the day.

---

## 🚀 Quick Start (Local Setup)

### 1. Clone the repository
```bash
git clone https://github.com/Akash100997/Fitness_Journey_Tracker.git
cd Fitness_Journey_Tracker
```

### 2. Create and activate a virtual environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the application
```bash
streamlit run app.py
```

### 5. Access on Mobile
When running locally, your terminal displays a **Network URL** (e.g., `http://192.168.1.XX:8501`). Open this address in your mobile browser while connected to the same local network for a gym-ready companion app!

---

## ☁️ Cloud Deployment (Streamlit Community Cloud)

1. Sign in to [share.streamlit.io](https://share.streamlit.io) with GitHub.
2. Select repository: `Akash100997/Fitness_Journey_Tracker` (`main` branch).
3. Main file path: `app.py`.
4. In **Advanced settings**, add your Google AI Studio API key:
   ```toml
   GEMINI_API_KEY = "your-google-ai-studio-api-key"
   ```
5. Click **Deploy** to launch your companion app with a permanent public HTTPS URL.
