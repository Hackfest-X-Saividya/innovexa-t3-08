"""
app.py - Main Flask Application for Green Pulse
Carbon Footprint Tracking, Reduction and Rewards Platform
Tagline: "Track Your Impact. Make Every Action Count."
Features:
 - User Authentication (Register, Login, Logout)
 - AI Evidence Verification Engine (< 2 min automated verification)
 - Real-Time Dashboard Status Display
 - Casual Everyday Default Suggestions / Habits
 - Before-and-After Simulator & Documented Carbon Calculator
"""

import os
import uuid
import functools
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, jsonify, send_from_directory, abort
)

import database
import calculations
import recommendations
import rewards
import ai_verifier

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "green-pulse-hackathon-2024-secret-key-xyz")

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 Megabytes limit

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Ensure required directories exist and database is initialized
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
with app.app_context():
    database.init_db()


def allowed_file(filename):
    """Validates image file extension against approved whitelist."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_user_id():
    """Returns active user ID from session. Default to Aarav (1) if in demo mode."""
    return session.get("user_id", 1)


def get_current_org_id():
    """Returns active organization ID for the current session, defaulting to 1 (Apex Institute)."""
    if "active_org_id" in session:
        return session["active_org_id"]
    user_id = session.get("user_id", 2)
    org = database.get_user_organization(user_id)
    if org:
        session["active_org_id"] = org["id"]
        return org["id"]
    return 1


def login_required(view):
    """Decorator to require login for user-specific actions."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please sign in or create an account to access this page.", "info")
            return redirect(url_for("login", next=request.url))
        return view(**kwargs)
    return wrapped_view


@app.context_processor
def inject_global_data():
    """Makes current user info, active mode, organization profile, points summaries, and auth status available globally."""
    user_id = session.get("user_id", 1)  # Default to demo user for smooth navigation
    is_authenticated = "user_id" in session
    active_mode = session.get("account_type", "individual")

    conn = database.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, username, full_name, email, role, account_type, institution FROM users WHERE id = ?", (user_id,))
    user_row = cursor.fetchone()
    current_user = dict(user_row) if user_row else {
        "id": 1, "username": "aarav_sharma", "full_name": "Aarav Sharma", 
        "email": "aarav@greenpulse.demo", "role": "user", "account_type": "individual",
        "institution": "Dept of Computer Science & Engineering"
    }

    # Count pending individual submissions for reviewer badge
    cursor.execute("SELECT COUNT(*) FROM evidence_submissions WHERE status = 'pending'")
    pending_submissions_count = cursor.fetchone()[0]

    # Organization metrics
    active_org_id = get_current_org_id()
    cursor.execute("SELECT COUNT(*) FROM org_evidence_submissions WHERE org_id = ? AND status = 'pending'", (active_org_id,))
    org_pending_row = cursor.fetchone()
    org_pending_submissions_count = org_pending_row[0] if org_pending_row else 0

    conn.close()

    points_data = rewards.get_user_points_summary(user_id)
    active_org = database.get_organization(active_org_id)
    org_points_data = database.get_org_points_summary(active_org_id)

    return {
        "current_user": current_user,
        "is_authenticated": is_authenticated,
        "active_mode": active_mode,
        "active_org_id": active_org_id,
        "active_org": active_org,
        "points_data": points_data,
        "org_points_data": org_points_data,
        "pending_submissions_count": pending_submissions_count,
        "org_pending_submissions_count": org_pending_submissions_count,
        "now_year": datetime.now().year
    }


