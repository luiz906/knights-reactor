import json
import uuid
from datetime import datetime
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

WORKOUT_LOGS_FILE = DATA_DIR / "workout_logs.json"
FOOD_LOGS_FILE = DATA_DIR / "food_logs.json"

EXERCISES = {
    "chest": [
        {"name": "Bench Press", "sets": 4, "reps": "8-10", "rest": 90, "tip": "Drive through your chest, keep shoulder blades pinched"},
        {"name": "Incline DB Press", "sets": 3, "reps": "10-12", "rest": 75, "tip": "Keep elbows at 45° from torso"},
        {"name": "Cable Chest Fly", "sets": 3, "reps": "12-15", "rest": 60, "tip": "Slight bend in elbows, squeeze at center"},
        {"name": "Push-ups", "sets": 3, "reps": "max", "rest": 60, "tip": "Full range of motion, chest to floor"},
    ],
    "back": [
        {"name": "Lat Pulldown", "sets": 4, "reps": "8-10", "rest": 90, "tip": "Pull to upper chest, squeeze lats at bottom"},
        {"name": "Barbell Rows", "sets": 4, "reps": "8-10", "rest": 90, "tip": "Hinge at hips, pull to lower chest"},
        {"name": "Seated Cable Rows", "sets": 3, "reps": "12", "rest": 75, "tip": "Sit tall, pull elbows past your back"},
        {"name": "Face Pulls", "sets": 3, "reps": "15", "rest": 60, "tip": "Pull to eye level, external rotation at end"},
    ],
    "legs": [
        {"name": "Squats", "sets": 4, "reps": "8-10", "rest": 120, "tip": "Chest up, knees track over toes, break parallel"},
        {"name": "Leg Press", "sets": 3, "reps": "12-15", "rest": 90, "tip": "Full range, don't lock knees at top"},
        {"name": "Romanian Deadlift", "sets": 3, "reps": "10", "rest": 90, "tip": "Push hips back, feel the hamstring stretch"},
        {"name": "Leg Curls", "sets": 3, "reps": "12", "rest": 60, "tip": "Slow and controlled on the way down"},
        {"name": "Calf Raises", "sets": 4, "reps": "20", "rest": 45, "tip": "Full range — all the way up and all the way down"},
    ],
    "cardio_walking": [
        {"name": "Warm-up Walk", "type": "timed", "duration": 300},
        {"name": "Brisk Walk", "type": "timed", "duration": 1500},
        {"name": "Cool-down Walk", "type": "timed", "duration": 300},
    ],
    "cardio_bag": [
        {"name": "Warm-up", "type": "timed", "duration": 120},
        {"name": "Rounds", "type": "rounds", "work": 180, "rest": 60, "total_rounds": 6},
        {"name": "Cool-down Stretch", "type": "timed", "duration": 300},
    ],
}


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, indent=2))


# ── Static files ───────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "workout.html")


@app.get("/workout.js")
def serve_js():
    return FileResponse(BASE_DIR / "workout.js", media_type="application/javascript")


@app.get("/workout.css")
def serve_css():
    return FileResponse(BASE_DIR / "workout.css", media_type="text/css")


# ── Exercise definitions ───────────────────────────────────────────────────────

@app.get("/api/exercises")
def get_exercises():
    return EXERCISES


# ── Workout logs ───────────────────────────────────────────────────────────────

class WorkoutLogIn(BaseModel):
    date: str
    type: str
    started_at: str
    completed_at: str
    duration_mins: int
    exercises: list


@app.get("/api/workout/logs")
def get_workout_logs():
    return load_json(WORKOUT_LOGS_FILE, [])


@app.post("/api/workout/logs")
def save_workout_log(log: WorkoutLogIn):
    logs = load_json(WORKOUT_LOGS_FILE, [])
    entry = log.dict()
    entry["id"] = uuid.uuid4().hex
    logs.append(entry)
    save_json(WORKOUT_LOGS_FILE, logs)
    return {"id": entry["id"]}


# ── Food logs ──────────────────────────────────────────────────────────────────

class FoodEntryIn(BaseModel):
    date: str
    name: str
    calories: float
    protein: float
    carbs: float
    fat: float
    grams: float


@app.get("/api/food/logs")
def get_food_logs(date: str = Query(...)):
    logs = load_json(FOOD_LOGS_FILE, {})
    return logs.get(date, [])


@app.post("/api/food/logs")
def save_food_entry(entry: FoodEntryIn):
    logs = load_json(FOOD_LOGS_FILE, {})
    if entry.date not in logs:
        logs[entry.date] = []
    item = entry.dict()
    item["id"] = uuid.uuid4().hex
    item["logged_at"] = datetime.now().isoformat()
    logs[entry.date].append(item)
    save_json(FOOD_LOGS_FILE, logs)
    return {"id": item["id"]}


@app.delete("/api/food/logs/{log_id}")
def delete_food_entry(log_id: str, date: str = Query(...)):
    logs = load_json(FOOD_LOGS_FILE, {})
    if date in logs:
        logs[date] = [e for e in logs[date] if e["id"] != log_id]
        if not logs[date]:
            del logs[date]
        save_json(FOOD_LOGS_FILE, logs)
    return {"ok": True}


# ── Food search proxy (Open Food Facts) ───────────────────────────────────────

@app.get("/api/food/search")
def food_search(q: str = Query(...)):
    try:
        r = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": q,
                "json": "1",
                "page_size": "10",
                "fields": "product_name,nutriments",
            },
            timeout=8,
        )
        data = r.json()
    except Exception as exc:
        raise HTTPException(502, f"Food API unavailable: {exc}")

    results = []
    for p in data.get("products", []):
        name = (p.get("product_name") or "").strip()
        if not name:
            continue
        n = p.get("nutriments", {})
        kcal = n.get("energy-kcal_100g") or n.get("energy-kcal") or 0
        if not kcal and n.get("energy_100g"):
            kcal = round(n["energy_100g"] / 4.184)
        results.append({
            "name": name,
            "kcal_per_100g": round(float(kcal or 0), 1),
            "protein_per_100g": round(float(n.get("proteins_100g") or 0), 1),
            "carbs_per_100g": round(float(n.get("carbohydrates_100g") or 0), 1),
            "fat_per_100g": round(float(n.get("fat_100g") or 0), 1),
        })
    return results
