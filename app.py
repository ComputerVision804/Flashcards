import os
import json
import datetime
import random
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from io import BytesIO

app = Flask("flashcard_app")
app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key')  # Change this in production

# Define upload folders for multimedia (ensure these folders exist)
UPLOAD_FOLDER_IMAGES = os.path.join('static', 'images')
UPLOAD_FOLDER_AUDIO = os.path.join('static', 'audio')
os.makedirs(UPLOAD_FOLDER_IMAGES, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_AUDIO, exist_ok=True)

# ---------------------------
# User Profiles Helper Functions
# ---------------------------
USER_PROFILES_FILE = 'user_profiles.json'

def load_user_profiles():
    if os.path.exists(USER_PROFILES_FILE):
        with open(USER_PROFILES_FILE, 'r') as f:
            return json.load(f)
    else:
        return {}

def save_user_profiles(profiles):
    with open(USER_PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=4)

def init_user_profile(username):
    now = datetime.datetime.now().isoformat()
    profile = {
        "score": 0,
        "reviewed_count": 0,
        "cards": {}
    }
    for card in global_flashcards:
        profile["cards"][card["question"]] = {"box": 1, "next_review": now}
    return profile

# ---------------------------
# Global Flashcards List
# ---------------------------
global_flashcards = [
    {
        "question": "What is the capital of France?",
        "answer": "Paris",
        "hint": "It's known as the city of love.",
        "explanation": "Paris is the capital and largest city of France.",
        "image": "paris.jpg",  # This file should be placed in static/images/
        "audio": "paris.mp3"   # This file should be placed in static/audio/
    },
    {
        "question": "What is 2 + 2?",
        "answer": "4",
        "hint": "Simple arithmetic.",
        "explanation": "2 + 2 equals 4.",
        "image": None,
        "audio": None
    },
    {
        "question": "What color is the sky on a clear day?",
        "answer": "Blue",
        "hint": "Look up on a clear day.",
        "explanation": "Due to Rayleigh scattering, the sky appears blue.",
        "image": None,
        "audio": None
    }
    # Add more flashcards as needed.
]

# ---------------------------
# Spaced Repetition Settings
# ---------------------------
INTERVALS = {1: 10, 2: 20, 3: 40, 4: 80}
MAX_BOX = 4

def get_due_cards(profile):
    now = datetime.datetime.now()
    due = []
    for card in global_flashcards:
        progress = profile["cards"].get(card["question"])
        if progress:
            next_review = datetime.datetime.fromisoformat(progress["next_review"])
            if now >= next_review:
                card_copy = card.copy()
                card_copy["box"] = progress["box"]
                card_copy["next_review"] = progress["next_review"]
                due.append(card_copy)
    random.shuffle(due)
    return due

# ---------------------------
# Routes
# ---------------------------
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('flashcards_route'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get("username", "").strip()
        if not username:
            flash("Username cannot be empty.", "error")
            return redirect(url_for("login"))
        profiles = load_user_profiles()
        if username not in profiles:
            profiles[username] = init_user_profile(username)
            save_user_profiles(profiles)
        session['username'] = username
        return redirect(url_for("flashcards_route"))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route('/flashcards', methods=['GET', 'POST'])
def flashcards_route():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    profiles = load_user_profiles()
    profile = profiles.get(username)
    if not profile:
        flash("Profile not found.", "error")
        return redirect(url_for("login"))
    
    if request.method == 'POST':
        question = request.form.get("question")
        mark = request.form.get("mark")  # "correct" or "incorrect"
        progress = profile["cards"].get(question)
        now = datetime.datetime.now()
        if mark == "correct":
            profile["score"] += 1
            if progress["box"] < MAX_BOX:
                progress["box"] += 1
            interval = INTERVALS[progress["box"]]
            next_review = now + datetime.timedelta(seconds=interval)
            progress["next_review"] = next_review.isoformat()
        else:
            progress["box"] = 1
            interval = INTERVALS[1]
            next_review = now + datetime.timedelta(seconds=interval)
            progress["next_review"] = next_review.isoformat()
        profile["reviewed_count"] = profile.get("reviewed_count", 0) + 1
        profiles[username] = profile
        save_user_profiles(profiles)
        return redirect(url_for("flashcards_route"))
    
    due_cards = get_due_cards(profile)
    if not due_cards:
        return render_template('no_cards.html')
    
    card = due_cards[0]
    return render_template('flashcards.html', card=card, username=username)

@app.route('/statistics')
def statistics():
    if 'username' not in session:
        return redirect(url_for("login"))
    username = session['username']
    profiles = load_user_profiles()
    profile = profiles.get(username)
    total_reviewed = profile.get("reviewed_count", 0)
    score = profile.get("score", 0)
    accuracy = (score / total_reviewed * 100) if total_reviewed > 0 else 0
    return render_template('statistics.html', username=username, total_reviewed=total_reviewed, score=score, accuracy=round(accuracy, 2))

# ---------------------------
# Import / Export Routes
# ---------------------------
@app.route('/import_flashcards', methods=['GET', 'POST'])
def import_flashcards():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        file = request.files.get("flashcard_file")
        if file and file.filename.endswith(".json"):
            try:
                imported_cards = json.load(file)
                count = 0
                for card in imported_cards:
                    if "question" in card and "answer" in card:
                        if not any(c["question"] == card["question"] for c in global_flashcards):
                            global_flashcards.append(card)
                            count += 1
                flash(f"Imported {count} new flashcards.", "success")
            except Exception as e:
                flash(f"Error importing flashcards: {e}", "error")
        else:
            flash("Please upload a valid JSON file.", "error")
        return redirect(url_for("flashcards_route"))
    return render_template('import_flashcards.html')

@app.route('/export_flashcards')
def export_flashcards():
    data = json.dumps(global_flashcards, indent=4)
    buf = BytesIO(data.encode('utf-8'))
    buf.seek(0)
    return send_file(buf, mimetype='application/json', as_attachment=True, attachment_filename="flashcards_export.json")

if __name__ == "__main__":
    app.run(debug=True)