# ==========================================================
# 1. USER AUTHENTICATION & DUAL-MODE PORTAL
# ==========================================================
@app.route("/")
def index():
    """Default landing route: routes based on login and active mode (Individual vs Organization)."""
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("account_type") == "organization":
        return redirect(url_for("org_dashboard"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Dual-Mode Login: Individual Mode (User) vs Organization/Industry Mode (Admin)."""
    selected_mode = request.args.get("mode", "individual")

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "").strip()
        selected_mode = request.form.get("mode", "individual")

        result = database.authenticate_user(identifier, password, required_mode=selected_mode)
        if result["success"]:
            user = result["user"]
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            acc_type = user.get("account_type", selected_mode)
            session["account_type"] = acc_type

            if acc_type == "organization":
                org = database.get_user_organization(user["id"])
                session["active_org_id"] = org["id"] if org else (2 if user["id"] == 3 else 1)
                flash(f"Welcome, {user['full_name']}! Signed in to Organization Dashboard.", "success")
                next_url = request.args.get("next") or url_for("org_dashboard")
                return redirect(next_url)
            else:
                flash(f"Welcome, {user['full_name']}! Signed in to Individual Dashboard.", "success")
                next_url = request.args.get("next") or url_for("dashboard")
                return redirect(next_url)
        else:
            flash(result["message"], "danger")

    return render_template("login.html", active_mode=selected_mode)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Registration for Individuals (Students/Citizens) or Organizations (Colleges/Industries)."""
    selected_mode = request.args.get("mode", "individual")

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        account_type = request.form.get("account_type", "individual")
        institution = request.form.get("institution", "Green Tech Engineering College").strip()

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return render_template("register.html", active_mode=account_type)

        result = database.register_user(username, full_name, email, password, account_type, institution)
        if result["success"]:
            session["user_id"] = result["user_id"]
            session["role"] = "admin" if account_type == "organization" else "user"
            session["account_type"] = account_type

            if account_type == "organization":
                org_res = database.create_organization(
                    org_name=institution if institution else f"{full_name} Facility",
                    org_type="College/University",
                    sector="Higher Education & Campus Research",
                    employee_count=200,
                    building_count=3,
                    location="Main Campus, Bengaluru",
                    reporting_period="monthly",
                    admin_user_id=result["user_id"]
                )
                if org_res.get("success"):
                    session["active_org_id"] = org_res["org_id"]
                flash(f"{result['message']} Welcome to the Green Pulse Organization Portal!", "success")
                return redirect(url_for("org_dashboard"))
            else:
                flash(f"{result['message']} Welcome to Green Pulse!", "success")
                return redirect(url_for("dashboard"))
        else:
            flash(result["message"], "danger")

    return render_template("register.html", active_mode=selected_mode)


@app.route("/logout")
def logout():
    """Signs out current user and returns to Login portal."""
    session.clear()
    flash("You have been signed out. Thank you for making every action count!", "info")
    return redirect(url_for("login"))


@app.route("/mode/switch/<mode>")
def switch_mode(mode):
    """Instant switch between 'individual' and 'organization' modes."""
    if mode == "organization":
        session["account_type"] = "organization"
        if session.get("user_id") == 1:
            session["user_id"] = 2
            session["role"] = "admin"
        session["active_org_id"] = 1
        flash("Switched to Organization Mode (Apex Institute of Technology & Campus).", "info")
        return redirect(url_for("org_dashboard"))
    else:
        session["account_type"] = "individual"
        if session.get("user_id") in [2, 3]:
            session["user_id"] = 1
            session["role"] = "user"
        flash("Switched to Individual Mode (Aarav Sharma).", "info")
        return redirect(url_for("dashboard"))


@app.route("/switch_org/<int:target_org_id>")
def switch_org(target_org_id):
    """Switch active demonstration organization between Org 1 (Apex College) and Org 2 (EcoPulse Manufacturing)."""
    if target_org_id in [1, 2]:
        session["active_org_id"] = target_org_id
        session["account_type"] = "organization"
        if target_org_id == 1:
            session["user_id"] = 2
            session["role"] = "admin"
            flash("Active organization set to: Apex Institute of Technology & Campus (College/University).", "info")
        else:
            session["user_id"] = 3
            session["role"] = "admin"
            flash("Active organization set to: EcoPulse CleanTech Manufacturing Ltd (Industrial Factory).", "info")
    return redirect(url_for("org_dashboard"))


@app.route("/switch_role/<int:user_id>")
def switch_role(user_id):
    """Switch between Aarav (1), Dr. Priya (2), and EcoCorp (3)."""
    if user_id in [1, 2, 3]:
        session["user_id"] = user_id
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role, account_type FROM users WHERE id = ?", (user_id,))
        u = cursor.fetchone()
        conn.close()
        if u:
            session["role"] = u["role"]
            session["account_type"] = u["account_type"]
            if u["account_type"] == "organization":
                org = database.get_user_organization(user_id)
                session["active_org_id"] = org["id"] if org else (1 if user_id == 2 else 2)
                flash(f"Switched persona to {u['role'].capitalize()} ({'Apex Institute' if user_id == 2 else 'EcoPulse CleanTech'}).", "info")
                return redirect(url_for("org_dashboard"))
            else:
                flash("Switched persona to Aarav Sharma (Individual Mode).", "info")
                return redirect(url_for("dashboard"))
    next_page = request.args.get("next", url_for("dashboard"))
    return redirect(next_page)


@app.route("/demo/reset", methods=["POST"])
def demo_reset():
    """Resets the SQLite database to clean demo state for fresh demonstration."""
    database.reset_to_clean_demo()
    session["user_id"] = 1
    session["role"] = "user"
    session["account_type"] = "individual"
    session["active_org_id"] = 1
    flash("Database reset to pristine demo state with documented factors and sample records.", "success")
    return redirect(url_for("dashboard"))


# ==========================================================
# 2. MODULE A: USER DASHBOARD WITH REAL-TIME AI STATUS & CASUAL HABITS
# ==========================================================
@app.route("/dashboard")
def dashboard():
    """
    Module A: Green Pulse User Dashboard.
    Visualizes total estimated emissions, category breakdown,
    real-time AI evidence verification tracker, casual everyday suggestions,
    biggest contributors, active challenges, and points milestone progress.
    """
    user_id = get_current_user_id()
    summary = recommendations.get_user_emission_summary(user_id)
    recs = recommendations.generate_personalized_recommendations(user_id)
    points_info = rewards.get_user_points_summary(user_id)
    casual_habits = database.get_user_casual_habits(user_id)
    latest_ai_verification = ai_verifier.get_latest_ai_verification_status(user_id)

    conn = database.get_db_connection()
    cursor = conn.cursor()

    # Enrolled challenge statistics
    cursor.execute("""
    SELECT status, COUNT(*) as cnt FROM user_challenges WHERE user_id = ? GROUP BY status
    """, (user_id,))
    ch_stats = {row["status"]: row["cnt"] for row in cursor.fetchall()}
    active_challenges = ch_stats.get("accepted", 0)
    completed_challenges = ch_stats.get("completed", 0)

    # Pending submissions count
    cursor.execute("""
    SELECT COUNT(*) FROM evidence_submissions WHERE user_id = ? AND status = 'pending'
    """, (user_id,))
    pending_challenges = cursor.fetchone()[0]

    # Calculate verified emissions avoided through completed approved challenges
    cursor.execute("""
    SELECT COALESCE(SUM(c.co2e_saving_estimate), 0.0) as avoided_total
    FROM evidence_submissions es
    JOIN challenges c ON es.challenge_id = c.id
    WHERE es.user_id = ? AND es.status = 'approved'
    """, (user_id,))
    avoided_row = cursor.fetchone()
    emissions_avoided = round(float(avoided_row["avoided_total"] or 0.0), 2)

    # Recent activity records (last 5)
    cursor.execute("""
    SELECT * FROM activity_records WHERE user_id = ? ORDER BY record_date DESC, id DESC LIMIT 5
    """, (user_id,))
    recent_activities = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template(
        "dashboard.html",
        summary=summary,
        recommendations=recs[:3],
        casual_habits=casual_habits,
        latest_ai_verification=latest_ai_verification,
        active_challenges=active_challenges,
        completed_challenges=completed_challenges,
        pending_challenges=pending_challenges,
        emissions_avoided=emissions_avoided,
        recent_activities=recent_activities,
        points_info=points_info
    )


# ==========================================================
# 3. CASUAL EVERYDAY SUGGESTIONS / HABITS HANDLER
# ==========================================================
@app.route("/habits/log/<int:habit_id>", methods=["POST"])
def log_habit(habit_id):
    """Logs a completed casual everyday habit and awards instant micro-points."""
    user_id = get_current_user_id()
    result = database.log_user_casual_habit(user_id, habit_id)

    if result["success"]:
        flash(result["message"], "success")
    else:
        flash(result["message"], "info")

    next_page = request.form.get("next") or url_for("dashboard")
    return redirect(next_page)


# ==========================================================
# 4. MODULE B: CARBON FOOTPRINT CALCULATOR
# ==========================================================
@app.route("/calculator", methods=["GET", "POST"])
def calculator():
    """
    Module B: Carbon Footprint Calculator.
    Accepts daily or monthly activity data for Transportation, Electricity, Fuel, and Waste.
    Calculates estimated emissions = Activity data × Documented Emission Factor.
    """
    user_id = get_current_user_id()
    factors_data = calculations.load_emission_factors()

    if request.method == "POST":
        reporting_period = request.form.get("reporting_period", "monthly")
        record_date = request.form.get("record_date") or datetime.now().strftime("%Y-%m-%d")
        category = request.form.get("category")
        notes = request.form.get("notes", "").strip()

        calculation_result = None
        conn = database.get_db_connection()
        cursor = conn.cursor()

        if category == "transportation":
            mode_key = request.form.get("trans_mode", "motorcycle")
            distance = float(request.form.get("trans_distance", 0.0))
            if distance > 0:
                calculation_result = calculations.calculate_transportation(mode_key, distance)
                cursor.execute("""
                INSERT INTO activity_records (user_id, reporting_period, record_date, category, 
                                             activity_type, activity_name, input_value, input_unit, 
                                             emission_factor, emissions_kg_co2e, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, reporting_period, record_date, "transportation",
                    mode_key, calculation_result["name"], distance, "km",
                    calculation_result["factor"], calculation_result["emissions_kg_co2e"], notes
                ))

        elif category == "electricity":
            kwh = float(request.form.get("elec_kwh", 0.0))
            grid_mix = request.form.get("elec_grid", "grid_national")
            tariff = float(request.form.get("elec_tariff", 7.00))
            if kwh > 0:
                calculation_result = calculations.calculate_electricity(kwh, grid_mix, tariff)
                cursor.execute("""
                INSERT INTO activity_records (user_id, reporting_period, record_date, category, 
                                             activity_type, activity_name, input_value, input_unit, 
                                             emission_factor, emissions_kg_co2e, cost_inr, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, reporting_period, record_date, "electricity",
                    grid_mix, calculation_result["name"], kwh, "kWh",
                    calculation_result["factor"], calculation_result["emissions_kg_co2e"],
                    calculation_result["cost_inr"], notes
                ))

        elif category == "fuel":
            fuel_type = request.form.get("fuel_type", "lpg")
            qty = float(request.form.get("fuel_qty", 0.0))
            is_cylinder = request.form.get("is_cylinder") == "1"
            if qty > 0:
                calculation_result = calculations.calculate_fuel(fuel_type, qty, is_cylinder)
                cursor.execute("""
                INSERT INTO activity_records (user_id, reporting_period, record_date, category, 
                                             activity_type, activity_name, input_value, input_unit, 
                                             emission_factor, emissions_kg_co2e, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, reporting_period, record_date, "fuel",
                    fuel_type, calculation_result["name"], qty, calculation_result["input_unit"],
                    calculation_result["factor"], calculation_result["emissions_kg_co2e"], notes
                ))

        elif category == "waste":
            waste_type = request.form.get("waste_type", "mixed_landfill")
            kg = float(request.form.get("waste_kg", 0.0))
            if kg > 0:
                calculation_result = calculations.calculate_waste(waste_type, kg)
                cursor.execute("""
                INSERT INTO activity_records (user_id, reporting_period, record_date, category, 
                                             activity_type, activity_name, input_value, input_unit, 
                                             emission_factor, emissions_kg_co2e, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, reporting_period, record_date, "waste",
                    waste_type, calculation_result["name"], kg, "kg",
                    calculation_result["factor"], calculation_result["emissions_kg_co2e"], notes
                ))

        conn.commit()
        conn.close()

        if calculation_result:
            flash(
                f"Successfully recorded {calculation_result['name']}: {calculation_result['emissions_kg_co2e']} kg CO2e "
                f"added to your footprint ({calculation_result['formula']}).", 
                "success"
            )
            return redirect(url_for("dashboard"))
        else:
            flash("Please enter a valid positive quantity for calculation.", "warning")

    return render_template("calculator.html", factors=factors_data)


# ==========================================================
# 5. MODULE C: PERSONALIZED RECOMMENDATIONS
# ==========================================================
@app.route("/recommendations")
def view_recommendations():
    """
    Module C: Personalized Recommendations Hub.
    Presents customized reduction opportunities based on the user's largest emission sources,
    including the 12 criteria and casual everyday habits.
    """
    user_id = get_current_user_id()
    recs = recommendations.generate_personalized_recommendations(user_id)
    summary = recommendations.get_user_emission_summary(user_id)
    casual_habits = database.get_user_casual_habits(user_id)
    return render_template("recommendations.html", recommendations=recs, summary=summary, casual_habits=casual_habits)


# ==========================================================
# 6. MODULE D: BEFORE-AND-AFTER CARBON REDUCTION SIMULATOR
# ==========================================================
@app.route("/simulator", methods=["GET", "POST"])
def simulator():
    """
    Module D: Before-and-After Carbon Reduction Simulator.
    Simulates what-if scenarios (e.g. Motorcycle vs Bus, High kWh vs Reduced kWh)
    and calculates estimated CO2e avoided, % reduction, and financial ₹ savings.
    """
    sim_type = request.args.get("type", "transportation")
    sim_result = None

    if request.method == "POST":
        sim_type = request.form.get("sim_type", "transportation")
        if sim_type == "transportation":
            b_inputs = {
                "mode": request.form.get("b_mode", "motorcycle"),
                "distance": request.form.get("b_dist", 15.0)
            }
            p_inputs = {
                "mode": request.form.get("p_mode", "bus"),
                "distance": request.form.get("b_dist", 15.0)
            }
            sim_result = calculations.simulate_reduction("transportation", b_inputs, p_inputs)

        elif sim_type == "electricity":
            b_inputs = {
                "kwh": request.form.get("b_kwh", 250.0),
                "tariff_inr": request.form.get("tariff", 7.00),
                "grid_mix": request.form.get("grid_mix", "grid_national")
            }
            p_inputs = {
                "kwh": request.form.get("p_kwh", 200.0)
            }
            sim_result = calculations.simulate_reduction("electricity", b_inputs, p_inputs)

        elif sim_type == "waste":
            b_inputs = {"waste_kg": request.form.get("b_waste_kg", 20.0)}
            p_inputs = {
                "compost_kg": request.form.get("p_compost_kg", 12.0),
                "recycle_kg": request.form.get("p_recycle_kg", 6.0)
            }
            sim_result = calculations.simulate_reduction("waste", b_inputs, p_inputs)

    factors_data = calculations.load_emission_factors()
    return render_template("simulator.html", sim_type=sim_type, sim_result=sim_result, factors=factors_data)


# ==========================================================
# 7. MODULE E: SUSTAINABLE CHALLENGES & AI EVIDENCE VERIFICATION
# ==========================================================
@app.route("/challenges")
def challenges():
    """Lists available, accepted, and completed challenges for active user."""
    user_id = get_current_user_id()
    recs = recommendations.generate_personalized_recommendations(user_id)
    return render_template("challenges.html", challenges=recs)


@app.route("/challenges/accept/<int:challenge_id>", methods=["POST"])
def accept_challenge(challenge_id):
    """Enrolls the user in a sustainability challenge."""
    user_id = get_current_user_id()
    conn = database.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM user_challenges WHERE user_id = ? AND challenge_id = ?
    """, (user_id, challenge_id))
    existing = cursor.fetchone()

    if existing:
        flash("You are already enrolled in this challenge.", "info")
    else:
        cursor.execute("""
        INSERT INTO user_challenges (user_id, challenge_id, status)
        VALUES (?, ?, 'accepted')
        """, (user_id, challenge_id))
        conn.commit()
        flash("Challenge accepted! Complete the action and upload your evidence to earn points.", "success")

    conn.close()
    return redirect(url_for("evidence_upload", challenge_id=challenge_id))


@app.route("/evidence/upload", methods=["GET", "POST"])
def evidence_upload():
    """
    Module E: Evidence Upload with Automatic AI Analysis.
    Queues submission into AI Vision verification engine (finishes within 2 mins).
    """
    user_id = get_current_user_id()
    preselect_cid = request.args.get("challenge_id", type=int)

    conn = database.get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        challenge_id = request.form.get("challenge_id", type=int)
        submission_date = request.form.get("submission_date") or datetime.now().strftime("%Y-%m-%d")
        notes = request.form.get("notes", "").strip()

        if "evidence_file" not in request.files:
            flash("No file was uploaded.", "danger")
            return redirect(request.url)

        file = request.files["evidence_file"]
        if file.filename == "":
            flash("Please select an image file to upload as evidence.", "warning")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file format! Supported formats are PNG, JPG, JPEG, and WEBP.", "danger")
            return redirect(request.url)

        # Save file safely with unique filename
        ext = file.filename.rsplit(".", 1)[1].lower()
        unique_name = f"evidence_u{user_id}_c{challenge_id}_{uuid.uuid4().hex[:8]}.{ext}"
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(save_path)
        file_size = os.path.getsize(save_path)

        # Ensure user_challenge row exists
        cursor.execute("""
        SELECT id FROM user_challenges WHERE user_id = ? AND challenge_id = ?
        """, (user_id, challenge_id))
        uc_row = cursor.fetchone()
        if not uc_row:
            cursor.execute("""
            INSERT INTO user_challenges (user_id, challenge_id, status) VALUES (?, ?, 'submitted')
            """, (user_id, challenge_id))
            uc_id = cursor.lastrowid
        else:
            uc_id = uc_row["id"]
            cursor.execute("""
            UPDATE user_challenges SET status = 'submitted' WHERE id = ?
            """, (uc_id,))

        # Insert submission record with 'analyzing' status (preserve original filename)
        orig_name = secure_filename(file.filename) or unique_name
        cursor.execute("""
        INSERT INTO evidence_submissions (user_id, challenge_id, user_challenge_id, 
                                          file_path, file_name, file_size, submission_date, 
                                          notes, status, points_awarded, ai_status, ai_confidence, 
                                          ai_analysis_report, verification_eta_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, 'analyzing', 95.0, 'AI Vision Engine is analyzing photo geometry, timestamps, and route patterns...', 60)
        """, (user_id, challenge_id, uc_id, save_path, orig_name, file_size, submission_date, notes))
        submission_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Trigger AI automated verification worker (runs in background and verifies in 25s, well within 2 mins)
        ai_verifier.schedule_ai_verification_worker(submission_id, delay_seconds=25)

        flash("Evidence received! Green Pulse AI Vision Agent is analyzing your photo. Status will update on your Dashboard within 2 minutes.", "success")
        return redirect(url_for("dashboard"))

    # GET request: load user's eligible challenges and past submissions
    cursor.execute("""
    SELECT c.id, c.title, c.category, c.reward_points, c.evidence_type, uc.status
    FROM challenges c
    LEFT JOIN user_challenges uc ON c.id = uc.challenge_id AND uc.user_id = ?
    ORDER BY c.id ASC
    """, (user_id,))
    available_challenges = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT es.*, c.title as challenge_title, c.reward_points, c.evidence_type
    FROM evidence_submissions es
    JOIN challenges c ON es.challenge_id = c.id
    WHERE es.user_id = ?
    ORDER BY es.created_at DESC
    """, (user_id,))
    submissions_history = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template(
        "evidence.html",
        available_challenges=available_challenges,
        submissions_history=submissions_history,
        preselect_cid=preselect_cid
    )


# ==========================================================
# 8. REAL-TIME AI VERIFICATION APIS
# ==========================================================
@app.route("/api/ai_verify_now/<int:submission_id>", methods=["POST"])
def api_ai_verify_now(submission_id):
    """Fast-track immediate AI verification trigger."""
    result = ai_verifier.verify_submission_sync(submission_id, force=True)
    if result["success"]:
        flash(f"AI Verification Succeeded ({result.get('confidence', 95)}% confidence): Points awarded immediately!", "success")
    else:
        flash(f"AI Verification Outcome: {result.get('decision', 'REJECTED')} ({result.get('confidence', 0)}% confidence) - {result.get('report', 'Evidence does not match challenge requirements.')}", "danger")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/api/verification_status")
def api_verification_status():
    """Returns JSON with latest AI verification status for live dashboard polling."""
    user_id = get_current_user_id()
    status_data = ai_verifier.get_latest_ai_verification_status(user_id)
    points_info = rewards.get_user_points_summary(user_id)
    return jsonify({
        "status_data": status_data,
        "points_balance": points_info["balance"],
        "can_redeem": points_info["can_redeem"]
    })


@app.route("/uploads/<filename>")
def serve_upload(filename):
    """Safely serves uploaded evidence images with filename validation."""
    clean_name = secure_filename(filename)
    return send_from_directory(app.config["UPLOAD_FOLDER"], clean_name)


# ==========================================================
# 9. ADMINISTRATOR / REVIEWER APPROVAL WORKFLOW
# ==========================================================
@app.route("/admin/review")
def admin_review():
    """
    Reviewer Portal for Dr. Priya Rao.
    Inspects photo evidence, reviews AI recommendations, and approves/rejects claims.
    """
    conn = database.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT es.*, u.full_name as user_name, u.email as user_email,
           c.title as challenge_title, c.category, c.reward_points, c.evidence_type, c.instructions
    FROM evidence_submissions es
    JOIN users u ON es.user_id = u.id
    JOIN challenges c ON es.challenge_id = c.id
    ORDER BY CASE WHEN es.status = 'pending' THEN 0 ELSE 1 END, es.created_at DESC
    """)
    submissions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template("admin_review.html", submissions=submissions)


@app.route("/admin/approve/<int:submission_id>", methods=["POST"])
def approve_evidence(submission_id):
    """Approves evidence and awards points once. Strictly prevents duplicate award."""
    reviewer_notes = request.form.get("reviewer_notes", "Verified authentic evidence.").strip()
    result = rewards.approve_submission(submission_id, reviewer_id=get_current_user_id(), reviewer_notes=reviewer_notes)

    if result["success"]:
        flash(result["message"], "success")
    else:
        flash(result["message"], "danger")

    return redirect(url_for("admin_review"))


@app.route("/admin/reject/<int:submission_id>", methods=["POST"])
def reject_evidence(submission_id):
    """Rejects evidence submission with reviewer feedback note."""
    reviewer_notes = request.form.get("reviewer_notes", "Evidence is unclear or does not match guidelines.").strip()
    result = rewards.reject_submission(submission_id, reviewer_id=get_current_user_id(), reviewer_notes=reviewer_notes)

    if result["success"]:
        flash(result["message"], "info")
    else:
        flash(result["message"], "danger")

    return redirect(url_for("admin_review"))


# ==========================================================
# 10. MODULE F: REWARD POINTS & REDEMPTION
# ==========================================================
@app.route("/rewards")
def rewards_page():
    """
    Module F: Rewards Catalog & Wallet.
    Displays points balance, progress bar to 100-point threshold,
    unlocked demonstration vouchers, and redemption history.
    """
    user_id = get_current_user_id()
    catalog_data = rewards.get_rewards_catalog(user_id)
    points_summary = rewards.get_user_points_summary(user_id)

    return render_template(
        "rewards.html",
        catalog=catalog_data["rewards"],
        all_rewards=catalog_data["all_rewards"],
        individual_rewards=catalog_data["individual_rewards"],
        organization_rewards=catalog_data["organization_rewards"],
        user_account_type=catalog_data["account_type"],
        redemptions=catalog_data["redemptions"],
        points_info=points_summary
    )


@app.route("/rewards/redeem/<int:reward_id>", methods=["POST"])
def redeem_reward_action(reward_id):
    """Redeems an eligible reward if the user has reached the points threshold."""
    user_id = get_current_user_id()
    result = rewards.redeem_reward(user_id, reward_id)

    if result["success"]:
        flash(f"{result['message']} Copy your code and present it for verification.", "success")
    else:
        flash(result["message"], "danger")

    return redirect(url_for("rewards_page"))


# ==========================================================
# 11. MODULE G: PROGRESS TRACKING & HISTORICAL AUDIT
# ==========================================================
@app.route("/progress")
def progress():
    """
    Module G: Historical Progress Tracking.
    Compares emissions over reporting periods, visualizes category trends,
    and lists complete audit log of recorded activities and verified reductions.
    """
    user_id = get_current_user_id()
    summary = recommendations.get_user_emission_summary(user_id)

    conn = database.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM activity_records WHERE user_id = ? ORDER BY record_date DESC, id DESC
    """, (user_id,))
    all_activities = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT es.id, es.submission_date, es.reviewed_at, es.points_awarded, es.ai_status, es.ai_confidence,
           c.title as challenge_title, c.category, c.co2e_saving_estimate, c.financial_saving_estimate
    FROM evidence_submissions es
    JOIN challenges c ON es.challenge_id = c.id
    WHERE es.user_id = ? AND es.status = 'approved'
    ORDER BY es.reviewed_at DESC
    """, (user_id,))
    approved_actions = [dict(r) for r in cursor.fetchall()]

    total_verified_savings = sum(a["co2e_saving_estimate"] for a in approved_actions)

    conn.close()

    return render_template(
        "progress.html",
        summary=summary,
        all_activities=all_activities,
        approved_actions=approved_actions,
        total_verified_savings=round(total_verified_savings, 2)
    )


# ==========================================================
# 12. DEDICATED ORGANIZATION ROUTES (SCOPES 1, 2, 3 & 1000-PT THRESHOLD)
# ==========================================================

@app.route("/org/dashboard")
def org_dashboard():
    """
    Dedicated Organization Dashboard.
    Visualizes Scope 1, 2, 3 carbon emissions, intensity per employee/unit,
    avoided emissions, departmental and site breakdowns, challenges, and
    progress toward the mandatory 1,000-point organizational reward milestone.
    """
    org_id = get_current_org_id()
    org = database.get_organization(org_id)
    if not org:
        org_id = 1
        org = database.get_organization(1)

    summary = calculations.get_org_emission_summary(org_id)
    challenges = database.get_org_challenges(org_id)
    points_summary = database.get_org_points_summary(org_id)
    recent_activities = database.get_org_activity_records(org_id)[:6]
    departments = database.get_org_departments(org_id)
    sites = database.get_org_sites(org_id)
    leaderboard = database.get_all_organizations_leaderboard()

    return render_template(
        "org_dashboard.html",
        org=org,
        summary=summary,
        challenges=challenges,
        points_summary=points_summary,
        recent_activities=recent_activities,
        departments=departments,
        sites=sites,
        leaderboard=leaderboard,
        page_title=f"{org['org_name']} — Organization Dashboard"
    )


@app.route("/org/profile", methods=["GET", "POST"])
def org_profile():
    """Manages organization profile, organizational metadata, reporting periods, and administrator info."""
    org_id = get_current_org_id()
    org = database.get_organization(org_id)

    if request.method == "POST":
        org_name = request.form.get("org_name", "").strip()
        org_type = request.form.get("org_type", "Company")
        sector = request.form.get("sector", "").strip()
        employee_count = int(request.form.get("employee_count", 100) or 100)
        building_count = int(request.form.get("building_count", 1) or 1)
        location = request.form.get("location", "").strip()
        reporting_period = request.form.get("reporting_period", "monthly")

        res = database.update_organization_profile(
            org_id, org_name, org_type, sector, employee_count, building_count, location, reporting_period
        )
        if res["success"]:
            flash("Organization profile updated successfully.", "success")
        else:
            flash(res["message"], "danger")
        return redirect(url_for("org_profile"))

    departments = database.get_org_departments(org_id)
    sites = database.get_org_sites(org_id)

    return render_template(
        "org_profile.html",
        org=org,
        departments=departments,
        sites=sites,
        page_title="Organization Profile & Facility Settings"
    )


@app.route("/org/departments_sites", methods=["GET", "POST"])
def org_departments_sites():
    """Manages organizational departments and physical operating sites/campuses."""
    org_id = get_current_org_id()
    org = database.get_organization(org_id)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_dept":
            name = request.form.get("name", "").strip()
            head_name = request.form.get("head_name", "").strip()
            emp_count = int(request.form.get("employee_count", 20) or 20)
            if name:
                database.add_org_department(org_id, name, head_name, emp_count)
                flash(f"Department '{name}' added successfully.", "success")
            else:
                flash("Department name is required.", "warning")
        elif action == "add_site":
            site_name = request.form.get("site_name", "").strip()
            site_type = request.form.get("site_type", "Main Campus")
            address = request.form.get("address", "").strip()
            floor_area = float(request.form.get("floor_area_sqm", 2500.0) or 2500.0)
            if site_name:
                database.add_org_site(org_id, site_name, site_type, address, floor_area)
                flash(f"Operating site facility '{site_name}' added successfully.", "success")
            else:
                flash("Site name is required.", "warning")
        return redirect(url_for("org_departments_sites"))

    departments = database.get_org_departments(org_id)
    sites = database.get_org_sites(org_id)

    return render_template(
        "org_departments_sites.html",
        org=org,
        departments=departments,
        sites=sites,
        page_title="Departments & Operating Facilities"
    )


@app.route("/org/department/delete/<int:dept_id>", methods=["POST"])
def delete_org_department_route(dept_id):
    org_id = get_current_org_id()
    database.delete_org_department(org_id, dept_id)
    flash("Department removed.", "info")
    return redirect(url_for("org_departments_sites"))


@app.route("/org/site/delete/<int:site_id>", methods=["POST"])
def delete_org_site_route(site_id):
    org_id = get_current_org_id()
    database.delete_org_site(org_id, site_id)
    flash("Site facility removed.", "info")
    return redirect(url_for("org_departments_sites"))


@app.route("/org/activities", methods=["GET", "POST"])
def org_activities():
    """
    Dedicated Organization Activity Data Entry Portal:
      - Stream A: Electricity & Energy (Scope 2)
      - Stream B: Company Fleet & Travel (Scope 1)
      - Stream C: Aggregated Employee Commuting (Scope 3)
      - Stream D: Commercial & Operations Waste (Scope 3)
      - Stream E: Industrial Operations (Scope 1)
    """
    org_id = get_current_org_id()
    org = database.get_organization(org_id)

    if request.method == "POST":
        stream = request.form.get("stream", "electricity")
        reporting_period = request.form.get("reporting_period", "monthly")
        record_date = request.form.get("record_date") or datetime.now().strftime("%Y-%m-%d")
        dept_id = request.form.get("department_id")
        dept_id = int(dept_id) if dept_id and dept_id.isdigit() else None
        site_id = request.form.get("site_id")
        site_id = int(site_id) if site_id and site_id.isdigit() else None

        scope = "Scope 2"
        category = stream
        activity_type = ""
        activity_name = ""
        input_value = 0.0
        input_unit = ""
        emission_factor = 0.0
        emissions_kg_co2e = 0.0
        cost_inr = 0.0
        production_units = 0.0
        source_note = ""

        if stream == "electricity":
            kwh = float(request.form.get("kwh", 0.0) or 0.0)
            grid_mix = request.form.get("grid_mix", "grid_national")
            tariff = float(request.form.get("tariff_inr", 8.20) or 8.20)
            entered_cost = request.form.get("cost_inr")
            calc = calculations.calculate_org_electricity(kwh, grid_mix, tariff)
            category = "electricity"
            scope = calc["scope"]
            activity_type = grid_mix
            activity_name = calc["name"]
            input_value = kwh
            input_unit = "kWh"
            emission_factor = calc["factor"]
            emissions_kg_co2e = calc["emissions_kg_co2e"]
            cost_inr = float(entered_cost) if entered_cost and float(entered_cost) > 0 else calc["cost_inr"]
            source_note = calc["source"]

        elif stream == "fleet":
            vehicle_type = request.form.get("vehicle_type", "commercial_van")
            fuel_type = request.form.get("fuel_type", "diesel")
            distance_km = float(request.form.get("distance_km", 0.0) or 0.0)
            liters = float(request.form.get("liters", 0.0) or 0.0)
            calc = calculations.calculate_org_fleet(vehicle_type, fuel_type, distance_km, liters)
            category = "fleet"
            scope = calc["scope"]
            activity_type = vehicle_type
            activity_name = calc["name"]
            input_value = calc["input_value"]
            input_unit = calc["input_unit"]
            emission_factor = calc["factor"]
            emissions_kg_co2e = calc["emissions_kg_co2e"]
            cost_inr = float(request.form.get("cost_inr", 0.0) or 0.0)
            source_note = calc["source"]

        elif stream == "commuting":
            mode_key = request.form.get("mode_key", "bus")
            journeys = int(request.form.get("journeys_count", 50) or 50)
            avg_dist = float(request.form.get("avg_distance_km", 12.0) or 12.0)
            total_km = float(request.form.get("total_passenger_km", 0.0) or 0.0)
            if total_km <= 0.0:
                total_km = journeys * avg_dist
            calc = calculations.calculate_org_commuting(mode_key, total_km)
            category = "commuting"
            scope = calc["scope"]
            activity_type = mode_key
            activity_name = f"Employee Commute ({calc['name']}, {journeys} journeys)"
            input_value = total_km
            input_unit = "passenger-km"
            emission_factor = calc["factor"]
            emissions_kg_co2e = calc["emissions_kg_co2e"]
            source_note = calc["source"]

        elif stream == "waste":
            waste_key = request.form.get("waste_key", "mixed_commercial")
            qty_kg = float(request.form.get("quantity_kg", 0.0) or 0.0)
            qty_tonnes = float(request.form.get("quantity_tonnes", 0.0) or 0.0)
            if qty_tonnes > 0.0:
                qty_kg = qty_tonnes * 1000.0
            calc = calculations.calculate_org_waste(waste_key, qty_kg)
            category = "waste"
            scope = calc["scope"]
            activity_type = waste_key
            activity_name = f"Waste Management ({calc['name']})"
            input_value = qty_kg
            input_unit = "kg"
            emission_factor = calc["factor"]
            emissions_kg_co2e = calc["emissions_kg_co2e"]
            source_note = calc["source"]

        elif stream == "industrial":
            fuel_type = request.form.get("fuel_type", "diesel_generator")
            quantity = float(request.form.get("quantity", 0.0) or 0.0)
            production_units = float(request.form.get("production_units", 0.0) or 0.0)
            calc = calculations.calculate_org_industrial(fuel_type, quantity, production_units)
            category = "industrial"
            scope = calc["scope"]
            activity_type = fuel_type
            activity_name = f"Industrial Operation ({calc['name']})"
            input_value = quantity
            input_unit = calc["input_unit"]
            emission_factor = calc["factor"]
            emissions_kg_co2e = calc["emissions_kg_co2e"]
            cost_inr = float(request.form.get("cost_inr", 0.0) or 0.0)
            source_note = calc["source"]

        notes = request.form.get("notes", "").strip()

        database.add_org_activity_record(
            org_id=org_id,
            department_id=dept_id,
            site_id=site_id,
            reporting_period=reporting_period,
            record_date=record_date,
            category=category,
            scope=scope,
            activity_type=activity_type,
            activity_name=activity_name,
            input_value=input_value,
            input_unit=input_unit,
            emission_factor=emission_factor,
            emissions_kg_co2e=emissions_kg_co2e,
            cost_inr=cost_inr,
            production_units=production_units,
            notes=notes,
            created_by_user_id=session.get("user_id", 2),
            evidence_ref=request.form.get("evidence_ref", "")
        )

        flash(f"Activity recorded in {scope}! Emissions: {round(emissions_kg_co2e / 1000.0, 3)} tonnes CO2e ({emissions_kg_co2e:.1f} kg CO2e).", "success")
        return redirect(url_for("org_activities"))

    period_filter = request.args.get("period")
    activity_records = database.get_org_activity_records(org_id, reporting_period=period_filter)
    departments = database.get_org_departments(org_id)
    sites = database.get_org_sites(org_id)

    return render_template(
        "org_activities.html",
        org=org,
        activity_records=activity_records,
        departments=departments,
        sites=sites,
        period_filter=period_filter,
        page_title="Organizational Activity Data Entry (Scopes 1, 2, 3)"
    )


@app.route("/org/activities/delete/<int:record_id>", methods=["POST"])
def delete_org_activity_route(record_id):
    org_id = get_current_org_id()
    database.delete_org_activity_record(org_id, record_id)
    flash("Activity record deleted.", "info")
    return redirect(url_for("org_activities"))


@app.route("/org/challenges")
def org_challenges():
    """Displays organizational decarbonization challenges, departmental targets, and reward point values."""
    org_id = get_current_org_id()
    org = database.get_organization(org_id)
    challenges = database.get_org_challenges(org_id)
    departments = database.get_org_departments(org_id)

    return render_template(
        "org_challenges.html",
        org=org,
        challenges=challenges,
        departments=departments,
        page_title="Organizational Decarbonization Challenges"
    )


@app.route("/org/evidence/upload", methods=["GET", "POST"])
def org_evidence_upload():
    """Uploads institutional proof (electricity bills, fuel challans, weighbridge receipts)."""
    org_id = get_current_org_id()
    org = database.get_organization(org_id)

    if request.method == "POST":
        challenge_id = request.form.get("challenge_id")
        challenge_id = int(challenge_id) if challenge_id and challenge_id.isdigit() else None
        activity_record_id = request.form.get("activity_record_id")
        activity_record_id = int(activity_record_id) if activity_record_id and activity_record_id.isdigit() else None
        notes = request.form.get("notes", "").strip()
        user_id = session.get("user_id", 2)

        file = request.files.get("evidence_file")
        if not file or file.filename == "":
            flash("Please choose an evidence file (PNG, JPG, PDF) to upload.", "warning")
            return redirect(url_for("org_evidence_upload"))

        if not allowed_file(file.filename):
            flash("Invalid format. Approved formats: PNG, JPG, JPEG, WEBP.", "danger")
            return redirect(url_for("org_evidence_upload"))

        raw_filename = secure_filename(file.filename)
        unique_name = f"org_{org_id}_c{challenge_id or 0}_{uuid.uuid4().hex[:8]}_{raw_filename}"
        saved_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
        file.save(saved_path)
        file_size = os.path.getsize(saved_path)
        submission_date = datetime.now().strftime("%Y-%m-%d")

        # Submit to database
        res = database.submit_org_evidence(
            org_id=org_id,
            challenge_id=challenge_id,
            activity_record_id=activity_record_id,
            submitted_by_user_id=user_id,
            file_path=unique_name,
            file_name=raw_filename,
            file_size=file_size,
            submission_date=submission_date,
            notes=notes
        )

        if res.get("success"):
            sub_id = res["submission_id"]
            # Analyze image features using Computer Vision Engine
            img_analysis = ai_verifier.analyze_image_features(
                file_path=saved_path,
                challenge_title="Enterprise Utility & Operations Verification",
                category="energy",
                user_notes=notes,
                original_filename=raw_filename
            )
            conn = database.get_db_connection()
            cursor = conn.cursor()
            ai_status = "verified" if img_analysis["is_valid"] else "needs_review"
            ai_conf = img_analysis["confidence"]
            ai_rep = f"AI Vision Audit: {img_analysis['decision']} ({ai_conf}% confidence). {img_analysis['report']}"
            cursor.execute("""
            UPDATE org_evidence_submissions
            SET ai_status = ?, ai_confidence = ?, ai_analysis_report = ?
            WHERE id = ?
            """, (ai_status, ai_conf, ai_rep, sub_id))
            conn.commit()
            conn.close()

            flash("Institutional evidence uploaded and verified by AI Vision Engine! Ready for administrator sign-off.", "success")
            return redirect(url_for("org_evidence_review"))
        else:
            flash(res["message"], "danger")

    challenges = database.get_org_challenges(org_id)
    activity_records = database.get_org_activity_records(org_id)[:10]

    return render_template(
        "org_evidence_upload.html",
        org=org,
        challenges=challenges,
        activity_records=activity_records,
        page_title="Upload Institutional Evidence & Utility Proof"
    )


@app.route("/org/evidence/review")
def org_evidence_review():
    """Admin review console for organizational evidence submissions."""
    org_id = get_current_org_id()
    org = database.get_organization(org_id)
    submissions = database.get_org_evidence_submissions(org_id)

    return render_template(
        "org_evidence_review.html",
        org=org,
        submissions=submissions,
        page_title="Organization Evidence Review & ESG Audit Console"
    )


@app.route("/org/evidence/approve/<int:submission_id>", methods=["POST"])
def org_evidence_approve(submission_id):
    reviewer_user_id = session.get("user_id", 2)
    reviewer_notes = request.form.get("reviewer_notes", "Verified official institutional documentation.")
    res = database.review_org_evidence(submission_id, reviewer_user_id, "approved", reviewer_notes)
    if res["success"]:
        flash(res["message"], "success")
    else:
        flash(res["message"], "danger")
    return redirect(url_for("org_evidence_review"))


@app.route("/org/evidence/reject/<int:submission_id>", methods=["POST"])
def org_evidence_reject(submission_id):
    reviewer_user_id = session.get("user_id", 2)
    reviewer_notes = request.form.get("reviewer_notes", "Evidence incomplete or unreadable.")
    res = database.review_org_evidence(submission_id, reviewer_user_id, "rejected", reviewer_notes)
    if res["success"]:
        flash("Submission rejected with feedback notes.", "info")
    else:
        flash(res["message"], "danger")
    return redirect(url_for("org_evidence_review"))


@app.route("/org/rewards")
def org_rewards():
    """
    Dedicated Organization Rewards Portal.
    Mandatory Rule: 1,000-Point Milestone Threshold required to unlock redemptions.
    Displays organization points balance, progress toward 1,000 points, catalog, and active voucher redemptions.
    """
    org_id = get_current_org_id()
    org = database.get_organization(org_id)
    points_summary = database.get_org_points_summary(org_id)
    rewards_catalog = database.get_org_rewards_catalog(org_id)

    return render_template(
        "org_rewards.html",
        org=org,
        points_summary=points_summary,
        rewards_catalog=rewards_catalog,
        threshold=database.ORG_REWARD_THRESHOLD,
        page_title="Organization Decarbonization Rewards & ESG Grants"
    )


@app.route("/org/rewards/redeem/<int:reward_id>", methods=["POST"])
def org_rewards_redeem(reward_id):
    """Executes reward redemption enforcing the mandatory 1,000-point threshold."""
    org_id = get_current_org_id()
    user_id = session.get("user_id", 2)

    res = database.redeem_org_reward(org_id, user_id, reward_id)
    if res["success"]:
        flash(f"Redemption Successful! Generated Voucher Code: {res['voucher_code']}. {res['message']}", "success")
    else:
        flash(res["message"], "danger")

    return redirect(url_for("org_rewards"))


@app.route("/org/reports")
def org_reports():
    """
    Executive Sustainability & ESG Carbon Audit Report.
    Formal Scope 1, Scope 2, Scope 3 breakdown, intensity metrics, and inter-organization benchmarking leaderboard.
    """
    org_id = get_current_org_id()
    org = database.get_organization(org_id)
    summary = calculations.get_org_emission_summary(org_id)
    departments = database.get_org_departments(org_id)
    sites = database.get_org_sites(org_id)
    leaderboard = database.get_all_organizations_leaderboard()

    return render_template(
        "org_reports.html",
        org=org,
        summary=summary,
        departments=departments,
        sites=sites,
        leaderboard=leaderboard,
        page_title=f"Executive ESG Sustainability Report — {org['org_name']}"
    )


# ==========================================================
# 13. ERROR HANDLERS
# ==========================================================
@app.errorhandler(413)
def request_entity_too_large(error):
    flash("Uploaded file exceeds the maximum 5MB size limit. Please upload a smaller compressed image.", "danger")
    return redirect(url_for("evidence_upload")), 413


@app.errorhandler(404)
def not_found_error(error):
    return render_template("base.html", page_title="Page Not Found"), 404


if __name__ == "__main__":
    print("==================================================================")
    print("GREEN PULSE - Carbon Footprint Tracking & Reduction Platform")
    print("Tagline: 'Track Your Impact. Make Every Action Count.'")
    print("Server running locally on http://127.0.0.1:5000")
    print("==================================================================")
    app.run(debug=True, host="127.0.0.1", port=5000)
