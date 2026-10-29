"""
calculations.py - Carbon Footprint Calculation Engine for Green Pulse
Calculates greenhouse gas emissions based on activity data and documented emission factors.
Provides complete transparency regarding formulas, units, CEA/DEFRA/IPCC citations,
and powers the Before-and-After reduction simulator.
"""

import json
import os

FACTORS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emission_factors.json")


def load_emission_factors():
    """Loads factor definitions and metadata from emission_factors.json."""
    if os.path.exists(FACTORS_PATH):
        with open(FACTORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def calculate_transportation(mode_key, distance_km):
    """
    Calculates estimated transportation emissions.
    Formula: emissions = distance_km * factor
    Returns dictionary with calculated emissions, factor details, formula, and citation.
    """
    factors_data = load_emission_factors()
    transport_factors = factors_data.get("transportation", {})
    factor_info = transport_factors.get(mode_key)

    if not factor_info:
        # Fallback to general petrol car if key not found
        factor_val = 0.170
        name = "Unknown Transport"
        unit = "kg CO2e / km"
        source = "UK DESNZ / DEFRA 2023"
        scope = "Scope 1 & Scope 3"
        occupancy = 1.0
    else:
        factor_val = float(factor_info.get("factor", 0.0))
        name = factor_info.get("name", mode_key)
        unit = factor_info.get("unit", "kg CO2e / km")
        source = factor_info.get("source", "Documented Source")
        scope = factor_info.get("scope", "Scope 1 & Scope 3")
        occupancy = factor_info.get("occupancy_assumed", 1.0)

    distance = max(0.0, float(distance_km))
    emissions_kg_co2e = round(distance * factor_val, 4)

    return {
        "category": "transportation",
        "activity_type": mode_key,
        "name": name,
        "input_value": distance,
        "input_unit": "km",
        "factor": factor_val,
        "factor_unit": unit,
        "emissions_kg_co2e": emissions_kg_co2e,
        "source": source,
        "scope": scope,
        "occupancy": occupancy,
        "formula": f"{distance} km × {factor_val} {unit} = {emissions_kg_co2e} kg CO2e"
    }


def calculate_electricity(kwh_consumed, grid_mix="grid_national", tariff_inr=7.00):
    """
    Calculates estimated electricity consumption emissions and potential billing cost.
    Formula: emissions = kwh_consumed * factor (CEA Baseline Database)
    Cost: kwh_consumed * tariff_inr
    """
    factors_data = load_emission_factors()
    elec_factors = factors_data.get("electricity", {})
    factor_info = elec_factors.get(grid_mix, elec_factors.get("grid_national", {}))

    factor_val = float(factor_info.get("factor", 0.716))
    name = factor_info.get("name", "India National Grid Average Electricity")
    unit = factor_info.get("unit", "kg CO2 / kWh")
    source = factor_info.get("source", "Central Electricity Authority (CEA) v20.0")
    scope = factor_info.get("scope", "Scope 2")

    kwh = max(0.0, float(kwh_consumed))
    tariff = max(0.0, float(tariff_inr))

    emissions_kg_co2e = round(kwh * factor_val, 4)
    cost_inr = round(kwh * tariff, 2)

    return {
        "category": "electricity",
        "activity_type": grid_mix,
        "name": name,
        "input_value": kwh,
        "input_unit": "kWh",
        "factor": factor_val,
        "factor_unit": unit,
        "emissions_kg_co2e": emissions_kg_co2e,
        "cost_inr": cost_inr,
        "tariff_inr": tariff,
        "source": source,
        "scope": scope,
        "formula": f"{kwh} kWh × {factor_val} {unit} = {emissions_kg_co2e} kg CO2e"
    }


def calculate_fuel(fuel_type, quantity, is_cylinder=False):
    """
    Calculates estimated stationary and mobile fuel emissions.
    Formula: emissions = quantity * factor
    For LPG cylinders, 1 cylinder = 14.2 kg.
    """
    factors_data = load_emission_factors()
    fuel_factors = factors_data.get("fuel", {})
    factor_info = fuel_factors.get(fuel_type, {})

    factor_val = float(factor_info.get("factor", 2.310))
    name = factor_info.get("name", fuel_type)
    unit = factor_info.get("unit", "kg CO2e / unit")
    source = factor_info.get("source", "IPCC 2006 Guidelines / DEFRA")
    scope = factor_info.get("scope", "Scope 1")

    qty = max(0.0, float(quantity))
    if fuel_type == "lpg" and is_cylinder:
        # Convert cylinders to kg
        actual_kg = qty * 14.2
        emissions_kg_co2e = round(actual_kg * factor_val, 4)
        input_unit = "cylinders (14.2 kg each)"
        formula = f"{qty} cylinder(s) ({actual_kg} kg) × {factor_val} kg CO2e/kg = {emissions_kg_co2e} kg CO2e"
    else:
        emissions_kg_co2e = round(qty * factor_val, 4)
        input_unit = "litres" if "litre" in unit else "kg"
        formula = f"{qty} {input_unit} × {factor_val} {unit} = {emissions_kg_co2e} kg CO2e"

    return {
        "category": "fuel",
        "activity_type": fuel_type,
        "name": name,
        "input_value": qty,
        "input_unit": input_unit,
        "factor": factor_val,
        "factor_unit": unit,
        "emissions_kg_co2e": emissions_kg_co2e,
        "source": source,
        "scope": scope,
        "formula": formula
    }


def calculate_waste(waste_type, waste_kg):
    """
    Calculates estimated waste treatment emissions.
    Formula: emissions = waste_kg * factor
    """
    factors_data = load_emission_factors()
    waste_factors = factors_data.get("waste", {})
    factor_info = waste_factors.get(waste_type, {})

    factor_val = float(factor_info.get("factor", 0.580))
    name = factor_info.get("name", waste_type)
    unit = factor_info.get("unit", "kg CO2e / kg")
    source = factor_info.get("source", "IPCC Waste Guidelines / DEFRA 2023")
    scope = factor_info.get("scope", "Scope 3")

    kg = max(0.0, float(waste_kg))
    emissions_kg_co2e = round(kg * factor_val, 4)

    return {
        "category": "waste",
        "activity_type": waste_type,
        "name": name,
        "input_value": kg,
        "input_unit": "kg",
        "factor": factor_val,
        "factor_unit": unit,
        "emissions_kg_co2e": emissions_kg_co2e,
        "source": source,
        "scope": scope,
        "formula": f"{kg} kg × {factor_val} {unit} = {emissions_kg_co2e} kg CO2e"
    }


def simulate_reduction(simulation_type, baseline_inputs, proposed_inputs):
    """
    Before-and-After Carbon Reduction Simulator.
    Compares baseline activity with a proposed sustainable alternative.
    Returns:
      - baseline_emissions
      - proposed_emissions
      - avoided_emissions (kg CO2e)
      - percentage_reduction (%)
      - financial_savings_inr (if applicable)
      - factors & assumptions
    """
    simulation_type = simulation_type.lower()
    result = {
        "simulation_type": simulation_type,
        "baseline": {},
        "proposed": {},
        "avoided_kg_co2e": 0.0,
        "percentage_reduction": 0.0,
        "financial_savings_inr": 0.0,
        "assumptions": "",
        "is_beneficial": True
    }

    if simulation_type == "transportation":
        # baseline: mode and distance
        b_mode = baseline_inputs.get("mode", "motorcycle")
        b_dist = float(baseline_inputs.get("distance", 15.0))
        p_mode = proposed_inputs.get("mode", "bus")
        p_dist = float(proposed_inputs.get("distance", b_dist))

        base_res = calculate_transportation(b_mode, b_dist)
        prop_res = calculate_transportation(p_mode, p_dist)

        avoided = round(base_res["emissions_kg_co2e"] - prop_res["emissions_kg_co2e"], 4)
        pct = round((avoided / base_res["emissions_kg_co2e"] * 100) if base_res["emissions_kg_co2e"] > 0 else 0.0, 1)

        # Estimate fuel cost savings if switching from personal vehicle (petrol ~ ₹102.50/L) to bus/cycle/walk
        factors_data = load_emission_factors()
        meta = factors_data.get("metadata", {})
        petrol_price = meta.get("default_petrol_price_inr", 102.50)

        fin_savings = 0.0
        if b_mode in ["motorcycle", "petrol_car"]:
            # Estimated mileage: motorcycle ~ 45 km/L, petrol car ~ 14 km/L
            mileage = 45.0 if b_mode == "motorcycle" else 14.0
            fuel_saved_litres = b_dist / mileage
            fuel_cost_saved = fuel_saved_litres * petrol_price

            # Deduct bus fare if bus is chosen (~ ₹1.50 per km)
            transit_cost = (p_dist * 1.50) if p_mode == "bus" else (p_dist * 2.0 if p_mode == "metro_rail" else 0.0)
            fin_savings = max(0.0, round(fuel_cost_saved - transit_cost, 2))

        result["baseline"] = base_res
        result["proposed"] = prop_res
        result["avoided_kg_co2e"] = avoided
        result["percentage_reduction"] = pct
        result["financial_savings_inr"] = fin_savings
        result["assumptions"] = (
            f"Compared {base_res['name']} ({base_res['factor']} {base_res['factor_unit']}) "
            f"with {prop_res['name']} ({prop_res['factor']} {prop_res['factor_unit']}). "
            f"Bus factor reflects Indian city transit with 40-passenger occupancy. "
            f"Fuel savings assume ₹{petrol_price}/L petrol minus estimated transit fare."
        )
        result["is_beneficial"] = avoided > 0

    elif simulation_type == "electricity":
        # baseline: kwh and tariff
        b_kwh = float(baseline_inputs.get("kwh", 250.0))
        p_kwh = float(proposed_inputs.get("kwh", 200.0))
        tariff = float(baseline_inputs.get("tariff_inr", 7.00))
        grid = baseline_inputs.get("grid_mix", "grid_national")

        base_res = calculate_electricity(b_kwh, grid, tariff)
        prop_res = calculate_electricity(p_kwh, grid, tariff)

        avoided = round(base_res["emissions_kg_co2e"] - prop_res["emissions_kg_co2e"], 4)
        pct = round((avoided / base_res["emissions_kg_co2e"] * 100) if base_res["emissions_kg_co2e"] > 0 else 0.0, 1)
        fin_savings = round(base_res["cost_inr"] - prop_res["cost_inr"], 2)

        result["baseline"] = base_res
        result["proposed"] = prop_res
        result["avoided_kg_co2e"] = avoided
        result["percentage_reduction"] = pct
        result["financial_savings_inr"] = fin_savings
        result["assumptions"] = (
            f"Grid emission factor: {base_res['factor']} kg CO2/kWh from Central Electricity Authority (CEA) India v20.0. "
            f"Electricity tariff: ₹{tariff:.2f}/kWh. Monthly bill reduction directly proportional to kWh conserved."
        )
        result["is_beneficial"] = avoided > 0

    elif simulation_type == "waste":
        # e.g., Mixed waste to landfill vs Segregating into Composting & Recycling
        b_kg = float(baseline_inputs.get("waste_kg", 20.0))
        p_compost_kg = float(proposed_inputs.get("compost_kg", b_kg * 0.6))
        p_recycle_kg = float(proposed_inputs.get("recycle_kg", b_kg * 0.3))
        p_landfill_kg = max(0.0, b_kg - p_compost_kg - p_recycle_kg)

        base_res = calculate_waste("mixed_landfill", b_kg)

        comp_res = calculate_waste("composted_organic", p_compost_kg)
        rec_res = calculate_waste("segregated_recyclables", p_recycle_kg)
        rem_landfill_res = calculate_waste("mixed_landfill", p_landfill_kg)

        prop_emissions = round(comp_res["emissions_kg_co2e"] + rec_res["emissions_kg_co2e"] + rem_landfill_res["emissions_kg_co2e"], 4)
        avoided = round(base_res["emissions_kg_co2e"] - prop_emissions, 4)
        pct = round((avoided / base_res["emissions_kg_co2e"] * 100) if base_res["emissions_kg_co2e"] > 0 else 0.0, 1)

        result["baseline"] = base_res
        result["proposed"] = {
            "name": f"Segregated Waste ({p_compost_kg}kg Compost + {p_recycle_kg}kg Recycled + {p_landfill_kg}kg Landfill)",
            "emissions_kg_co2e": prop_emissions,
            "category": "waste"
        }
        result["avoided_kg_co2e"] = avoided
        result["percentage_reduction"] = pct
        result["financial_savings_inr"] = 0.0
        result["assumptions"] = (
            "Composting organic waste aerobically prevents anaerobic methanogenesis (decay to CH4 in dumpsites). "
            "Clean recycling diverts raw material extraction. Factors from IPCC Chapter 5: Waste Guidelines."
        )
        result["is_beneficial"] = avoided > 0

    return result


# ==========================================================
# ORGANIZATIONAL EMISSION CALCULATIONS (SCOPES 1, 2, 3)
# ==========================================================

def calculate_org_electricity(kwh_consumed, grid_mix="grid_national", tariff_inr=7.00):
    """Scope 2: Organizational Purchased Electricity Calculation."""
    base = calculate_electricity(kwh_consumed, grid_mix, tariff_inr)
    base["scope"] = "Scope 2 (Indirect emissions from purchased electricity - GHG Protocol)"
    base["emissions_tonnes_co2e"] = round(base["emissions_kg_co2e"] / 1000.0, 4)
    return base


def calculate_org_fleet(vehicle_type, *args, fuel_type="diesel", distance_km=0.0, fuel_litres=0.0, **kwargs):
    """Scope 1: Company Owned Vehicle Fleet & Business Logistics."""
    for arg in args:
        if isinstance(arg, str):
            fuel_type = arg
        elif isinstance(arg, (int, float)):
            if distance_km == 0.0:
                distance_km = float(arg)
            elif fuel_litres == 0.0:
                fuel_litres = float(arg)
    if "liters" in kwargs:
        fuel_litres = float(kwargs["liters"])
    if "distance" in kwargs:
        distance_km = float(kwargs["distance"])

    factors_data = load_emission_factors()
    trans_factors = factors_data.get("transportation", {})
    fuel_factors = factors_data.get("fuel", {})

    if fuel_litres > 0:
        fuel_key = "diesel_direct" if "diesel" in fuel_type.lower() else ("petrol_direct" if "petrol" in fuel_type.lower() else "cng")
        f_info = fuel_factors.get(fuel_key, fuel_factors.get("diesel_direct", {}))
        factor_val = float(f_info.get("factor", 2.68))
        unit = f_info.get("unit", "kg CO2e / litre")
        emissions = round(fuel_litres * factor_val, 4)
        name = f"Company Fleet ({fuel_litres}L {f_info.get('name', 'Fuel')})"
        input_val = fuel_litres
        input_u = "Litres"
    else:
        f_info = trans_factors.get(vehicle_type, trans_factors.get("commercial_van", {}))
        factor_val = float(f_info.get("factor", 0.240))
        unit = f_info.get("unit", "kg CO2e / km")
        emissions = round(distance_km * factor_val, 4)
        name = f"Company Fleet ({f_info.get('name', vehicle_type)})"
        input_val = distance_km
        input_u = "km"

    return {
        "category": "fleet",
        "scope": "Scope 1 (Direct Fleet Mobile Combustion)",
        "activity_type": vehicle_type,
        "name": name,
        "input_value": input_val,
        "input_unit": input_u,
        "factor": factor_val,
        "factor_unit": unit,
        "emissions_kg_co2e": emissions,
        "emissions_tonnes_co2e": round(emissions / 1000.0, 4),
        "source": f_info.get("source", "DEFRA / MoRTH Fleet Standard"),
        "formula": f"{input_val} {input_u} × {factor_val} {unit} = {emissions} kg CO2e"
    }


def calculate_org_commuting(mode_key, total_passenger_km):
    """Scope 3: Aggregated Employee Commuting."""
    base = calculate_transportation(mode_key, total_passenger_km)
    base["category"] = "commuting"
    base["scope"] = "Scope 3 (Category 7: Employee Commuting - Aggregated Transit Data)"
    base["emissions_tonnes_co2e"] = round(base["emissions_kg_co2e"] / 1000.0, 4)
    return base


def calculate_org_waste(waste_key, quantity_kg):
    """Scope 3: Organizational Solid Waste Disposal & Treatment."""
    base = calculate_waste(waste_key, quantity_kg)
    base["scope"] = "Scope 3 (Category 5: Waste Generated in Operations - IPCC Guidelines)"
    base["emissions_tonnes_co2e"] = round(base["emissions_kg_co2e"] / 1000.0, 4)
    return base


def calculate_org_industrial(fuel_type, quantity, production_units=0.0):
    """Scope 1: Stationary Combustion (Boilers, DG Sets, Furnaces)."""
    factors_data = load_emission_factors()
    fuel_factors = factors_data.get("fuel", {})
    f_info = fuel_factors.get(fuel_type, fuel_factors.get("diesel_generator", {}))

    factor_val = float(f_info.get("factor", 2.68))
    unit = f_info.get("unit", "kg CO2e / unit")
    emissions = round(float(quantity) * factor_val, 4)

    intensity = round(emissions / production_units, 4) if production_units > 0 else 0.0

    return {
        "category": "industrial",
        "scope": "Scope 1 (Direct Stationary Combustion & Process Operations)",
        "activity_type": fuel_type,
        "name": f_info.get("name", fuel_type),
        "input_value": float(quantity),
        "input_unit": unit.split("/")[-1].strip(),
        "factor": factor_val,
        "factor_unit": unit,
        "emissions_kg_co2e": emissions,
        "emissions_tonnes_co2e": round(emissions / 1000.0, 4),
        "production_units": float(production_units),
        "emissions_per_unit": intensity,
        "source": f_info.get("source", "BEE / CPCB Baseline"),
        "formula": f"{quantity} × {factor_val} {unit} = {emissions} kg CO2e ({intensity} kg/unit)"
    }


def get_org_emission_summary(org_id):
    """
    Aggregates all organizational activity records into Scopes 1, 2, 3,
    categories, departments, sites, baseline comparison, and Chart.js metrics.
    """
    import database
    org = database.get_organization(org_id)
    if not org:
        return None

    records = database.get_org_activity_records(org_id)

    scope1_kg = 0.0
    scope2_kg = 0.0
    scope3_kg = 0.0

    category_breakdown = {
        "electricity": 0.0,
        "fleet": 0.0,
        "commuting": 0.0,
        "waste": 0.0,
        "fuel": 0.0,
        "industrial": 0.0
    }

    dept_breakdown = {}
    site_breakdown = {}
    total_energy_kwh = 0.0
    total_cost_inr = 0.0
    total_production_units = 0.0

    for r in records:
        em_kg = float(r["emissions_kg_co2e"] or 0.0)
        scope = r.get("scope", "Scope 2")
        cat = r.get("category", "electricity").lower()

        if "scope 1" in scope.lower():
            scope1_kg += em_kg
        elif "scope 2" in scope.lower():
            scope2_kg += em_kg
        else:
            scope3_kg += em_kg

        category_breakdown[cat] = category_breakdown.get(cat, 0.0) + em_kg

        # Dept
        dept_name = r.get("department_name") or "Campus Wide / Unassigned"
        dept_breakdown[dept_name] = dept_breakdown.get(dept_name, 0.0) + em_kg

        # Site
        site_name = r.get("site_name") or "Main Campus / Plant"
        site_breakdown[site_name] = site_breakdown.get(site_name, 0.0) + em_kg

        # Energy & Cost
        if cat == "electricity":
            total_energy_kwh += float(r.get("input_value") or 0.0)
        total_cost_inr += float(r.get("cost_inr") or 0.0)
        total_production_units += float(r.get("production_units") or 0.0)

    total_kg = scope1_kg + scope2_kg + scope3_kg
    total_tonnes = round(total_kg / 1000.0, 3)

    # Baseline & Avoidance metrics
    baseline_kg = float(org.get("baseline_emissions_co2e") or 28500.0)
    avoided_kg = max(0.0, round(baseline_kg - total_kg, 2))
    pct_reduction = round((avoided_kg / baseline_kg) * 100.0, 1) if baseline_kg > 0 else 0.0

    # Intensity Ratios
    emp_count = max(1, int(org.get("employee_count") or 100))
    tonnes_per_employee = round(total_tonnes / emp_count, 3)
    kg_per_unit = round(total_kg / total_production_units, 2) if total_production_units > 0 else 0.0

    # Scope percentages
    s1_pct = round((scope1_kg / total_kg * 100) if total_kg > 0 else 0.0, 1)
    s2_pct = round((scope2_kg / total_kg * 100) if total_kg > 0 else 0.0, 1)
    s3_pct = round((scope3_kg / total_kg * 100) if total_kg > 0 else 0.0, 1)

    return {
        "org": org,
        "records_count": len(records),
        "total_emissions_kg": round(total_kg, 2),
        "total_emissions_kg_co2e": round(total_kg, 2),
        "total_emissions_tonnes": total_tonnes,
        "total_tonnes_co2e": total_tonnes,
        "scope1_kg": round(scope1_kg, 2),
        "scope1_tonnes": round(scope1_kg / 1000.0, 3),
        "scope1_tonnes_co2e": round(scope1_kg / 1000.0, 3),
        "scope1_pct": s1_pct,
        "scope2_kg": round(scope2_kg, 2),
        "scope2_tonnes": round(scope2_kg / 1000.0, 3),
        "scope2_tonnes_co2e": round(scope2_kg / 1000.0, 3),
        "scope2_pct": s2_pct,
        "scope3_kg": round(scope3_kg, 2),
        "scope3_tonnes": round(scope3_kg / 1000.0, 3),
        "scope3_tonnes_co2e": round(scope3_kg / 1000.0, 3),
        "scope3_pct": s3_pct,
        "baseline_emissions_kg": baseline_kg,
        "baseline_emissions_tonnes": round(baseline_kg / 1000.0, 3),
        "avoided_kg": avoided_kg,
        "avoided_tonnes": round(avoided_kg / 1000.0, 3),
        "avoided_tonnes_co2e": round(avoided_kg / 1000.0, 3),
        "pct_reduction": pct_reduction,
        "percentage_reduction": pct_reduction,
        "total_energy_kwh": round(total_energy_kwh, 1),
        "total_cost_inr": round(total_cost_inr, 2),
        "tonnes_per_employee": tonnes_per_employee,
        "intensity_per_employee": tonnes_per_employee,
        "kg_per_unit": kg_per_unit,
        "intensity_per_production_unit": kg_per_unit,
        "production_units": total_production_units,
        "category_breakdown": {k: round(v, 2) for k, v in category_breakdown.items()},
        "dept_breakdown": {k: round(v, 2) for k, v in dept_breakdown.items()},
        "site_breakdown": {k: round(v, 2) for k, v in site_breakdown.items()}
    }

