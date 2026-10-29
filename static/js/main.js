/**
 * main.js - Green Pulse Interactive Visualizations & Client-Side Logic
 */

document.addEventListener("DOMContentLoaded", function () {
  // 1. Evidence Image Live Preview
  const evidenceInput = document.getElementById("evidence_file");
  const previewContainer = document.getElementById("imagePreviewContainer");
  const previewImage = document.getElementById("imagePreview");

  if (evidenceInput && previewContainer && previewImage) {
    evidenceInput.addEventListener("change", function () {
      const file = this.files[0];
      if (file) {
        // Validate file size (5MB max)
        if (file.size > 5 * 1024 * 1024) {
          alert("File size exceeds 5MB limit. Please upload a smaller compressed image.");
          this.value = "";
          previewContainer.style.display = "none";
          return;
        }

        const reader = new FileReader();
        reader.onload = function (e) {
          previewImage.src = e.target.result;
          previewContainer.style.display = "block";
        };
        reader.readAsDataURL(file);
      } else {
        previewContainer.style.display = "none";
      }
    });
  }

  // 2. Calculator Category Tab Switching & Dynamic Factor Previews
  const categorySelect = document.getElementById("calc_category");
  const catPanels = document.querySelectorAll(".calc-category-panel");

  if (categorySelect) {
    function updateActivePanel() {
      const selected = categorySelect.value;
      catPanels.forEach(panel => {
        if (panel.id === `panel-${selected}`) {
          panel.style.display = "block";
        } else {
          panel.style.display = "none";
        }
      });
      updateLiveFormulaPreview();
    }

    categorySelect.addEventListener("change", updateActivePanel);
    // Initial trigger
    updateActivePanel();
  }

  // Live Formula Calculator Preview
  const livePreviewBox = document.getElementById("liveCalculationPreview");
  function updateLiveFormulaPreview() {
    if (!livePreviewBox || !categorySelect) return;
    const cat = categorySelect.value;
    let formulaText = "";

    if (cat === "transportation") {
      const modeSelect = document.getElementById("trans_mode");
      const distInput = document.getElementById("trans_distance");
      const dist = parseFloat(distInput ? distInput.value : 0) || 0;
      const factor = modeSelect ? parseFloat(modeSelect.selectedOptions[0]?.dataset?.factor || 0.084) : 0.084;
      const modeName = modeSelect ? modeSelect.selectedOptions[0]?.text : "Mode";
      const total = (dist * factor).toFixed(2);
      formulaText = `Estimated: ${dist} km × ${factor} kg CO2e/km = <strong>${total} kg CO2e</strong> (${modeName})`;
    } else if (cat === "electricity") {
      const kwhInput = document.getElementById("elec_kwh");
      const kwh = parseFloat(kwhInput ? kwhInput.value : 0) || 0;
      const gridSelect = document.getElementById("elec_grid");
      const factor = gridSelect ? parseFloat(gridSelect.selectedOptions[0]?.dataset?.factor || 0.716) : 0.716;
      const tariffInput = document.getElementById("elec_tariff");
      const tariff = parseFloat(tariffInput ? tariffInput.value : 7.0) || 7.0;
      const total = (kwh * factor).toFixed(2);
      const cost = (kwh * tariff).toFixed(2);
      formulaText = `Estimated: ${kwh} kWh × ${factor} kg CO2/kWh = <strong>${total} kg CO2e</strong> (Est. Bill: ₹${cost})`;
    } else if (cat === "fuel") {
      const fuelSelect = document.getElementById("fuel_type");
      const qtyInput = document.getElementById("fuel_qty");
      const qty = parseFloat(qtyInput ? qtyInput.value : 0) || 0;
      const factor = fuelSelect ? parseFloat(fuelSelect.selectedOptions[0]?.dataset?.factor || 2.31) : 2.31;
      const unit = fuelSelect ? fuelSelect.selectedOptions[0]?.dataset?.unit || "units" : "units";
      const total = (qty * factor).toFixed(2);
      formulaText = `Estimated: ${qty} ${unit} × ${factor} kg CO2e/unit = <strong>${total} kg CO2e</strong>`;
    } else if (cat === "waste") {
      const wasteSelect = document.getElementById("waste_type");
      const kgInput = document.getElementById("waste_kg");
      const kg = parseFloat(kgInput ? kgInput.value : 0) || 0;
      const factor = wasteSelect ? parseFloat(wasteSelect.selectedOptions[0]?.dataset?.factor || 0.58) : 0.58;
      const total = (kg * factor).toFixed(2);
      formulaText = `Estimated: ${kg} kg × ${factor} kg CO2e/kg = <strong>${total} kg CO2e</strong>`;
    }

    livePreviewBox.innerHTML = formulaText;
  }

  // Bind input listeners for live preview
  document.querySelectorAll(".calc-dynamic-input").forEach(input => {
    input.addEventListener("input", updateLiveFormulaPreview);
    input.addEventListener("change", updateLiveFormulaPreview);
  });
});
