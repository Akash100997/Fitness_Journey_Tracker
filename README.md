# 🏃‍♂️ Robur Fit: Metabolic Companion

A mobile-first, responsive personal metabolic, training, and AI nutrition tracking web application built with **Python**, **Streamlit**, **SQLite**, and **Google Generative AI (Gemini)**.

Designed specifically for a 12-week metabolic reset and body recomposition journey.

---

## 🌟 Key Features

### 1. 📊 Dashboard Overview
* **Accuniq Baselines**: Tracks starting weight (77.8 kg), target weight (66.9 kg), muscle mass (30.4 kg), and target fat loss (10.9 kg).
* **Daily Budget Cards**: Real-time progress bars for calorie budget (1850 kcal) and protein target (110 g).
* **12-Week Metabolic Countdown**: Live countdown and week tracker towards target recomposition date.
* **Metabolic Stats**: Displays resting BMR (1562 kcal), TDEE (2405 kcal), and 3.8 L daily water target.

### 2. ⚖️ Weight Tracker & Rolling Trend
* Daily morning weigh-in logging.
* Automatic **7-day rolling moving average** calculation with pandas interpolation to filter daily water/glycogen fluctuations.
* Interactive **Plotly** visualization featuring daily markers, trend curves, and target reference lines.

### 3. 🏋️ Workout Routine & Double Progression Logger
* **5-Day Routine Splits**:
  - **Day 1**: Push Focus (Chest, Shoulders, Triceps)
  - **Day 2**: Pull Focus (Back, Biceps)
  - **Day 3**: Legs Focus
  - **Day 4**: Upper Body Focus (Compounds & Arms)
  - **Day 5**: Lower Body & Core Focus
* **Zone 2 Cardio Finishers**: Specific daily cardio targets (Treadmill Incline, Elliptical, Cycling, Rowing machine for trunk fat).
* **Set-by-Set Logging**: Track set numbers, weights (kg), and rep counts.
* **Exercise Progression History**: Double-progression charts tracking max weight lifted over time for each exercise.

### 4. 🥗 AI Food Scanner & Macro Tracker
* **Gemini Vision Integration**: Take a photo or upload an image of your meal to calculate estimated calories, protein, carbs, and fat.
* **Model Selection**: Switch between `gemini-1.5-flash`, `gemini-2.0-flash`, or `gemini-1.5-pro`.
* **Eggetarian & Saturday Egg-Free Alert**: Dynamic dietary guidance, reminding you to swap eggs for paneer, tofu, soya chunks, sprouts, and curd on Saturdays.
* **Meal Log Table**: Review, log, and manage daily meals.

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
When running locally, your terminal will display a **Network URL** (e.g., `http://192.168.1.XX:8501`). Open this address on your phone's browser while connected to the same Wi-Fi network and add it to your home screen!

---

## ☁️ Cloud Deployment (Streamlit Community Cloud)

1. Go to [share.streamlit.io](https://share.streamlit.io) and log in with GitHub.
2. Select repository: `Akash100997/Fitness_Journey_Tracker`.
3. Main file path: `app.py`.
4. In Advanced Settings, add your secret key:
   ```toml
   GEMINI_API_KEY = "your-google-ai-studio-api-key"
   ```
5. Click **Deploy** to get a public HTTPS link accessible on mobile anywhere!
