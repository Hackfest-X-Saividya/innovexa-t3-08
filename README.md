# 🌱 Green Pulse — Carbon Footprint Tracking, Reduction & Rewards Platform

> **“Track Your Impact. Make Every Action Count.”**

Green Pulse is a full-featured, beginner-friendly web application developed for a 24-hour GreenTech & Impact Hackathon. It provides two separate, dedicated operational modes:
1. **Individual Mode:** Designed for students and citizens with personal footprint calculators, everyday habit tracking, and a **100-point reward threshold**.
2. **Organization Mode:** Enterprise ESG portal designed for colleges, universities, corporate offices, and manufacturing industries with **Scope 1, Scope 2, and Scope 3** carbon accounting, multi-stream data logging, departmental allocations, executive audit reporting, and a **mandatory 1,000-point reward threshold**.

---

## 📌 Problem Statement

> *“Individuals, colleges, and organizations contribute to greenhouse gas emissions through transportation, electricity consumption, fuel usage, and waste generation. However, many lack a simple way to estimate their carbon footprint and identify opportunities to reduce emissions. Develop a digital platform that helps users estimate their carbon footprint, understand the main sources of emissions, and adopt more sustainable practices.”*

Green Pulse solves this by closing the loop between carbon estimation, actionable reduction, photo verification, and behavioral rewards:
$$\text{Measure} \longrightarrow \text{Recommend} \longrightarrow \text{Action} \longrightarrow \text{Evidence} \longrightarrow \text{Verify} \longrightarrow \text{Earn Points} \longrightarrow \text{Redeem Rewards} \longrightarrow \text{Audit Progress}$$

---

## 👥 Pre-Seeded Demo Accounts for Judges

| Mode | User Persona | Email / Identifier | Password | Role / Access | Organization |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Individual** | Aarav Sharma | `aarav@greenpulse.demo` | `password123` | Student / User | Dept of CSE |
| **Organization** | Dr. Priya Rao | `priya@greenpulse.demo` | `admin123` | Campus Admin | Apex Institute of Technology & Campus (College) |
| **Organization** | EcoPulse Admin | `ecocorp@industry.demo` | `org123` | Industrial Admin | EcoPulse CleanTech Manufacturing Ltd (Factory) |

*Judge Convenience:* Instant persona switcher available in top header or via `/switch_role/<id>` (1: Aarav, 2: Dr. Priya, 3: EcoPulse).

---

## 🏢 Organization Mode vs Individual Mode Architecture

```text
               GREEN PULSE DUAL-MODE ARCHITECTURE
                         ┌─────────────┐
                         │ Login/Portal│
                         └──────┬──────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                               ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│        INDIVIDUAL MODE        │       │       ORGANIZATION MODE       │
├───────────────────────────────┤       ├───────────────────────────────┤
│ • Personal Carbon Calculator  │       │ • Scopes 1, 2, 3 Data Entry   │
│ • Daily Casual Green Habits   │       │ • Electricity / Grid / Solar  │
│ • Student Bus/Commute Tasks   │       │ • Commercial Fleet / Trucks   │
│ • 100-Point Reward Threshold  │       │ • Aggregated Commute (Scope 3)│
│ • Eco-Store & Canteen Vouchers│       │ • Commercial Waste Diversion  │
│ • Personal Progress Log       │       │ • Boilers, DG Sets & Process  │
│                               │       │ • Departments & Site Facilities│
│                               │       │ • 1,000-Point Reward Threshold│
│                               │       │ • ESG Dossiers & Rating Seals │
│                               │       │ • Executive Benchmarking Board│
└───────────────────────────────┘       └───────────────────────────────┘
```

### 1. Completely Decoupled Points & Reward Milestones
- **Individual Mode:** Threshold is **100 points**. Users start with 80 points, complete daily habits (+3 pts) or transit challenges (+20 pts) to unlock ₹150 vouchers.
- **Organization Mode:** Threshold is **1,000 points**. Organizations start with 550 points and must fulfill institutional challenges (+200 to +350 pts) such as rooftop solar expansions or fleet hybrid transitions to unlock formal ESG audit dossiers and fleet electrification subsidies.
- **Total Isolation:** Organization points are tracked in `org_points_transactions` and individual points in `points_transactions`. Neither impacts the other.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.10+ / 3.14, Flask 3.x
- **Database:** SQLite3 (`greenpulse.db`) with multi-tenant relational integrity (`users`, `organizations`, `departments`, `organization_sites`, `org_activity_records`, `org_challenges`, `org_evidence_submissions`, `org_rewards`, `org_points_transactions`)
- **Calculation Engine:** `calculations.py` with documented CEA India v20.0, UK DESNZ 2023, and IPCC factors
- **AI Verification Engine:** `ai_verifier.py` (Optical feature extraction, HSV color balance, and luminance classification for instant document audits)
- **Frontend:** Semantic HTML5, Responsive Modern CSS (Emerald/Sky/Slate palette), Vanilla JavaScript
- **Visualizations:** Chart.js 4.4 (Category Doughnuts, Departmental Bar Charts, Trend Lines)
- **Automated Tests:** 17 Python `unittest` tests with 100% pass rate

