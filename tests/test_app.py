"""
test_app.py - Automated Unit & Integration Tests for Green Pulse
Runs out-of-the-box with Python's built-in `unittest` module or `pytest`.
Validates calculation formulas, CEA/DEFRA factors, simulator math,
points threshold (100 pts), duplicate award prevention, and Flask web routes.
"""

import os
import sys
import unittest

# Ensure application modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import calculations
import recommendations
import rewards
import database
from app import app


class GreenPulseTestSuite(unittest.TestCase):
    def setUp(self):
        """Prepares test client and ensures clean seeded database state for each test."""
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.test_client()
        with app.app_context():
            database.reset_to_clean_demo()

    # 1. EMISSION FACTOR & CALCULATION TESTS
    def test_transportation_calculation(self):
        # 15 km on motorcycle @ 0.084 kg CO2e/km = 1.26 kg CO2e
        result = calculations.calculate_transportation("motorcycle", 15.0)
        self.assertEqual(result["emissions_kg_co2e"], 1.26)
        self.assertEqual(result["factor"], 0.084)
        self.assertTrue("UK DESNZ" in result["source"] or "ARAI" in result["source"])

    def test_electricity_cea_grid_calculation(self):
        # 100 kWh @ 0.716 kg CO2/kWh (CEA India v20.0) = 71.6 kg CO2e
        # Cost @ ₹7.00/kWh = ₹700.00
        result = calculations.calculate_electricity(100.0, "grid_national", 7.00)
        self.assertEqual(result["emissions_kg_co2e"], 71.6)
        self.assertEqual(result["cost_inr"], 700.00)
        self.assertEqual(result["factor"], 0.716)
        self.assertIn("Central Electricity Authority", result["source"])

    def test_fuel_lpg_cylinder_calculation(self):
        # 1 cylinder = 14.2 kg @ 2.983 kg CO2e/kg = 42.3586 -> 42.3586 kg CO2e
        result = calculations.calculate_fuel("lpg", 1.0, is_cylinder=True)
        self.assertAlmostEqual(result["emissions_kg_co2e"], 42.36, places=1)
        self.assertEqual(result["factor"], 2.983)

    def test_waste_diversion_calculation(self):
        # 10 kg mixed waste @ 0.58 = 5.8 kg CO2e
        # 10 kg composted waste @ 0.10 = 1.0 kg CO2e
        landfill_res = calculations.calculate_waste("mixed_landfill", 10.0)
        compost_res = calculations.calculate_waste("composted_organic", 10.0)
        self.assertEqual(landfill_res["emissions_kg_co2e"], 5.80)
        self.assertEqual(compost_res["emissions_kg_co2e"], 1.00)
        self.assertLess(compost_res["emissions_kg_co2e"], landfill_res["emissions_kg_co2e"])

    # 2. BEFORE-AND-AFTER SIMULATOR TESTS
    def test_simulator_transportation(self):
        # 15 km motorcycle (1.26 kg) vs 15 km bus (0.81 kg)
        # Avoided = 1.26 - 0.81 = 0.45 kg CO2e
        sim = calculations.simulate_reduction(
            "transportation",
            {"mode": "motorcycle", "distance": 15.0},
            {"mode": "bus", "distance": 15.0}
        )
        self.assertTrue(sim["is_beneficial"])
        self.assertEqual(sim["avoided_kg_co2e"], 0.45)
        self.assertGreater(sim["percentage_reduction"], 0)
        self.assertIn("assumptions", sim)

    def test_simulator_electricity(self):
        # 250 kWh vs 200 kWh (saving 50 kWh @ 0.716 kg/kWh = 35.8 kg CO2e)
        # Bill savings = 50 * ₹7 = ₹350
        sim = calculations.simulate_reduction(
            "electricity",
            {"kwh": 250.0, "tariff_inr": 7.00, "grid_mix": "grid_national"},
            {"kwh": 200.0}
        )
        self.assertTrue(sim["is_beneficial"])
        self.assertEqual(sim["avoided_kg_co2e"], 35.8)
        self.assertEqual(sim["financial_savings_inr"], 350.0)
        self.assertEqual(sim["percentage_reduction"], 20.0)

    # 3. PERSONALIZED RECOMMENDATIONS (12 CRITERIA)
    def test_recommendations_structure(self):
        recs = recommendations.generate_personalized_recommendations(user_id=1)
        self.assertGreater(len(recs), 0)
        first = recs[0]

        # Verify all 12 criteria are present in each recommendation
        required_keys = [
            "title",                   # 1
            "why_recommended",         # 2
            "baseline_activity",       # 3
            "proposed_alternative",    # 4
            "emissions_before",        # 5
            "emissions_after",         # 6
            "emissions_diff",          # 7
            "financial_savings",       # 8
            "instructions",            # 9
            "evidence_type",           # 10
            "reward_points",           # 11
            "status"                   # 12
        ]
        for key in required_keys:
            self.assertIn(key, first, f"Missing required criterion: {key}")

    # 4. POINTS & REWARDS (100 POINTS THRESHOLD & REDEMPTION)
    def test_points_threshold_and_redemption(self):
        # Aarav starts with 80 earned points (seeded demo state)
        summary = rewards.get_user_points_summary(user_id=1)
        self.assertEqual(summary["balance"], 80)
        self.assertEqual(summary["threshold"], 100)
        self.assertEqual(summary["points_needed"], 20)
        self.assertFalse(summary["can_redeem"])

        # Attempt to redeem 100-point reward with insufficient balance should fail
        attempt = rewards.redeem_reward(user_id=1, reward_id=1)
        self.assertFalse(attempt["success"])
        self.assertIn("Insufficient", attempt["message"])

        # Now add 25 points to reach 105 points (> 100 threshold)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO points_transactions (user_id, transaction_type, points, description, reference_type)
        VALUES (1, 'earned', 25, 'Test points grant', 'test')
        """)
        conn.commit()
        conn.close()

        updated = rewards.get_user_points_summary(user_id=1)
        self.assertEqual(updated["balance"], 105)
        self.assertTrue(updated["can_redeem"])

        # Now redeem 100-point reward (id=1: Eco-Store Student Voucher)
        redemption = rewards.redeem_reward(user_id=1, reward_id=1)
        self.assertTrue(redemption["success"])
        self.assertIn("GP-ECO", redemption["voucher_code"])
        self.assertEqual(redemption["points_spent"], 100)
        self.assertEqual(redemption["remaining_balance"], 5)

    # 5. ADMIN APPROVAL & DUPLICATE AWARD PREVENTION
    def test_duplicate_award_prevention(self):
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # Create a fresh pending submission for challenge 1 (worth 20 points)
        cursor.execute("""
        INSERT INTO evidence_submissions (user_id, challenge_id, file_path, file_name, submission_date, notes, status, points_awarded)
        VALUES (1, 1, 'dummy_path.jpg', 'ticket.jpg', '2026-10-28', 'Bus commute', 'pending', 0)
        """)
        sub_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # First approval should succeed and award points
        appr1 = rewards.approve_submission(sub_id, reviewer_id=2, reviewer_notes="Approved valid ticket.")
        self.assertTrue(appr1["success"])
        self.assertEqual(appr1["points_awarded"], 20)

        # Second approval attempt on the same submission MUST be blocked
        appr2 = rewards.approve_submission(sub_id, reviewer_id=2, reviewer_notes="Trying duplicate award.")
        self.assertFalse(appr2["success"])
        self.assertIn("already been awarded", appr2["message"])

    # 6. USER AUTHENTICATION & CASUAL HABITS TESTS
    def test_user_registration_and_authentication(self):
        # Register new user
        reg = database.register_user("test_student", "Test Student", "test@college.edu", "mySecret123", "CSE Dept")
        self.assertTrue(reg["success"])
        self.assertIn("user_id", reg)

        # Authenticate with valid password
        auth_success = database.authenticate_user("test@college.edu", "mySecret123")
        self.assertTrue(auth_success["success"])
        self.assertEqual(auth_success["user"]["username"], "test_student")

        # Reject invalid password
        auth_fail = database.authenticate_user("test@college.edu", "wrongPassword")
        self.assertFalse(auth_fail["success"])

    def test_casual_everyday_habits(self):
        habits = database.get_user_casual_habits(user_id=1)
        self.assertGreaterEqual(len(habits), 6)

        # Log habit 1 (Geyser off 5 mins early)
        log_res = database.log_user_casual_habit(user_id=1, habit_id=1)
        self.assertTrue(log_res["success"])
        self.assertEqual(log_res["points"], 3)

        # Prevent duplicate log on the same date
        log_dup = database.log_user_casual_habit(user_id=1, habit_id=1)
        self.assertFalse(log_dup["success"])

    # 7. AI EVIDENCE VERIFICATION ENGINE TEST (< 2 MIN SLA)
    def test_ai_evidence_verification(self):
        import ai_verifier
        # Valid ticket: Seeded submission 1 has sample_bus_ticket.png
        res = ai_verifier.verify_submission_sync(submission_id=1, force=True)
        self.assertTrue(res["success"])
        self.assertEqual(res["ai_status"], "verified")
        self.assertEqual(res["status"], "approved")
        self.assertGreaterEqual(res["confidence"], 90.0)
        self.assertIn("AI Vision", res["report"])

        # Mismatched input: Kitchen cooking soup pots for a bus commute challenge MUST be rejected
        soup_path = os.path.join(os.path.dirname(__file__), "..", "uploads", "evidence_u2_c1_7bf5cc21.jpg")
        if os.path.exists(soup_path):
            analysis = ai_verifier.analyze_image_features(
                file_path=soup_path,
                challenge_title="Switch Commute: Take the City Bus",
                category="transportation",
                user_notes="cooking in kitchen",
                original_filename="soup_cooking.jpg"
            )
            self.assertFalse(analysis["is_valid"])
            self.assertEqual(analysis["decision"], "REJECTED")
            self.assertIn("Kitchen / Culinary", analysis["report"])

    # 8. FLASK WEB ROUTES INTEGRATION TESTS
    def test_web_routes(self):
        routes = [
            "/",
            "/dashboard",
            "/login",
            "/register",
            "/calculator",
            "/simulator",
            "/simulator?type=electricity",
            "/recommendations",
            "/challenges",
            "/evidence/upload",
            "/admin/review",
            "/rewards",
            "/progress"
        ]
        for r in routes:
            response = self.client.get(r, follow_redirects=True)
            self.assertEqual(response.status_code, 200, f"Route {r} failed with status {response.status_code}")
            data_str = response.data.decode("utf-8", errors="ignore").lower()
            self.assertTrue("green pulse" in data_str)

    # 9. ORGANIZATION SCOPE 1, 2, 3 EMISSION ENGINE TESTS
    def test_org_emission_calculations(self):
        # Scope 1 Fleet: Commercial Van 1,200 km @ 0.240 kg/km = 288.0 kg CO2e
        fleet_res = calculations.calculate_org_fleet("commercial_van", "diesel", distance_km=1200.0)
        self.assertEqual(fleet_res["emissions_kg_co2e"], 288.0)
        self.assertIn("Scope 1", fleet_res["scope"])

        # Scope 1 Industrial: 250 L Diesel Generator @ 2.68 kg/L = 670.0 kg CO2e
        ind_res = calculations.calculate_org_industrial("diesel_generator", 250.0, production_units=500.0)
        self.assertEqual(ind_res["emissions_kg_co2e"], 670.0)
        self.assertEqual(ind_res["emissions_per_unit"], 1.34)
        self.assertIn("Scope 1", ind_res["scope"])

        # Scope 2 Electricity: 18,500 kWh @ 0.716 kg/kWh = 13,246.0 kg CO2e
        elec_res = calculations.calculate_org_electricity(18500.0, "grid_national", tariff_inr=8.20)
        self.assertEqual(elec_res["emissions_kg_co2e"], 13246.0)
        self.assertIn("Scope 2", elec_res["scope"])

        # Scope 3 Commuting: 6,300 passenger-km on city bus @ 0.054 kg/p-km = 340.2 kg CO2e
        comm_res = calculations.calculate_org_commuting("bus", 6300.0)
        self.assertEqual(comm_res["emissions_kg_co2e"], 340.2)
        self.assertIn("Scope 3", comm_res["scope"])

        # Organization Aggregate Summary (Org 1: Apex Institute)
        summary = calculations.get_org_emission_summary(1)
        self.assertIsNotNone(summary)
        self.assertGreater(summary["total_tonnes_co2e"], 0)
        self.assertIn("scope1_pct", summary)
        self.assertIn("scope2_pct", summary)
        self.assertIn("scope3_pct", summary)
        self.assertIn("intensity_per_employee", summary)
        self.assertIn("avoided_tonnes_co2e", summary)

    # 10. ORGANIZATION MANDATORY 1,000-POINT THRESHOLD & ISOLATION TESTS
    def test_org_points_threshold_1000_and_isolation(self):
        # Org 1 starts with 550 earned points (seeded demo state)
        summary = database.get_org_points_summary(org_id=1)
        self.assertEqual(summary["balance"], 550)
        self.assertEqual(summary["threshold"], 1000)
        self.assertEqual(summary["points_needed"], 450)
        self.assertFalse(summary["can_redeem"])

        # Individual points for Aarav should remain untouched (80 points)
        ind_summary = rewards.get_user_points_summary(user_id=1)
        self.assertEqual(ind_summary["balance"], 80)
        self.assertEqual(ind_summary["threshold"], 100)

        # Attempt to redeem 1,000-pt reward below threshold must be rejected
        attempt = database.redeem_org_reward(org_id=1, user_id=2, reward_id=4)
        self.assertFalse(attempt["success"])
        self.assertIn("1,000", attempt["message"])

        # Grant 500 organization points -> new balance = 1,050 pts (> 1,000 threshold)
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO org_points_transactions (org_id, transaction_type, points, description, reference_type)
        VALUES (1, 'earned', 500, 'Campus Rooftop Solar Phase 1 Grant', 'grant')
        """)
        conn.commit()
        conn.close()

        updated_summary = database.get_org_points_summary(org_id=1)
        self.assertEqual(updated_summary["balance"], 1050)
        self.assertTrue(updated_summary["can_redeem"])

        # Now redeem 1,000-pt reward (id=4: Institutional Carbon Audit Summary Dossier)
        redemption = database.redeem_org_reward(org_id=1, user_id=2, reward_id=4)
        self.assertTrue(redemption["success"])
        self.assertIn("ORG-AUDIT", redemption["voucher_code"])
        self.assertEqual(redemption["points_spent"], 1000)
        self.assertEqual(redemption["remaining_balance"], 50)

        # Verify individual points balance is still completely decoupled
        ind_check = rewards.get_user_points_summary(user_id=1)
        self.assertEqual(ind_check["balance"], 80)

    # 11. ORGANIZATION EVIDENCE APPROVAL & DUPLICATE BLOCKING TESTS
    def test_org_evidence_approval_and_points_credit(self):
        # Submit an organizational evidence record
        sub_res = database.submit_org_evidence(
            org_id=1,
            challenge_id=1,
            activity_record_id=None,
            submitted_by_user_id=2,
            file_path="sample_bill.png",
            file_name="solar_inverter_telemetry.png",
            file_size=10240,
            submission_date="2026-10-28",
            notes="Solar microgrid commissioning certificate"
        )
        self.assertTrue(sub_res["success"])
        sub_id = sub_res["submission_id"]

        # First approval awards challenge reward points (+200 points)
        appr1 = database.review_org_evidence(sub_id, reviewer_user_id=2, status="approved", reviewer_notes="Solar certificate verified.")
        self.assertTrue(appr1["success"])
        self.assertEqual(appr1["points_awarded"], 200)

        # Duplicate approval on the same submission must award ZERO additional points
        appr2 = database.review_org_evidence(sub_id, reviewer_user_id=2, status="approved", reviewer_notes="Trying duplicate.")
        self.assertFalse(appr2["success"])
        self.assertIn("already been awarded", appr2["message"])

    # 12. DEDICATED ORGANIZATION WEB ROUTES INTEGRATION TESTS
    def test_org_web_routes(self):
        org_routes = [
            "/mode/switch/organization",
            "/org/dashboard",
            "/org/profile",
            "/org/departments_sites",
            "/org/activities",
            "/org/challenges",
            "/org/evidence/upload",
            "/org/evidence/review",
            "/org/rewards",
            "/org/reports"
        ]
        for r in org_routes:
            response = self.client.get(r, follow_redirects=True)
            self.assertEqual(response.status_code, 200, f"Organization Route {r} failed with status {response.status_code}")
            data_str = response.data.decode("utf-8", errors="ignore").lower()
            self.assertTrue("green pulse" in data_str)

    # 13. ORGANIZATION ACTIVITY ENTRY FORM SUBMISSION (CALCULATE & SAVE RECORD)
    def test_org_activity_form_submission(self):
        # 1. Switch to Organization Mode
        self.client.get("/mode/switch/organization", follow_redirects=True)

        # 2. Submit Electricity Activity Record (15,000 kWh @ 0.716 kg/kWh = 10,740.0 kg CO2e)
        post_elec = self.client.post("/org/activities", data={
            "stream": "electricity",
            "reporting_period": "monthly",
            "record_date": "2026-10-28",
            "department_id": "1",
            "site_id": "1",
            "kwh": "15000",
            "grid_mix": "grid_national",
            "tariff_inr": "8.20",
            "cost_inr": "123000",
            "notes": "Main electrical intake sub-meter audit",
            "evidence_ref": "BESCOM-LT-40291"
        }, follow_redirects=True)
        self.assertEqual(post_elec.status_code, 200)
        self.assertIn("activity recorded in scope 2", post_elec.data.decode("utf-8").lower())

        # 3. Submit Commercial Waste Activity Record with evidence_ref
        post_waste = self.client.post("/org/activities", data={
            "stream": "waste",
            "reporting_period": "monthly",
            "record_date": "2026-10-28",
            "department_id": "1",
            "site_id": "1",
            "waste_key": "mixed_commercial",
            "quantity_kg": "850",
            "notes": "Weekly solid waste weighbridge slip",
            "evidence_ref": "BBMP-WB-88421"
        }, follow_redirects=True)
        self.assertEqual(post_waste.status_code, 200)
        self.assertIn("activity recorded in scope 3", post_waste.data.decode("utf-8").lower())

        # 4. Verify records were inserted in the database with reference note
        records = database.get_org_activity_records(org_id=1)
        found_ref = any("BBMP-WB-88421" in (r["notes"] or "") for r in records)
        self.assertTrue(found_ref, "Evidence reference should be safely recorded in activity notes.")


if __name__ == "__main__":
    unittest.main()
