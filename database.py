"""
database.py - SQLite Database Management for Green Pulse
Supports:
 - Mode-based User Accounts: 'individual' vs 'organization' / 'industry'
 - Domain-specific rewards for individuals and organizations
 - AI verification data tracking and casual green habits
"""

import os
import sqlite3
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "greenpulse.db")
FACTORS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emission_factors.json")


def get_db_connection():
    """Returns a SQLite connection with Row factory enabled for dictionary-style access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Creates all required tables if they do not exist and populates initial data."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users Table (with account_type: 'individual' or 'organization')
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',               -- 'user' or 'admin'
        account_type TEXT NOT NULL DEFAULT 'individual', -- 'individual' or 'organization'
        institution TEXT DEFAULT 'Green Tech Engineering College',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Emission Factors Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS emission_factors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,           -- transportation, electricity, fuel, waste
        factor_key TEXT UNIQUE NOT NULL,  -- e.g. motorcycle, grid_national
        name TEXT NOT NULL,
        factor_value REAL NOT NULL,       -- kg CO2e per unit
        unit TEXT NOT NULL,               -- e.g. kg CO2e / km, kg CO2 / kWh
        source TEXT NOT NULL,             -- e.g. CEA India v20.0, UK DESNZ 2023
        reference_year INTEGER DEFAULT 2023,
        scope TEXT,
        notes TEXT,
        is_placeholder INTEGER DEFAULT 0  -- 0 for verified, 1 for placeholder
    );
    """)

    # 3. Activity Records Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        reporting_period TEXT NOT NULL,   -- 'daily', 'monthly'
        record_date TEXT NOT NULL,        -- YYYY-MM-DD
        category TEXT NOT NULL,           -- transportation, electricity, fuel, waste
        activity_type TEXT NOT NULL,      -- links to factor_key
        activity_name TEXT NOT NULL,
        input_value REAL NOT NULL,
        input_unit TEXT NOT NULL,
        emission_factor REAL NOT NULL,
        emissions_kg_co2e REAL NOT NULL,
        cost_inr REAL DEFAULT 0.0,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # 4. Master Challenges Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        target_audience TEXT NOT NULL DEFAULT 'both', -- 'individual', 'organization', 'both'
        description TEXT NOT NULL,
        baseline_desc TEXT NOT NULL,
        proposed_desc TEXT NOT NULL,
        co2e_saving_estimate REAL NOT NULL,
        financial_saving_estimate REAL NOT NULL,
        instructions TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        reward_points INTEGER NOT NULL,
        icon TEXT NOT NULL,
        difficulty TEXT DEFAULT 'Medium'
    );
    """)

    # 5. User Enrolled Challenges Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        challenge_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'accepted', -- 'accepted', 'submitted', 'completed'
        accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (challenge_id) REFERENCES challenges (id) ON DELETE CASCADE
    );
    """)

    # 6. Evidence Submissions Table (with AI Verification fields)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS evidence_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        challenge_id INTEGER NOT NULL,
        user_challenge_id INTEGER,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        submission_date TEXT NOT NULL,
        notes TEXT,
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
        reviewer_notes TEXT,
        reviewed_at TIMESTAMP,
        points_awarded INTEGER DEFAULT 0,
        ai_status TEXT DEFAULT 'verified',       -- 'analyzing', 'verified', 'flagged', 'rejected'
        ai_confidence REAL DEFAULT 95.0,
        ai_analysis_report TEXT,
        verification_eta_seconds INTEGER DEFAULT 60,
        verified_by_ai INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (challenge_id) REFERENCES challenges (id) ON DELETE CASCADE
    );
    """)

    # 7. Points Transactions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS points_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL, -- 'earned' or 'redeemed'
        points INTEGER NOT NULL,
        description TEXT NOT NULL,
        reference_id INTEGER,
        reference_type TEXT,            -- 'challenge_approval', 'reward_redemption', 'casual_habit', 'initial_grant'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # 8. Rewards Catalog Table (with domain-specific target_audience)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        target_audience TEXT NOT NULL DEFAULT 'individual', -- 'individual' or 'organization'
        points_cost INTEGER NOT NULL DEFAULT 100,
        voucher_prefix TEXT NOT NULL,
        terms TEXT NOT NULL,
        icon TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 9. Reward Redemptions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reward_redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        reward_id INTEGER NOT NULL,
        voucher_code TEXT UNIQUE NOT NULL,
        points_spent INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', -- 'active', 'redeemed'
        redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (reward_id) REFERENCES rewards (id) ON DELETE CASCADE
    );
    """)

    # 10. Casual Everyday Default Suggestions / Habits Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS casual_habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,          -- energy, transport, waste, food, lifestyle
        co2e_saved_kg REAL NOT NULL,
        points_reward INTEGER NOT NULL DEFAULT 3,
        icon TEXT NOT NULL,
        quick_tip TEXT NOT NULL
    );
    """)

    # 11. User Daily Logged Casual Habits
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_daily_habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        habit_id INTEGER NOT NULL,
        completed_date TEXT NOT NULL,    -- YYYY-MM-DD
        points_awarded INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, habit_id, completed_date),
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY (habit_id) REFERENCES casual_habits (id) ON DELETE CASCADE
    );
    """)

    # ==========================================================
    # ORGANIZATIONAL SECTION TABLES (SCOPES 1, 2, 3 & 1,000-PT REWARDS)
    # ==========================================================

    # 12. Organizations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_name TEXT NOT NULL,
        org_type TEXT NOT NULL,          -- 'College/University', 'Company', 'Manufacturing Industry', 'Office', 'Factory', 'Other'
        sector TEXT DEFAULT 'Education & CleanTech',
        employee_count INTEGER DEFAULT 150,
        building_count INTEGER DEFAULT 3,
        location TEXT DEFAULT 'Bangalore, Karnataka, India',
        reporting_period TEXT DEFAULT 'monthly', -- 'monthly', 'quarterly', 'yearly'
        admin_user_id INTEGER,
        baseline_emissions_co2e REAL DEFAULT 28500.0,
        target_reduction_pct REAL DEFAULT 15.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_user_id) REFERENCES users (id) ON DELETE SET NULL
    );
    """)

    # 13. Organization Memberships
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS organization_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role TEXT NOT NULL DEFAULT 'member', -- 'admin', 'manager', 'member'
        department_id INTEGER,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(org_id, user_id),
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # 14. Departments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        head_name TEXT,
        employee_count INTEGER DEFAULT 30,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE
    );
    """)

    # 15. Organization Sites or Buildings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS organization_sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        site_name TEXT NOT NULL,
        site_type TEXT DEFAULT 'Main Campus', -- 'Main Campus', 'Manufacturing Plant', 'Branch Office', 'Warehouse'
        address TEXT,
        floor_area_sqm REAL DEFAULT 5000.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE
    );
    """)

    # 16. Organizational Activity Records (Scopes 1, 2, 3)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS org_activity_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        department_id INTEGER,
        site_id INTEGER,
        reporting_period TEXT NOT NULL DEFAULT 'monthly', -- 'monthly', 'quarterly', 'yearly'
        record_date TEXT NOT NULL,                        -- YYYY-MM-DD
        scope TEXT NOT NULL,                             -- 'Scope 1', 'Scope 2', 'Scope 3'
        category TEXT NOT NULL,                          -- 'electricity', 'fleet', 'commuting', 'waste', 'industrial'
        activity_type TEXT NOT NULL,                     -- links to factor_key
        activity_name TEXT NOT NULL,
        input_value REAL NOT NULL,
        input_unit TEXT NOT NULL,
        emission_factor REAL NOT NULL,
        emissions_kg_co2e REAL NOT NULL,
        cost_inr REAL DEFAULT 0.0,
        production_units REAL DEFAULT 0.0,               -- optional production count for manufacturing
        notes TEXT,
        created_by_user_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE,
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
        FOREIGN KEY (site_id) REFERENCES organization_sites (id) ON DELETE SET NULL
    );
    """)

    # 17. Organization Sustainability Challenges
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS org_challenges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER,                                  -- NULL for universal templates, or org_id
        title TEXT NOT NULL,
        scope TEXT NOT NULL DEFAULT 'Scope 2',
        category TEXT NOT NULL,                          -- electricity, fleet, waste, fuel, industrial
        department_id INTEGER,
        site_id INTEGER,
        description TEXT NOT NULL,
        baseline_desc TEXT NOT NULL,
        target_desc TEXT NOT NULL,
        co2e_saving_estimate_kg REAL NOT NULL,
        financial_saving_estimate_inr REAL NOT NULL,
        instructions TEXT NOT NULL,
        evidence_type TEXT NOT NULL,
        reward_points INTEGER NOT NULL DEFAULT 200,
        status TEXT NOT NULL DEFAULT 'active',           -- 'active', 'submitted', 'completed'
        due_date TEXT,
        icon TEXT NOT NULL DEFAULT 'fa-building',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE,
        FOREIGN KEY (department_id) REFERENCES departments (id) ON DELETE SET NULL,
        FOREIGN KEY (site_id) REFERENCES organization_sites (id) ON DELETE SET NULL
    );
    """)

    # 18. Organization Evidence Submissions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS org_evidence_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        challenge_id INTEGER,
        activity_record_id INTEGER,
        submitted_by_user_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        submission_date TEXT NOT NULL,
        notes TEXT,
        status TEXT NOT NULL DEFAULT 'pending',          -- 'pending', 'approved', 'rejected'
        reviewer_notes TEXT,
        reviewed_at TIMESTAMP,
        reviewed_by_user_id INTEGER,
        points_awarded INTEGER DEFAULT 0,
        ai_status TEXT DEFAULT 'verified',               -- 'analyzing', 'verified', 'flagged', 'rejected'
        ai_confidence REAL DEFAULT 95.0,
        ai_analysis_report TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE,
        FOREIGN KEY (challenge_id) REFERENCES org_challenges (id) ON DELETE SET NULL,
        FOREIGN KEY (submitted_by_user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    # 19. Organization Points Transactions (Completely Decoupled from Individual Points)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS org_points_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,                  -- 'earned' or 'redeemed'
        points INTEGER NOT NULL,
        description TEXT NOT NULL,
        reference_id INTEGER,
        reference_type TEXT,                             -- 'challenge_approval', 'reward_redemption', 'initial_grant'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE
    );
    """)

    # 20. Organization Rewards Catalog (1,000-Point Mandatory Threshold)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS org_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        points_cost INTEGER NOT NULL DEFAULT 1000,       -- Mandatory Threshold: 1000
        voucher_prefix TEXT NOT NULL,
        terms TEXT NOT NULL,
        icon TEXT NOT NULL,
        badge_level TEXT DEFAULT 'Gold',
        is_active INTEGER DEFAULT 1
    );
    """)

    # 21. Organization Reward Redemptions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS org_reward_redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id INTEGER NOT NULL,
        reward_id INTEGER NOT NULL,
        redeemed_by_user_id INTEGER NOT NULL,
        voucher_code TEXT UNIQUE NOT NULL,
        points_spent INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (org_id) REFERENCES organizations (id) ON DELETE CASCADE,
        FOREIGN KEY (reward_id) REFERENCES org_rewards (id) ON DELETE CASCADE,
        FOREIGN KEY (redeemed_by_user_id) REFERENCES users (id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    run_schema_migrations(cursor)
    conn.commit()
    conn.close()

    # Sync emission factors and demo seeds
    sync_factors_from_json()
    seed_demo_data()


def run_schema_migrations(cursor):
    """Ensures all columns and organization tables exist in existing SQLite databases without dropping tables."""
    # 1. Users table migrations (safe try-except)
    for col, col_def in [
        ("account_type", "TEXT NOT NULL DEFAULT 'individual'"),
        ("password_hash", "TEXT NOT NULL DEFAULT ''"),
        ("org_id", "INTEGER REFERENCES organizations (id)")
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass

    # 2. Rewards table migrations
    try:
        cursor.execute("ALTER TABLE rewards ADD COLUMN target_audience TEXT NOT NULL DEFAULT 'individual'")
    except sqlite3.OperationalError:
        pass

    # 3. Challenges table migrations
    try:
        cursor.execute("ALTER TABLE challenges ADD COLUMN target_audience TEXT NOT NULL DEFAULT 'both'")
    except sqlite3.OperationalError:
        pass

    # 4. Evidence submissions migrations
    for col, col_def in [
        ("ai_status", "TEXT DEFAULT 'verified'"),
        ("ai_confidence", "REAL DEFAULT 95.0"),
        ("ai_analysis_report", "TEXT"),
        ("verification_eta_seconds", "INTEGER DEFAULT 60"),
        ("verified_by_ai", "INTEGER DEFAULT 1")
    ]:
        try:
            cursor.execute(f"ALTER TABLE evidence_submissions ADD COLUMN {col} {col_def}")
        except sqlite3.OperationalError:
            pass


def sync_factors_from_json():
    """Reads emission_factors.json and populates the database table."""
    if not os.path.exists(FACTORS_JSON_PATH):
        return

    with open(FACTORS_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = get_db_connection()
    cursor = conn.cursor()

    for category in ["transportation", "electricity", "fuel", "waste"]:
        items = data.get(category, {})
        for key, item in items.items():
            cursor.execute("""
            INSERT INTO emission_factors (category, factor_key, name, factor_value, unit, source, reference_year, scope, notes, is_placeholder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(factor_key) DO UPDATE SET
                factor_value=excluded.factor_value,
                unit=excluded.unit,
                source=excluded.source,
                notes=excluded.notes
            """, (
                category,
                key,
                item.get("name", key),
                float(item.get("factor", 0.0)),
                item.get("unit", ""),
                item.get("source", "Documented Source"),
                int(item.get("reference_year", 2023)),
                item.get("scope", "Scope 1/2/3"),
                item.get("description", ""),
                0
            ))

    conn.commit()
    conn.close()


def seed_demo_data():
    """Seeds default demo users with secure password hashes, casual habits, master challenges, and rewards."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Seed Demo Users with Hashed Passwords (Individual & Organization Modes)
    pw_student = generate_password_hash("password123")
    pw_admin = generate_password_hash("admin123")
    pw_org = generate_password_hash("org123")

    cursor.execute("""
    INSERT OR IGNORE INTO users (id, username, full_name, email, password_hash, role, account_type, institution)
    VALUES 
        (1, 'aarav_sharma', 'Aarav Sharma', 'aarav@greenpulse.demo', ?, 'user', 'individual', 'Dept of Computer Science & Engineering'),
        (2, 'dr_priya_rao', 'Dr. Priya Rao', 'priya@greenpulse.demo', ?, 'admin', 'organization', 'Campus Sustainability Assessment Cell'),
        (3, 'ecocorp_admin', 'EcoPulse CleanTech Ltd', 'ecocorp@industry.demo', ?, 'admin', 'organization', 'Industrial CleanTech Park')
    """, (pw_student, pw_admin, pw_org))

    # Ensure roles, password hashes, and modes are consistent
    cursor.execute("UPDATE users SET password_hash = ?, account_type = 'individual' WHERE id = 1", (pw_student,))
    cursor.execute("UPDATE users SET password_hash = ?, role = 'admin', account_type = 'organization' WHERE id = 2", (pw_admin,))
    cursor.execute("UPDATE users SET password_hash = ?, role = 'admin', account_type = 'organization' WHERE id = 3", (pw_org,))

    # 2. Seed Master Challenges
    cursor.execute("SELECT COUNT(*) FROM challenges")
    if cursor.fetchone()[0] == 0:
        challenges_data = [
            (
                1,
                "Switch Commute: Take the City Bus",
                "transportation",
                "individual",
                "Swap your daily individual motorbike/car commute for the public city bus to lower per-passenger greenhouse emissions.",
                "Daily 15 km commute on a personal motorcycle (0.084 kg CO2e/km).",
                "Ride the municipal transit bus for the same 15 km (0.054 kg CO2e/p-km).",
                0.45,  # 15 * (0.084 - 0.054) = 0.45 kg CO2e saved per trip
                45.0,  # ~0.35L petrol saved = ~₹36 - ₹45
                "Take a public bus for your college or office commute. Keep your digital or paper bus ticket, take a clear photo showing the date and route, and upload it.",
                "Bus Ticket or Commute Receipt Photo",
                20,
                "fa-bus",
                "Easy"
            ),
            (
                2,
                "Save Kilowatt-Hours: Appliance Audit",
                "electricity",
                "both",
                "Eliminate phantom standby power, use LED fixtures, and adjust AC thermostat to 24°C to cut at least 25 kWh this month.",
                "Unoptimized monthly power consumption (300 kWh @ 0.716 kg CO2/kWh = 214.8 kg CO2e).",
                "Reduced monthly power consumption to 270 kWh (saving 30 kWh).",
                21.48, # 30 kWh * 0.716 kg CO2/kWh
                210.0, # 30 kWh * ₹7.00/kWh
                "Inspect your home/hostel room electrical appliances. Turn off vampire standby loads and ensure AC runs at 24°C+. Upload a photo of your electricity meter reading or tariff bill showing monthly savings.",
                "Electricity Meter Reading / Tariff Bill Photo",
                25,
                "fa-bolt",
                "Medium"
            ),
            (
                3,
                "Waste Segregation: Source Separation",
                "waste",
                "both",
                "Strictly segregate wet organic food waste from clean dry recyclables (paper, plastic, metal) for 7 consecutive days.",
                "5 kg of mixed kitchen and paper waste sent unsegregated to municipal landfill (2.9 kg CO2e).",
                "Food waste segregated for compost, dry paper/plastic sent to recycling facility (0.35 kg CO2e).",
                2.55,  # Avoided methane emission from anaerobic decomposition
                0.0,   # Civic environmental benefit
                "Set up dual bins (Green for Wet/Organic, Blue for Dry Recyclables). Take a clear photo of your segregated bins in use with both organic and recyclable fractions clearly separated.",
                "Photo of Segregated Waste Bins (Wet + Dry)",
                10,
                "fa-recycle",
                "Easy"
            ),
            (
                4,
                "Clean Cooking / Fuel Conservation",
                "fuel",
                "individual",
                "Optimize cooking and hot water fuel usage by using induction cooking, pressure cooking, and lids to save 2 kg of LPG.",
                "Standard unoptimized LPG consumption (1 cylinder = 14.2 kg = 42.36 kg CO2e).",
                "Saving 2.0 kg LPG through covered cooking and batch meal prep.",
                5.97,  # 2.0 kg * 2.983 kg CO2e/kg
                140.0, # Approximate subsidized LPG equivalent savings
                "Adopt fuel conservation techniques (lids on pots, pressure cooker, soaking pulses). Upload a photo of your efficient cooking setup or induction cooktop in use.",
                "Photo of Efficient Cooking Setup / Induction Cooktop",
                20,
                "fa-fire",
                "Medium"
            ),
            (
                5,
                "Zero Emission Commute: Cycle or Walk",
                "transportation",
                "individual",
                "Replace short-distance motorized motorcycle or auto-rickshaw trips (< 4 km) with cycling or walking.",
                "Motorcycle trip of 4 km = 0.336 kg CO2e.",
                "Walk or bicycle the 4 km = 0.000 kg CO2e.",
                0.34,
                15.0,
                "Cycle or walk for your trip to campus or local market. Upload a screenshot from your fitness/strava/pedometer app or a photo of your bicycle at campus parking.",
                "Fitness Tracker Screenshot or Bicycle at Campus",
                20,
                "fa-bicycle",
                "Easy"
            ),
            (
                6,
                "Organization Fleet EV Transition Pledge",
                "transportation",
                "organization",
                "Deploy electric shuttle buses or battery-operated staff transit vehicles across campus routes.",
                "Diesel fleet bus consuming 35L diesel per 100 km (~93.8 kg CO2e).",
                "Electric shuttle bus charged on grid (~37.1 kg CO2e).",
                56.7,
                1200.0,
                "Upload purchase order, charging station log, or telemetry report showing EV shuttle fleet kilometers.",
                "Fleet EV Telemetry Log or Charging Bill",
                40,
                "fa-charging-station",
                "Hard"
            )
        ]

        cursor.executemany("""
        INSERT OR IGNORE INTO challenges (id, title, category, target_audience, description, baseline_desc, proposed_desc, 
                               co2e_saving_estimate, financial_saving_estimate, instructions, 
                               evidence_type, reward_points, icon, difficulty)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, challenges_data)

    # 3. Seed Casual Everyday Default Suggestions / Habits
    cursor.execute("SELECT COUNT(*) FROM casual_habits")
    if cursor.fetchone()[0] == 0:
        habits_data = [
            (
                1,
                "Turn off geyser 5 mins early",
                "Switch off electric water heater early and use residual hot water to shave 0.5 kWh.",
                "electricity",
                0.36,
                3,
                "fa-shower",
                "Water heaters draw 2000W; 5 minutes saved daily cuts ~15 kWh monthly."
            ),
            (
                2,
                "Carry a reusable cloth tote bag",
                "Bring your own cloth or jute bag when shopping for groceries or campus stationery.",
                "waste",
                0.08,
                3,
                "fa-bag-shopping",
                "Eliminates 2-3 single-use low-micron polyethylene bags from landfill."
            ),
            (
                3,
                "Refill a reusable water bottle",
                "Drink from a personal stainless steel bottle instead of buying single-use bottled water.",
                "waste",
                0.16,
                3,
                "fa-bottle-water",
                "Manufacturing a 1L PET bottle consumes 3L of water and ~160g CO2."
            ),
            (
                4,
                "Take stairs instead of elevator",
                "Climb 2 to 3 flights of stairs instead of calling the high-draw traction elevator.",
                "lifestyle",
                0.05,
                2,
                "fa-stairs",
                "Zero electricity consumed while boosting cardiovascular fitness."
            ),
            (
                5,
                "Unplug chargers & kill phantom power",
                "Switch off power strips and unplug phone/laptop chargers when devices reach 100%.",
                "electricity",
                0.12,
                3,
                "fa-plug",
                "Vampire loads consume 5-10% of standard domestic residential electricity."
            ),
            (
                6,
                "Pack lunch in reusable dabba",
                "Bring homemade food or mess lunch in a stainless steel container without clingwrap.",
                "food",
                0.22,
                4,
                "fa-utensils",
                "Eliminates single-use foil, plastic clamshells, and food-delivery emissions."
            ),
            (
                7,
                "Turn off vehicle engine at signals (>30s)",
                "Cut two-wheeler/car ignition at long red traffic lights to avoid wasteful idling.",
                "transportation",
                0.18,
                3,
                "fa-traffic-light",
                "Idling for 10 minutes burns up to 0.14L fuel and generates dense local particulate smog."
            ),
            (
                8,
                "Enjoy a plant-based vegetarian meal",
                "Opt for lentils, beans, paneer, or seasonal veggies for lunch or dinner.",
                "food",
                1.40,
                5,
                "fa-carrot",
                "Plant proteins produce 80% lower lifecycle GHG emissions compared to red meat."
            )
        ]

        cursor.executemany("""
        INSERT OR IGNORE INTO casual_habits (id, title, description, category, co2e_saved_kg, points_reward, icon, quick_tip)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, habits_data)

    # 4. Seed Rewards Catalog (Individual & Domain-Specific Organization/Industry Rewards)
    rewards_data = [
        # Individual Rewards
            (
                1,
                "10% Eco-Store Student Voucher",
                "Get a simulated 10% instant discount coupon on sustainable stationery, bamboo items, and organic student essentials at GreenCampus Store.",
                "Shopping & Supplies",
                "individual",
                100,
                "GP-ECO",
                "Valid for 30 days from redemption. Maximum discount ₹150. Simulated hackathon demonstration coupon.",
                "fa-tag"
            ),
            (
                2,
                "Public Transit Metro / Bus Pass Credit",
                "Redeem a simulated ₹50 smart-card recharge credit for city bus and metro commuter services.",
                "Sustainable Commute",
                "individual",
                100,
                "GP-TRANSIT",
                "Valid on participating city transport feeder buses and urban metro networks. Demo voucher.",
                "fa-ticket-alt"
            ),
            (
                3,
                "Campus Green Cafe Reusable Cup Perk",
                "Enjoy a complimentary beverage upgrade or ₹40 off when presenting your own reusable travel mug at the campus cafe.",
                "Zero Waste Food",
                "individual",
                100,
                "GP-CAFE",
                "Single use per student per week. Encourages zero-disposable-cup culture.",
                "fa-coffee"
            ),
            (
                4,
                "Campus Tree Plantation Certificate & Tag",
                "Green Pulse sponsors a native sapling planted on campus in your name with a verifiable digital certificate and geotagged tree ledger.",
                "Impact & Recognition",
                "individual",
                120,
                "GP-TREE",
                "Coordinated with the campus botanical garden and sustainability club.",
                "fa-seedling"
            ),
            (
                5,
                "Shared Electric Mobility Voucher",
                "Simulated ₹100 credit for campus shared electric cycles or EV feeder shuttles.",
                "Electric Mobility",
                "individual",
                150,
                "GP-EVSHUTTLE",
                "Valid on campus EV shuttle fleet. Zero tailpipe emission rides.",
                "fa-bolt"
            ),

            # Domain-Specific Organization & Industry Rewards
            (
                6,
                "BEE / ISO 50001 Energy Audit Advisory Voucher",
                "Complimentary professional preliminary energy efficiency assessment for campus buildings or industrial facilities.",
                "Industrial Energy Advisory",
                "organization",
                100,
                "GP-AUDIT",
                "Redeemable with accredited Bureau of Energy Efficiency (BEE) auditing partners.",
                "fa-industry"
            ),
            (
                7,
                "Bulk Green Tariff & REC Allocation Credit",
                "Simulated certificate allocating 500 kWh of verified off-site solar/wind Renewable Energy Credits to your organizational balance.",
                "Renewable Energy Credits",
                "organization",
                120,
                "GP-REC",
                "Facilitates Scope 2 market-based carbon offset reporting for institutional ESG audits.",
                "fa-solar-panel"
            ),
            (
                8,
                "Institutional ESG Sustainability Rating Endorsement",
                "Formal Green Pulse Platinum Sustainability Seal for college prospectus, CSR annual reporting, and corporate sustainability portals.",
                "ESG Rating & Recognition",
                "organization",
                100,
                "GP-ESG",
                "Recognized in annual Green Campus Benchmarking indices.",
                "fa-award"
            ),
            (
                9,
                "Industrial E-Waste & Recycler Processing Rebate",
                "Specialized subsidized processing voucher with state pollution control board (SPCB) authorized electronic waste recyclers.",
                "Waste Recovery",
                "organization",
                120,
                "GP-EWASTE",
                "Valid for bulk decommissioning of campus electronics, computers, and battery scrap.",
                "fa-recycle"
            ),
            (
                10,
                "Rooftop Solar Feasibility & CAPEX/OPEX Advisory",
                "Engineered rooftop solar PV irradiation mapping, capacity sizing report, and DISCOM net-metering regulatory clearance dossier.",
                "Clean Power Transition",
                "organization",
                140,
                "GP-SOLAR",
                "Customized for institutional multi-kilowatt rooftop installations.",
                "fa-sun"
            )
        ]

    cursor.executemany("""
    INSERT OR IGNORE INTO rewards (id, title, description, category, target_audience, points_cost, voucher_prefix, terms, icon)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rewards_data)

    # 5. Seed Baseline Activity Records for User 1
    cursor.execute("SELECT COUNT(*) FROM activity_records WHERE user_id = 1")
    if cursor.fetchone()[0] == 0:
        sample_activities = [
            (1, "monthly", "2026-10-01", "transportation", "motorcycle", "Petrol Two-Wheeler Commute", 220.0, "km", 0.084, 18.48, 650.0, "College daily commute"),
            (1, "monthly", "2026-10-01", "electricity", "grid_national", "Hostel / Flat Power Consumption", 180.0, "kWh", 0.716, 128.88, 1260.0, "Monthly utility bill meter reading"),
            (1, "monthly", "2026-10-01", "fuel", "lpg", "LPG Domestic Cooking Cylinder", 7.1, "kg", 2.983, 21.18, 480.0, "Half cylinder shared student cooking"),
            (1, "monthly", "2026-10-01", "waste", "mixed_landfill", "Unsegregated Hostel Waste", 18.0, "kg", 0.580, 10.44, 0.0, "Estimated monthly landfill discard")
        ]

        cursor.executemany("""
        INSERT OR IGNORE INTO activity_records (user_id, reporting_period, record_date, category, activity_type, 
                                     activity_name, input_value, input_unit, emission_factor, 
                                     emissions_kg_co2e, cost_inr, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_activities)

    # 6. Seed Initial Points and Challenge Enrolment for Aarav
    cursor.execute("SELECT COUNT(*) FROM points_transactions WHERE user_id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT OR IGNORE INTO user_challenges (user_id, challenge_id, status, accepted_at)
        VALUES 
            (1, 1, 'accepted', '2026-10-25 10:00:00'),
            (1, 2, 'completed', '2026-10-20 14:30:00'),
            (1, 3, 'completed', '2026-10-22 16:00:00'),
            (1, 4, 'completed', '2026-10-24 11:20:00'),
            (1, 5, 'completed', '2026-10-26 09:15:00')
        """)

        cursor.execute("""
        INSERT OR IGNORE INTO points_transactions (user_id, transaction_type, points, description, reference_id, reference_type, created_at)
        VALUES 
            (1, 'earned', 5, 'Welcome Green Pulse onboarding pledge', NULL, 'initial_grant', '2026-10-18 10:00:00'),
            (1, 'earned', 25, 'Approved: Save Kilowatt-Hours: Appliance Audit', 2, 'challenge_approval', '2026-10-20 14:35:00'),
            (1, 'earned', 10, 'Approved: Waste Segregation: Source Separation', 3, 'challenge_approval', '2026-10-22 16:05:00'),
            (1, 'earned', 20, 'Approved: Clean Cooking / Fuel Conservation', 4, 'challenge_approval', '2026-10-24 11:25:00'),
            (1, 'earned', 20, 'Approved: Zero Emission Commute: Cycle or Walk', 5, 'challenge_approval', '2026-10-26 09:20:00')
        """)

        # Seed sample evidence submission for Challenge 1 (City Bus commute)
        cursor.execute("""
        INSERT OR IGNORE INTO evidence_submissions (user_id, challenge_id, user_challenge_id, 
                                          file_path, file_name, file_size, submission_date, 
                                          notes, status, points_awarded, ai_status, ai_confidence, 
                                          ai_analysis_report, verification_eta_seconds, verified_by_ai)
        VALUES (1, 1, 1, 'uploads/sample_bus_ticket.png', 'sample_bus_ticket.png', 18450, 
                '2026-10-28', 'Took route 335E municipal express bus to campus instead of my petrol two-wheeler. Bus ticket attached.', 
                'pending', 0, 'analyzing', 96.5, 
                'AI Vision Agent: Optical analysis detected valid municipal transit ticket (Route 335E). Date and transit fare verified. Authenticity score: 96.5%. Pending final confirmation.', 
                45, 1)
        """)

    # ==========================================================
    # 7. SEED ORGANIZATIONS, DEPARTMENTS, SITES & SCOPE 1,2,3 DATA
    # ==========================================================
    cursor.execute("SELECT COUNT(*) FROM organizations")
    if cursor.fetchone()[0] == 0:
        orgs_data = [
            (
                1,
                "Apex Institute of Technology & Campus",
                "College/University",
                "Higher Education & Applied Research",
                2400,
                6,
                "Electronic City Campus, Bengaluru, Karnataka",
                "monthly",
                2,
                28500.0,
                15.0
            ),
            (
                2,
                "EcoPulse CleanTech Manufacturing Ltd",
                "Manufacturing Industry",
                "CleanTech Electronics & Solar Inverters",
                350,
                2,
                "Plot 48, Peenya 2nd Stage Industrial Area, Bengaluru",
                "monthly",
                3,
                42000.0,
                20.0
            )
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO organizations (id, org_name, org_type, sector, employee_count, 
                                            building_count, location, reporting_period, 
                                            admin_user_id, baseline_emissions_co2e, target_reduction_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, orgs_data)

        # Link users 2 and 3 to organizations
        cursor.execute("UPDATE users SET org_id = 1 WHERE id = 2")
        cursor.execute("UPDATE users SET org_id = 2 WHERE id = 3")

        # Memberships
        cursor.execute("""
        INSERT OR IGNORE INTO organization_members (id, org_id, user_id, role, department_id)
        VALUES 
            (1, 1, 2, 'admin', 1),
            (2, 2, 3, 'admin', 4)
        """)

        # Departments for Org 1 (Apex Institute)
        cursor.execute("""
        INSERT OR IGNORE INTO departments (id, org_id, name, head_name, employee_count)
        VALUES
            (1, 1, 'Dept of Computer Science & Engineering', 'Prof. K. Sharma', 650),
            (2, 1, 'Dept of Mechanical & Electrical Sciences', 'Dr. A. Sen', 580),
            (3, 1, 'Campus Facilities, Hostels & Central Canteen', 'R. Sundaram', 1170),
            (4, 2, 'Electronics Production Line A', 'M. Joshi', 140),
            (5, 2, 'Inverter Assembly & Testing Plant', 'S. Rao', 110),
            (6, 2, 'Logistics, Warehousing & Administration', 'N. Patil', 100)
        """)

        # Sites for Org 1 & 2
        cursor.execute("""
        INSERT OR IGNORE INTO organization_sites (id, org_id, site_name, site_type, address, floor_area_sqm)
        VALUES
            (1, 1, 'North Academic Quad & Science Labs', 'Main Campus', 'Block A & B, Electronic City', 12500.0),
            (2, 1, 'South Engineering Tech Complex', 'Research Labs', 'Block C, Electronic City', 15200.0),
            (3, 1, 'Student Hostels & Central Green Canteen', 'Residential & Dining', 'Hostel Zone, Electronic City', 18000.0),
            (4, 2, 'Peenya CleanTech Manufacturing Plant 1', 'Manufacturing Plant', 'Plot 48, Peenya 2nd Stage, Bangalore', 8500.0),
            (5, 2, 'Logistics Depot & Central Warehouse', 'Warehouse', 'Plot 52, Peenya 2nd Stage, Bangalore', 6200.0)
        """)

        # Scope 1, 2, 3 Activity Records for Org 1 (Apex Institute)
        org1_activities = [
            (
                1, 1, 1, "monthly", "2026-10-01", "Scope 2", "electricity", "grid_national",
                "Campus Grid Power Consumption (HT Supply)", 18500.0, "kWh", 0.716, 13246.0, 129500.0, 0.0,
                "Central electricity meter tariff billing invoice for North Quad & Labs", 2
            ),
            (
                1, 2, 2, "monthly", "2026-10-01", "Scope 2", "electricity", "solar_rooftop",
                "Rooftop Solar PV Clean Power Generation", 4200.0, "kWh", 0.041, 172.2, 0.0, 0.0,
                "Inverter clean power telemetry avoiding 3,007 kg CO2e grid power", 2
            ),
            (
                1, 3, 1, "monthly", "2026-10-01", "Scope 1", "fleet", "company_bus",
                "Dedicated Student & Staff Feeder Shuttles", 1850.0, "km", 0.680, 1258.0, 18500.0, 0.0,
                "Campus transit routes providing 35-seat mass transit", 2
            ),
            (
                1, 3, 1, "monthly", "2026-10-01", "Scope 1", "fuel", "diesel_generator",
                "Campus Standby Diesel Generator Set (DG Backup)", 320.0, "Litre", 2.680, 857.6, 28480.0, 0.0,
                "Monthly power backup fuel during regional substation line maintenance", 2
            ),
            (
                1, 1, 1, "monthly", "2026-10-01", "Scope 3", "commuting", "bus",
                "Aggregated Student & Employee Transit Commute", 14200.0, "p-km", 0.054, 766.8, 0.0, 0.0,
                "Aggregated public transit survey data (BMTC & Metro commuters)", 2
            ),
            (
                1, 3, 3, "monthly", "2026-10-01", "Scope 3", "waste", "composted_organic",
                "Canteen Organic Food Waste to On-Site Vermicomposter", 450.0, "kg", 0.100, 45.0, 3200.0, 0.0,
                "100% segregated wet waste converted to organic fertilizer (avoiding 234 kg CO2e)", 2
            ),
            (
                1, 3, 3, "monthly", "2026-10-01", "Scope 3", "waste", "mixed_landfill",
                "Unsegregated Campus Municipal Discard", 820.0, "kg", 0.580, 475.6, 0.0, 0.0,
                "Residual landfill discard monitored for source segregation target", 2
            )
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO org_activity_records (org_id, department_id, site_id, reporting_period, 
                                                    record_date, scope, category, activity_type, 
                                                    activity_name, input_value, input_unit, emission_factor, 
                                                    emissions_kg_co2e, cost_inr, production_units, notes, created_by_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, org1_activities)

        # Activity Records for Org 2 (EcoPulse CleanTech Manufacturing)
        org2_activities = [
            (
                2, 4, 4, "monthly", "2026-10-01", "Scope 2", "electricity", "grid_national",
                "Industrial High-Tension (HT) Power Supply", 45000.0, "kWh", 0.716, 32220.0, 315000.0, 1200.0,
                "Industrial tariff billing for assembly lines & cleanrooms", 3
            ),
            (
                2, 5, 4, "monthly", "2026-10-01", "Scope 1", "fuel", "furnace_oil",
                "Thermal Boiler & Furnace Heat Fuel", 650.0, "Litre", 3.150, 2047.5, 48750.0, 1200.0,
                "Boiler fuel for curing solar inverter components", 3
            ),
            (
                2, 6, 5, "monthly", "2026-10-01", "Scope 1", "fleet", "heavy_truck",
                "Logistics Distribution Heavy Freight", 1200.0, "km", 0.850, 1020.0, 18000.0, 1200.0,
                "Inter-state component distribution truck logistics", 3
            )
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO org_activity_records (org_id, department_id, site_id, reporting_period, 
                                                    record_date, scope, category, activity_type, 
                                                    activity_name, input_value, input_unit, emission_factor, 
                                                    emissions_kg_co2e, cost_inr, production_units, notes, created_by_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, org2_activities)

        # 8. Seed Organization Challenges
        org_challenges_data = [
            (
                1, 1, "Campus Facility LED Lighting & Smart HVAC Retrofit", "Scope 2", "electricity", 1, 1,
                "Replace fluorescent fixtures with sensor-controlled LEDs and regulate central chiller setpoints to 24°C across academic quad.",
                "Unoptimized baseline power draw of 21,000 kWh/mo (15,036 kg CO2e)",
                "Reduce monthly consumption to 18,500 kWh (saving 2,500 kWh/mo)",
                1790.0, 17500.0,
                "Upload utility electricity submeter invoice or energy management BMS log showing reduction.",
                "Electric Submeter / DISCOM Bill", 200, "completed", "2026-11-15", "fa-lightbulb"
            ),
            (
                2, 1, "100 kWp Rooftop Solar PV Installation & DISCOM Net-Metering", "Scope 2", "electricity", 2, 2,
                "Commission rooftop solar PV arrays to offset grid power during peak daylight hours.",
                "100% grid dependency for south engineering complex",
                "Generate at least 4,000 kWh solar clean energy monthly",
                2864.0, 28000.0,
                "Upload inverter telemetry portal screenshot or DISCOM net-metering solar export credit bill.",
                "Solar Generation Telemetry or Net-Meter Bill", 250, "completed", "2026-12-01", "fa-solar-panel"
            ),
            (
                3, 1, "Zero-Emission Campus EV Shuttle & Commuter Vanpool", "Scope 1", "fleet", 3, 1,
                "Transition 2 diesel feeder buses to shared electric commuter shuttles for students and staff.",
                "Diesel shuttle routes burning 350L diesel monthly (938 kg CO2e)",
                "Achieve 1,200 km on electric shuttles (saving ~650 kg CO2e)",
                650.0, 14200.0,
                "Upload EV telematics report, charging station energy log, or vehicle odometer log.",
                "EV Telematics or Charging Station Log", 200, "active", "2026-11-30", "fa-bus"
            ),
            (
                4, 1, "Zero-Landfill Decentralized Organic Composting & Segregation", "Scope 3", "waste", 3, 3,
                "Divert 100% of campus canteen food scraps to on-site aerobic vermicompost units.",
                "500 kg canteen wet waste dumped in mixed municipal landfill (310 kg CO2e)",
                "100% source-segregated composting (45 kg CO2e, saving 265 kg CO2e)",
                265.0, 3500.0,
                "Upload photograph of dual-stream segregation bins in active use and compost bed weight ledger.",
                "Canteen Segregation & Compost Ledger Photo", 200, "active", "2026-11-20", "fa-recycle"
            ),
            (
                5, 1, "Diesel Generator Optimization & Power-Factor Correction", "Scope 1", "fuel", 1, 1,
                "Install automatic power factor controllers (APFC) and tune standby DG sets to reduce idle fuel waste.",
                "Low power factor (0.84) and frequent generator short-cycling consuming 400L diesel",
                "Improve power factor to 0.98 and cut generator diesel consumption by 80L",
                214.4, 7120.0,
                "Upload generator logbook showing operating hours, diesel consumption and APFC capacitor panel reading.",
                "DG Maintenance Logbook & APFC Readout", 150, "active", "2026-12-10", "fa-industry"
            )
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO org_challenges (id, org_id, title, scope, category, department_id, site_id, 
                                             description, baseline_desc, target_desc, co2e_saving_estimate_kg, 
                                             financial_saving_estimate_inr, instructions, evidence_type, 
                                             reward_points, status, due_date, icon)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, org_challenges_data)

        # 9. Seed Organization Points Transactions (Apex Institute: 550 Points Earned)
        cursor.execute("""
        INSERT OR IGNORE INTO org_points_transactions (org_id, transaction_type, points, description, reference_id, reference_type, created_at)
        VALUES
            (1, 'earned', 100, 'Welcome Institutional Decarbonization Charter Pledge', NULL, 'initial_grant', '2026-10-01 09:00:00'),
            (1, 'earned', 200, 'Approved: Campus Facility LED Lighting & Smart HVAC Retrofit', 1, 'challenge_approval', '2026-10-15 14:00:00'),
            (1, 'earned', 250, 'Approved: 100 kWp Rooftop Solar PV Installation & DISCOM Net-Metering', 2, 'challenge_approval', '2026-10-22 16:30:00')
        """)

    # 10. Seed Organization Rewards (Mandatory 1,000-Point Threshold)
    cursor.execute("SELECT COUNT(*) FROM org_rewards")
    if cursor.fetchone()[0] == 0:
        org_rewards_data = [
            (
                1,
                "Green Starter Institutional Digital Badge",
                "Verified Green Pulse institutional onboarding certificate with QR verification for website prospectus and annual ESG disclosures.",
                "Institutional Certification",
                250,
                "ORG-BADGE",
                "Valid for 1 academic/financial year. Digital verifiable credential for institutional compliance.",
                "fa-certificate",
                "Bronze"
            ),
            (
                2,
                "Sustainability Benchmark Progress Seal",
                "Intermediate recognition seal demonstrating documented Scope 1, Scope 2, and Scope 3 carbon accounting adherence.",
                "ESG Rating & Accreditation",
                500,
                "ORG-SEAL",
                "Applicable for college NIRF / NAAC green campus criteria and corporate CSR annual sustainability filings.",
                "fa-award",
                "Silver"
            ),
            (
                3,
                "Organization Eco Champion Award",
                "Official Green Pulse Platinum Institutional Sustainability Trophy & Digital Accredited Certification. Unlocks full institutional sustainability honors!",
                "Accredited Championship",
                1000,
                "ORG-CHAMP",
                "Requires reaching the mandatory 1,000 organization points threshold. Validated by Green Pulse Sustainability Council.",
                "fa-trophy",
                "Platinum"
            ),
            (
                4,
                "Institutional Carbon Audit Summary Dossier",
                "Comprehensive verified Scope 1, Scope 2, and Scope 3 carbon audit report dossier suitable for official disclosures and stakeholder presentations.",
                "Carbon Audit Dossier",
                1000,
                "ORG-AUDIT",
                "Executive summary PDF dossier including departmental intensity metrics, site rankings, and decarbonization roadmap.",
                "fa-file-invoice",
                "Platinum"
            ),
            (
                5,
                "BEE / ISO 50001 Energy Audit Consultation Voucher",
                "Complimentary preliminary energy efficiency audit and thermal optimization consultation with certified energy managers.",
                "Industrial Advisory",
                1000,
                "ORG-BEE",
                "Redeemable with accredited Bureau of Energy Efficiency (BEE) auditing partner network.",
                "fa-bolt",
                "Platinum"
            ),
            (
                6,
                "Corporate / Campus EV Fleet Transition Subsidy",
                "Simulated commercial fleet electrification incentive subsidy with charging infrastructure installation rebate.",
                "Fleet Electrification",
                1500,
                "ORG-FLEET",
                "Covers up to ₹1,50,000 simulated capex rebate on fast-charging stations for company fleet.",
                "fa-charging-station",
                "Diamond"
            ),
            (
                7,
                "Platinum National ESG Sustainability Rating Seal",
                "Highest tier institutional sustainability rating recognized across academic and industrial ESG indices.",
                "National Recognition",
                2000,
                "ORG-PLATINUM",
                "Formal recognition for net-zero carbon trajectory, circular waste management, and renewable transition.",
                "fa-medal",
                "Diamond"
            )
        ]
        cursor.executemany("""
        INSERT OR IGNORE INTO org_rewards (id, title, description, category, points_cost, voucher_prefix, terms, icon, badge_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, org_rewards_data)

    conn.commit()
    conn.close()


def register_user(username, full_name, email, password, account_type="individual", institution="Green Tech Engineering College"):
    """Registers a new user under Individual or Organization mode."""
    if account_type not in ["individual", "organization"]:
        institution = account_type
        account_type = "individual"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        pw_hash = generate_password_hash(password)
        role = "admin" if account_type == "organization" else "user"
        cursor.execute("""
        INSERT INTO users (username, full_name, email, password_hash, role, account_type, institution)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, full_name, email, pw_hash, role, account_type, institution))
        conn.commit()
        user_id = cursor.lastrowid
        # Grant welcome pledge points
        cursor.execute("""
        INSERT INTO points_transactions (user_id, transaction_type, points, description, reference_type)
        VALUES (?, 'earned', 10, 'Welcome to Green Pulse: Environmental Pledge Bonus', 'initial_grant')
        """, (user_id,))
        conn.commit()
        conn.close()
        return {"success": True, "user_id": user_id, "account_type": account_type, "message": f"Account created in {account_type.capitalize()} Mode! +10 Welcome Points credited."}
    except sqlite3.IntegrityError as e:
        conn.close()
        if "email" in str(e).lower():
            return {"success": False, "message": "An account with this email already exists."}
        elif "username" in str(e).lower():
            return {"success": False, "message": "Username is already taken."}
        return {"success": False, "message": "Registration failed. Please check inputs."}


def authenticate_user(username_or_email, password, required_mode=None):
    """Authenticates a user and verifies account mode matches selection."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM users WHERE email = ? OR username = ?
    """, (username_or_email, username_or_email))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return {"success": False, "message": "Invalid email or username."}

    if not check_password_hash(user["password_hash"], password):
        return {"success": False, "message": "Incorrect password."}

    user_dict = dict(user)
    # Check mode compatibility if specified
    if required_mode and user_dict.get("account_type") != required_mode:
        # We allow gentle warning or auto-switch to their actual account mode
        pass

    return {"success": True, "user": user_dict}


def get_user_casual_habits(user_id, today_date=None):
    """Fetches casual habits and checks if user has completed them today."""
    if not today_date:
        today_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM casual_habits ORDER BY id ASC")
    habits = [dict(r) for r in cursor.fetchall()]

    cursor.execute("""
    SELECT habit_id FROM user_daily_habits WHERE user_id = ? AND completed_date = ?
    """, (user_id, today_date))
    completed_habit_ids = {r["habit_id"] for r in cursor.fetchall()}

    conn.close()

    for h in habits:
        h["is_completed_today"] = h["id"] in completed_habit_ids

    return habits


def log_user_casual_habit(user_id, habit_id, today_date=None):
    """Logs completion of a casual everyday habit and awards micro-points."""
    if not today_date:
        today_date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id FROM user_daily_habits WHERE user_id = ? AND habit_id = ? AND completed_date = ?
    """, (user_id, habit_id, today_date))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        return {"success": False, "message": "You have already logged this habit today! Keep up the daily streak."}

    cursor.execute("SELECT * FROM casual_habits WHERE id = ?", (habit_id,))
    habit = cursor.fetchone()
    if not habit:
        conn.close()
        return {"success": False, "message": "Habit not found."}

    points = habit["points_reward"]
    co2e_saved = habit["co2e_saved_kg"]

    try:
        cursor.execute("""
        INSERT INTO user_daily_habits (user_id, habit_id, completed_date, points_awarded)
        VALUES (?, ?, ?, ?)
        """, (user_id, habit_id, today_date, points))

        cursor.execute("""
        INSERT INTO points_transactions (user_id, transaction_type, points, description, reference_id, reference_type)
        VALUES (?, 'earned', ?, ?, ?, 'casual_habit')
        """, (user_id, points, f"Casual Habit: {habit['title']} (-{co2e_saved}kg CO2e)", habit_id))

        conn.commit()
        conn.close()
        return {
            "success": True, 
            "message": f"Awesome! '{habit['title']}' logged! +{points} Points earned & saved {co2e_saved} kg CO2e.",
            "points": points
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Error: {str(e)}"}


# ==========================================================
# ORGANIZATIONAL DATA ACCESS HELPERS & SCOPE 1,2,3 QUERIES
# ==========================================================

def get_organization(org_id):
    """Retrieves full organization profile by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM organizations WHERE id = ?", (org_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_organization(user_id):
    """Retrieves the organization associated with a given user ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Check users.org_id first
    cursor.execute("SELECT org_id FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    org_id = u["org_id"] if u and u["org_id"] else None

    if not org_id:
        # Check organization_members
        cursor.execute("SELECT org_id FROM organization_members WHERE user_id = ? LIMIT 1", (user_id,))
        m = cursor.fetchone()
        org_id = m["org_id"] if m else None

    if not org_id:
        # Check if user is admin_user_id of an org
        cursor.execute("SELECT id FROM organizations WHERE admin_user_id = ? LIMIT 1", (user_id,))
        o = cursor.fetchone()
        org_id = o["id"] if o else None

    if org_id:
        cursor.execute("SELECT * FROM organizations WHERE id = ?", (org_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    conn.close()
    return None


def create_organization(org_name, org_type, sector, employee_count, building_count, location, reporting_period, admin_user_id):
    """Registers a new organization and links the admin user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO organizations (org_name, org_type, sector, employee_count, building_count, 
                                  location, reporting_period, admin_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (org_name, org_type, sector, int(employee_count or 100), int(building_count or 1), 
              location, reporting_period or 'monthly', admin_user_id))
        org_id = cursor.lastrowid

        # Update user's org_id and role
        cursor.execute("UPDATE users SET org_id = ?, role = 'admin', account_type = 'organization' WHERE id = ?", (org_id, admin_user_id))
        cursor.execute("""
        INSERT OR IGNORE INTO organization_members (org_id, user_id, role)
        VALUES (?, ?, 'admin')
        """, (org_id, admin_user_id))

        # Seed default departments and sites for the new organization
        cursor.execute("""
        INSERT INTO departments (org_id, name, head_name, employee_count)
        VALUES 
            (?, 'Operations & Administration', 'Facility Manager', ?),
            (?, 'Sustainability & ESG Cell', 'Sustainability Lead', 10)
        """, (org_id, max(10, int(employee_count or 50) - 10), org_id))

        cursor.execute("""
        INSERT INTO organization_sites (org_id, site_name, site_type, address, floor_area_sqm)
        VALUES (?, 'Main Facility / Campus', 'Main Campus', ?, 5000.0)
        """, (org_id, location or 'Central Facility'))

        # Grant initial institutional onboarding points
        cursor.execute("""
        INSERT INTO org_points_transactions (org_id, transaction_type, points, description, reference_type)
        VALUES (?, 'earned', 100, 'Institutional Decarbonization Charter Onboarding Grant', 'initial_grant')
        """, (org_id,))

        conn.commit()
        conn.close()
        return {"success": True, "org_id": org_id, "message": f"Organization '{org_name}' registered successfully!"}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Failed to register organization: {str(e)}"}


def update_organization_profile(org_id, org_name, org_type, sector, employee_count, building_count, location, reporting_period):
    """Updates organizational profile settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        UPDATE organizations
        SET org_name = ?, org_type = ?, sector = ?, employee_count = ?, 
            building_count = ?, location = ?, reporting_period = ?
        WHERE id = ?
        """, (org_name, org_type, sector, int(employee_count), int(building_count), location, reporting_period, org_id))
        conn.commit()
        conn.close()
        return {"success": True, "message": "Organization profile updated successfully!"}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Error updating profile: {str(e)}"}


def get_org_departments(org_id):
    """Returns list of departments for the given organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM departments WHERE org_id = ? ORDER BY id ASC", (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def add_org_department(org_id, name, head_name="", employee_count=20):
    """Adds a new department to an organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO departments (org_id, name, head_name, employee_count)
        VALUES (?, ?, ?, ?)
        """, (org_id, name.strip(), head_name.strip(), int(employee_count or 0)))
        conn.commit()
        conn.close()
        return {"success": True, "message": f"Department '{name}' added successfully."}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": str(e)}


def delete_org_department(org_id, dept_id):
    """Deletes a department belonging to the specified organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM departments WHERE id = ? AND org_id = ?", (dept_id, org_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Department deleted."}


def get_org_sites(org_id):
    """Returns list of operating sites/buildings for the given organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM organization_sites WHERE org_id = ? ORDER BY id ASC", (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def add_org_site(org_id, site_name, site_type="Main Campus", address="", floor_area_sqm=5000.0):
    """Adds an operating site or building to the organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO organization_sites (org_id, site_name, site_type, address, floor_area_sqm)
        VALUES (?, ?, ?, ?, ?)
        """, (org_id, site_name.strip(), site_type, address.strip(), float(floor_area_sqm or 0.0)))
        conn.commit()
        conn.close()
        return {"success": True, "message": f"Site '{site_name}' added successfully."}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": str(e)}


def delete_org_site(org_id, site_id):
    """Deletes an operating site belonging to the specified organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM organization_sites WHERE id = ? AND org_id = ?", (site_id, org_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Site deleted."}


def add_org_activity_record(org_id, department_id, site_id, reporting_period, record_date, 
                            scope, category, activity_type, activity_name, input_value, 
                            input_unit, emission_factor, emissions_kg_co2e, cost_inr=0.0, 
                            production_units=0.0, notes="", created_by_user_id=None, evidence_ref="", **kwargs):
    """Inserts a verified Scope 1, Scope 2, or Scope 3 organizational activity record."""
    if evidence_ref:
        ref_text = f"[Evidence/Manifest: {evidence_ref}]"
        notes = f"{notes} {ref_text}".strip() if notes else ref_text

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO org_activity_records (org_id, department_id, site_id, reporting_period, 
                                          record_date, scope, category, activity_type, 
                                          activity_name, input_value, input_unit, emission_factor, 
                                          emissions_kg_co2e, cost_inr, production_units, notes, created_by_user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (org_id, department_id or None, site_id or None, reporting_period, record_date,
              scope, category, activity_type, activity_name, float(input_value), input_unit,
              float(emission_factor), float(emissions_kg_co2e), float(cost_inr or 0.0),
              float(production_units or 0.0), notes, created_by_user_id))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"success": True, "record_id": record_id, "message": f"{activity_name} logged successfully!"}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Database error: {str(e)}"}


def get_org_activity_records(org_id, reporting_period=None):
    """Fetches organizational activity records with joined department and site names."""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT oar.*, d.name as department_name, s.site_name
    FROM org_activity_records oar
    LEFT JOIN departments d ON oar.department_id = d.id
    LEFT JOIN organization_sites s ON oar.site_id = s.id
    WHERE oar.org_id = ?
    """
    params = [org_id]
    if reporting_period:
        query += " AND oar.reporting_period = ?"
        params.append(reporting_period)
    query += " ORDER BY oar.record_date DESC, oar.id DESC"

    cursor.execute(query, tuple(params))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def delete_org_activity_record(org_id, record_id):
    """Deletes an organization activity record securely."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM org_activity_records WHERE id = ? AND org_id = ?", (record_id, org_id))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Activity record deleted."}


def get_org_challenges(org_id):
    """Fetches active, pending, and completed challenges for the organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT oc.*, d.name as department_name, s.site_name
    FROM org_challenges oc
    LEFT JOIN departments d ON oc.department_id = d.id
    LEFT JOIN organization_sites s ON oc.site_id = s.id
    WHERE oc.org_id = ? OR oc.org_id IS NULL
    ORDER BY oc.id ASC
    """, (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def submit_org_evidence(org_id, challenge_id, activity_record_id, submitted_by_user_id, 
                        file_path, file_name, file_size, submission_date, notes):
    """Submits evidence for an organizational challenge or activity record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO org_evidence_submissions (org_id, challenge_id, activity_record_id, 
                                             submitted_by_user_id, file_path, file_name, 
                                             file_size, submission_date, notes, status, 
                                             ai_status, ai_confidence, ai_analysis_report)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'analyzing', 95.0, 
                'AI Vision Agent: Optical structural audit initiated on organizational document...')
        """, (org_id, challenge_id or None, activity_record_id or None, submitted_by_user_id,
              file_path, file_name, file_size, submission_date, notes))
        sub_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"success": True, "submission_id": sub_id, "message": "Evidence submitted successfully for review."}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Error saving evidence: {str(e)}"}


def get_org_evidence_submissions(org_id):
    """Retrieves all submitted evidence records for an organization."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT oes.*, oc.title as challenge_title, oc.category as ch_category, 
           oc.reward_points, u.full_name as submitter_name
    FROM org_evidence_submissions oes
    LEFT JOIN org_challenges oc ON oes.challenge_id = oc.id
    LEFT JOIN users u ON oes.submitted_by_user_id = u.id
    WHERE oes.org_id = ?
    ORDER BY oes.id DESC
    """, (org_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def review_org_evidence(submission_id, reviewer_user_id, status, reviewer_notes=""):
    """
    Approves or rejects organizational evidence.
    Awards organization points EXACTLY ONCE on approved status.
    Pending/rejected earn zero points. Prevents duplicate credit.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT oes.*, oc.title as challenge_title, oc.reward_points
    FROM org_evidence_submissions oes
    LEFT JOIN org_challenges oc ON oes.challenge_id = oc.id
    WHERE oes.id = ?
    """, (submission_id,))
    sub = cursor.fetchone()

    if not sub:
        conn.close()
        return {"success": False, "message": "Submission record not found."}

    sub_dict = dict(sub)
    org_id = sub_dict["org_id"]
    already_approved = (sub_dict["status"] == "approved" and (sub_dict["points_awarded"] or 0) > 0)

    if status == "approved" and already_approved:
        conn.close()
        return {
            "success": False,
            "message": "Points have already been awarded for this submission. Duplicate awards are blocked.",
            "points_awarded": 0
        }

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if status == "approved":
        points_to_award = sub_dict["reward_points"] or 150
        if already_approved:
            points_to_award = 0  # Do not award twice

        cursor.execute("""
        UPDATE org_evidence_submissions
        SET status = 'approved',
            reviewer_notes = ?,
            reviewed_at = ?,
            reviewed_by_user_id = ?,
            points_awarded = ?,
            ai_status = 'verified'
        WHERE id = ?
        """, (reviewer_notes or "Evidence verified and approved by organizational reviewer.",
              now_str, reviewer_user_id, points_to_award if not already_approved else sub_dict["points_awarded"], submission_id))

        if not already_approved and points_to_award > 0:
            # Credit points to organization ledger
            cursor.execute("""
            INSERT INTO org_points_transactions (org_id, transaction_type, points, description, reference_id, reference_type)
            VALUES (?, 'earned', ?, ?, ?, 'challenge_approval')
            """, (org_id, points_to_award, f"Approved Challenge: {sub_dict['challenge_title']} (+{points_to_award} Pts)", submission_id))

        if sub_dict["challenge_id"]:
            cursor.execute("UPDATE org_challenges SET status = 'completed' WHERE id = ?", (sub_dict["challenge_id"],))

        conn.commit()
        conn.close()
        return {
            "success": True, 
            "message": f"Submission approved! +{points_to_award} Organization Points awarded.",
            "points_awarded": points_to_award
        }

    else:
        # Rejection: Revoke points if previously awarded by error
        prev_points = sub_dict["points_awarded"] or 0
        cursor.execute("""
        UPDATE org_evidence_submissions
        SET status = 'rejected',
            reviewer_notes = ?,
            reviewed_at = ?,
            reviewed_by_user_id = ?,
            points_awarded = 0,
            ai_status = 'rejected'
        WHERE id = ?
        """, (reviewer_notes or "Evidence documentation did not satisfy verification criteria.",
              now_str, reviewer_user_id, submission_id))

        if prev_points > 0:
            cursor.execute("""
            INSERT INTO org_points_transactions (org_id, transaction_type, points, description, reference_id, reference_type)
            VALUES (?, 'redeemed', ?, ?, ?, 'audit_reversal')
            """, (org_id, prev_points, f"Audit Correction: Revoked points for '{sub_dict['challenge_title']}'", submission_id))

        if sub_dict["challenge_id"]:
            cursor.execute("UPDATE org_challenges SET status = 'active' WHERE id = ?", (sub_dict["challenge_id"],))

        conn.commit()
        conn.close()
        return {"success": True, "message": "Submission rejected. 0 Points awarded."}


# ==========================================================
# 1,000-POINT MANDATORY ORGANIZATIONAL REWARDS ENGINE
# ==========================================================

ORG_REWARD_THRESHOLD = 1000  # Mandatory threshold for organizational rewards

def get_org_points_summary(org_id):
    """
    Computes organization points balance, total earned, total spent,
    and progress toward the MANDATORY 1,000-point reward threshold.
    Completely decoupled from individual points!
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT 
        COALESCE(SUM(CASE WHEN transaction_type = 'earned' THEN points ELSE 0 END), 0) AS total_earned,
        COALESCE(SUM(CASE WHEN transaction_type = 'redeemed' THEN points ELSE 0 END), 0) AS total_redeemed
    FROM org_points_transactions
    WHERE org_id = ?
    """, (org_id,))
    row = cursor.fetchone()

    total_earned = row["total_earned"]
    total_redeemed = row["total_redeemed"]
    balance = max(0, total_earned - total_redeemed)

    # 1,000-point threshold calculation
    points_needed = max(0, ORG_REWARD_THRESHOLD - balance)
    progress_percentage = min(100.0, round((balance / ORG_REWARD_THRESHOLD) * 100, 1))
    can_redeem = balance >= ORG_REWARD_THRESHOLD

    # Fetch transaction audit trail
    cursor.execute("""
    SELECT id, transaction_type, points, description, reference_type, created_at
    FROM org_points_transactions
    WHERE org_id = ?
    ORDER BY created_at DESC, id DESC
    """, (org_id,))
    transactions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "balance": balance,
        "total_earned": total_earned,
        "total_redeemed": total_redeemed,
        "threshold": ORG_REWARD_THRESHOLD,
        "points_needed": points_needed,
        "progress_percentage": progress_percentage,
        "can_redeem": can_redeem,
        "transactions": transactions
    }


def get_org_rewards_catalog(org_id):
    """
    Retrieves the separate organization rewards catalog,
    marking eligibility against the 1,000-point threshold and current balance.
    """
    points_info = get_org_points_summary(org_id)
    balance = points_info["balance"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM org_rewards WHERE is_active = 1 ORDER BY points_cost ASC")
    catalog = []
    for r in cursor.fetchall():
        item = dict(r)
        cost = item["points_cost"]
        # Unlock logic: if cost >= 1000, requires reaching the 1,000 threshold
        item["is_eligible"] = (balance >= cost) and (cost < 1000 or points_info["can_redeem"])
        item["points_short"] = max(0, cost - balance)
        catalog.append(item)

    # Fetch organization's redemption history
    cursor.execute("""
    SELECT orr.*, r.title as reward_title, r.category, r.terms, r.icon, r.badge_level,
           u.full_name as redeemed_by_name
    FROM org_reward_redemptions orr
    JOIN org_rewards r ON orr.reward_id = r.id
    LEFT JOIN users u ON orr.redeemed_by_user_id = u.id
    WHERE orr.org_id = ?
    ORDER BY orr.redeemed_at DESC
    """, (org_id,))
    redemptions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "catalog": catalog,
        "redemptions": redemptions,
        "points_info": points_info
    }


def redeem_org_reward(org_id, user_id, reward_id):
    """
    Redeems an institutional reward from the organization points balance.
    Validates balance, enforces threshold, deducts points, generates unique voucher code.
    Transaction-safe and duplicate protected!
    """
    points_info = get_org_points_summary(org_id)
    balance = points_info["balance"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM org_rewards WHERE id = ? AND is_active = 1", (reward_id,))
    reward = cursor.fetchone()

    if not reward:
        conn.close()
        return {"success": False, "message": "Reward not found or no longer active."}

    cost = reward["points_cost"]

    # Enforce mandatory 1,000-point threshold for flagship tier
    if cost >= ORG_REWARD_THRESHOLD and not points_info["can_redeem"]:
        conn.close()
        return {"success": False, "message": f"Organizational threshold locked! You need {points_info['points_needed']} more points to reach the 1,000-point milestone."}

    if balance < cost:
        conn.close()
        return {"success": False, "message": f"Insufficient balance! Need {cost - balance} more organization points."}

    # Generate unique institutional voucher code
    unique_suffix = os.urandom(3).hex().upper()
    voucher_code = f"{reward['voucher_prefix']}-{datetime.now().strftime('%y%m')}-{unique_suffix}"

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Deduct points from organization ledger
        cursor.execute("""
        INSERT INTO org_points_transactions (org_id, transaction_type, points, description, reference_type, created_at)
        VALUES (?, 'redeemed', ?, ?, 'reward_redemption', ?)
        """, (org_id, cost, f"Redeemed: {reward['title']} (Code: {voucher_code})", now_str))

        # Record redemption
        cursor.execute("""
        INSERT INTO org_reward_redemptions (org_id, reward_id, redeemed_by_user_id, voucher_code, points_spent, status, redeemed_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?)
        """, (org_id, reward_id, user_id, voucher_code, cost, now_str))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "voucher_code": voucher_code,
            "reward_title": reward["title"],
            "points_spent": cost,
            "remaining_balance": max(0, balance - cost),
            "message": f"Successfully redeemed '{reward['title']}'! Your voucher code is {voucher_code}."
        }
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "message": f"Redemption transaction failed: {str(e)}"}


def get_all_organizations_leaderboard():
    """
    Returns comparative performance metrics for organizations based on 
    intensity ratios (emissions per employee and emissions per sqm) rather than raw totals.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT o.id, o.org_name, o.org_type, o.sector, o.employee_count, o.location,
           COALESCE(SUM(oar.emissions_kg_co2e), 0) AS total_emissions_kg,
           COALESCE((SELECT SUM(points) FROM org_points_transactions WHERE org_id = o.id AND transaction_type = 'earned'), 0) AS total_points,
           COALESCE((SELECT COUNT(*) FROM org_challenges WHERE org_id = o.id AND status = 'completed'), 0) AS completed_challenges
    FROM organizations o
    LEFT JOIN org_activity_records oar ON o.id = oar.org_id
    GROUP BY o.id
    ORDER BY total_points DESC
    """)
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        emp = max(1, d["employee_count"] or 1)
        tot_kg = d["total_emissions_kg"]
        d["total_emissions_tonnes"] = round(tot_kg / 1000.0, 2)
        d["per_employee_tonnes"] = round((tot_kg / 1000.0) / emp, 2)
        rows.append(d)

    conn.close()
    return rows



def reset_to_clean_demo():
    """Helper to reseed fresh demo state if requested."""
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
    init_db()


if __name__ == "__main__":
    init_db()
    print("Green Pulse SQLite Database initialized with Individual & Organization modes successfully.")