---

## 🗂️ Project File Structure

```text
GreenPulse/
│
├── app.py                   # Main Flask application with Dual-Mode routing & context processors
├── database.py              # SQLite schema, 10 organization tables & demo seed data
├── calculations.py          # Carbon engine: Scopes 1, 2, 3, avoidance math, and intensity metrics
├── recommendations.py       # Dynamic 12-criteria reduction recommendation engine
├── rewards.py               # Points balance & threshold enforcement (100-pt & 1,000-pt)
├── ai_verifier.py           # Computer Vision & optical feature verification engine
├── emission_factors.json    # Standardized, documented factors with CEA/DEFRA/BEE citations
├── requirements.txt         # Dependency specifications
├── README.md                # Comprehensive documentation and hackathon guide
├── run.bat                  # Windows one-click launcher
├── run.ps1                  # PowerShell one-click launcher
│
├── uploads/                 # Secure folder for photo evidence (bills, weighbridge slips)
│
├── static/
│   ├── css/style.css        # Clean, modern sustainability CSS design system
│   └── js/main.js           # Chart.js configs and dynamic calculation previews
│
├── templates/
│   ├── base.html            # Navigation with dynamic mode switcher and user role pill
│   ├── dashboard.html       # Individual user dashboard with habits and calculator
│   ├── org_dashboard.html   # Organization Dashboard with Scopes 1/2/3 & 1,000-pt bar
│   ├── org_activities.html  # Multi-stream enterprise data entry form
│   ├── org_profile.html     # Organization metadata and facility settings
│   ├── org_departments_sites.html # Internal departments and physical operating sites
│   ├── org_challenges.html  # Enterprise decarbonization challenges
│   ├── org_evidence_upload.html # Upload institutional utility proof for AI verification
│   ├── org_evidence_review.html # Admin review console with AI confidence scores
│   ├── org_rewards.html     # Organization Rewards Portal (1,000-pt milestone)
│   ├── org_reports.html     # Executive ESG Sustainability Audit Report & Leaderboard
│   ├── calculator.html      # Individual carbon calculator
│   ├── simulator.html       # Before-and-after scenario reduction simulator
│   ├── recommendations.html # 12-criteria tailored reduction recommendations
│   ├── challenges.html      # Individual challenges catalog
│   ├── evidence.html        # Individual evidence photo upload form
│   ├── admin_review.html    # Individual review console
│   ├── rewards.html         # Individual rewards catalog (100-pt threshold)
│   ├── progress.html        # Historical individual audit log
│   ├── login.html           # Dual-mode sign in portal
│   └── register.html        # Dual-mode account registration
│
└── tests/
    └── test_app.py          # 17 automated unit and integration tests (100% passing)
```

---

## 🚀 How to Run the Application

### Option A: Direct Terminal Command
```bash
# Navigate to the project directory
cd "C:\Users\Bhumika MS\.gemini\antigravity\scratch\GreenPulse"

# Install dependencies (only required once)
pip install -r requirements.txt

# Run the Flask application
python app.py
```
Open your web browser and navigate to: **`http://127.0.0.1:5000`**

### Option B: Windows Explorer Double-Click
- Double-click **`run.bat`** or right-click **`run.ps1`** -> *Run with PowerShell*.

---

## 🧪 Automated Test Suite (100% Pass Rate)

Run the full automated test suite containing 17 comprehensive unit & integration tests:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

**Test Coverage:**
1. Transportation formula validation (Motorcycle, Bus, Metro)
2. CEA India v20.0 National Grid Factor calculation (0.716 kg CO2/kWh)
3. LPG cylinder calculations (14.2 kg @ 2.983 kg/kg)
4. Waste diversion and composting carbon reductions
5. Before-and-After simulator math (Avoided kg CO2e, % reduction)
6. Dynamic 12-criteria recommendations structure
7. **Individual 100-Point threshold** enforcement & voucher generation
8. Duplicate award blocking & audit trail protection
9. User authentication & daily casual habits logging
10. AI Vision Evidence verification & scene rejection for irrelevant photos
11. **Organization Scope 1, 2, 3 calculation engine** (Fleet, Industrial, Electricity, Commuting, Waste)
12. **Organization Mandatory 1,000-Point Threshold** & Points Isolation
13. Organization Evidence Review & +Points Credit
14. Complete integration testing of all 17 web routes

---

## 🏆 Regulatory & Methodological Transparency

- **Scope 1:** Direct emissions from stationary combustion (boilers, generators) and mobile company fleets. Factors referenced from UK DESNZ / DEFRA 2023 and Bureau of Energy Efficiency (BEE) India guidelines.
- **Scope 2:** Indirect emissions associated with purchased grid electricity. Factor: **0.716 kg CO2/kWh** (*Central Electricity Authority India CO2 Baseline Database v20.0*).
- **Scope 3:** Other indirect value chain emissions (Category 7: Employee Commuting, Category 5: Operational Solid Waste).
- *Disclaimer:* Prototype developed for academic and demonstration purposes; not a substitute for statutory third-party ISO 14064 certification.
