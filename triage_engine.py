"""
Clinical Triage & Urgency Evaluation Engine
GEC Hackathon 2026 - Problem Statement 01
Healthcare: Patient Triage & Queue Management

Implements:
1. Manchester Triage System (MTS) & Emergency Severity Index (ESI) compatible scoring.
2. Configurable multi-parameter rule evaluation (Vitals, Red Flags, Comorbidities, Age).
3. Explainable Clinical Decision Support: Detailed transparent breakdown of why
   each priority level was assigned, explicitly stating weights and triggers.
4. Decision Support Safe Harbor: Non-diagnostic disclaimer and manual clinician override.
"""

import json
from datetime import datetime

class ClinicalTriageEngine:
    """
    Transparent Decision-Support Clinical Triage Engine.
    Evaluates patient vitals, reported symptoms, age, and chronic conditions
    to recommend an urgency priority: CRITICAL, URGENT, or ROUTINE.
    """

    # Priority Definitions
    PRIORITY_CRITICAL = 'CRITICAL' # ESI Level 1/2: Immediate life-threat / resuscitation
    PRIORITY_URGENT = 'URGENT'     # ESI Level 3: Emergent / potentially unstable
    PRIORITY_ROUTINE = 'ROUTINE'   # ESI Level 4/5: Non-urgent / standard care

    @staticmethod
    def evaluate(patient_info, vitals, selected_symptom_codes, active_rules=None, symptoms_catalog=None):
        """
        Evaluate patient data and return recommended priority, total score, and explainable reasons.

        :param patient_info: dict with age, gender, known_allergies, chronic_conditions
        :param vitals: dict with hr, systolic_bp, diastolic_bp, spo2, temp_c, rr, pain_score
        :param selected_symptom_codes: list of symptom codes reported
        :param active_rules: list of rule dicts from database (optional)
        :param symptoms_catalog: dict of symptom metadata from database (optional)
        :return: dict(priority_level, urgency_score, reasons, red_flags_found, vitals_warnings)
        """
        reasons = []
        red_flags_found = []
        vitals_warnings = []
        urgency_score = 0
        forced_critical = False
        forced_urgent = False

        # Extract vitals with safe defaults
        hr = float(vitals.get('hr') or 75)
        systolic = float(vitals.get('systolic_bp') or 120)
        diastolic = float(vitals.get('diastolic_bp') or 80)
        spo2 = float(vitals.get('spo2') or 98)
        temp_c = float(vitals.get('temp_c') or 37.0)
        rr = float(vitals.get('rr') or 16)
        pain = int(vitals.get('pain_score') or 0)
        age = int(patient_info.get('age') or 30)
        chronic = (patient_info.get('chronic_conditions') or '').lower()

        # -------------------------------------------------------------
        # STEP 1: Physiological Vitals Rule Analysis
        # -------------------------------------------------------------
        # A. Oxygen Saturation (SpO2)
        if spo2 < 90:
            urgency_score += 50
            forced_critical = True
            msg = f"Critical Hypoxia Alert: SpO2 is {spo2}% (<90%). Severe oxygen desaturation requiring immediate airway & O2 resuscitation."
            reasons.append({"rule": "RULE_SPO2_CRITICAL", "weight": +50, "description": msg, "severity": "CRITICAL"})
            vitals_warnings.append(f"Hypoxia (SpO2: {spo2}%)")
        elif spo2 <= 94:
            urgency_score += 25
            forced_urgent = True
            msg = f"Moderate Hypoxia: SpO2 is {spo2}% (90-94%). Prompt supplemental oxygen and respiratory monitoring needed."
            reasons.append({"rule": "RULE_SPO2_URGENT", "weight": +25, "description": msg, "severity": "URGENT"})
            vitals_warnings.append(f"Borderline Hypoxia (SpO2: {spo2}%)")

        # B. Blood Pressure (Hemodynamics)
        if systolic < 90:
            urgency_score += 45
            forced_critical = True
            msg = f"Hemodynamic Collapse / Shock Alert: Systolic BP {systolic} mmHg (<90). High risk of systemic hypoperfusion."
            reasons.append({"rule": "RULE_HYPOTENSION", "weight": +45, "description": msg, "severity": "CRITICAL"})
            vitals_warnings.append(f"Severe Hypotension ({systolic}/{diastolic} mmHg)")
        elif systolic >= 190:
            urgency_score += 40
            forced_critical = True
            msg = f"Hypertensive Emergency: Systolic BP {systolic} mmHg (>=190). High risk of end-organ damage (stroke, aortic dissection)."
            reasons.append({"rule": "RULE_HYPERTENSIVE_CRISIS", "weight": +40, "description": msg, "severity": "CRITICAL"})
            vitals_warnings.append(f"Hypertensive Crisis ({systolic}/{diastolic} mmHg)")
        elif systolic >= 160 or diastolic >= 100:
            urgency_score += 15
            reasons.append({"rule": "RULE_HYPERTENSION_STAGE2", "weight": +15, "description": f"Stage 2 Hypertension ({systolic}/{diastolic} mmHg).", "severity": "URGENT"})

        # C. Heart Rate (Pulse)
        if hr > 130:
            urgency_score += 30
            forced_urgent = True
            msg = f"Marked Tachycardia: Heart rate {hr} bpm (>130 bpm). Risk of supraventricular tachycardia, sepsis or hypovolemia."
            reasons.append({"rule": "RULE_TACHYCARDIA_EXTREME", "weight": +30, "description": msg, "severity": "URGENT"})
            vitals_warnings.append(f"Severe Tachycardia ({hr} bpm)")
        elif hr < 45:
            urgency_score += 35
            forced_critical = True
            msg = f"Severe Bradycardia: Heart rate {hr} bpm (<45 bpm). Risk of heart block or sinus node arrest."
            reasons.append({"rule": "RULE_BRADYCARDIA_SEVERE", "weight": +35, "description": msg, "severity": "CRITICAL"})
            vitals_warnings.append(f"Severe Bradycardia ({hr} bpm)")
        elif hr > 105:
            urgency_score += 15
            reasons.append({"rule": "RULE_TACHYCARDIA_MILD", "weight": +15, "description": f"Mild Tachycardia ({hr} bpm).", "severity": "ROUTINE"})

        # D. Respiratory Rate
        if rr > 28:
            urgency_score += 30
            forced_urgent = True
            msg = f"Severe Tachypnea: Respiratory rate {rr}/min (>28). Significant respiratory distress or metabolic acidosis."
            reasons.append({"rule": "RULE_RESPIRATORY_DISTRESS", "weight": +30, "description": msg, "severity": "URGENT"})
            vitals_warnings.append(f"Tachypnea ({rr}/min)")
        elif rr < 10:
            urgency_score += 45
            forced_critical = True
            msg = f"Bradypnea / Respiratory Depression: Rate {rr}/min (<10). Impending respiratory arrest."
            reasons.append({"rule": "RULE_BRADYPNEA_CRITICAL", "weight": +45, "description": msg, "severity": "CRITICAL"})
            vitals_warnings.append(f"Respiratory Depression ({rr}/min)")

        # E. Body Temperature
        if temp_c >= 39.5:
            urgency_score += 20
            forced_urgent = True
            msg = f"Hyperpyrexia: Core temperature {temp_c}°C (>=39.5°C / 103.1°F). High risk of severe sepsis or febrile encephalopathy."
            reasons.append({"rule": "RULE_HIGH_FEVER_EXTREME", "weight": +20, "description": msg, "severity": "URGENT"})
            vitals_warnings.append(f"High Fever ({temp_c}°C)")
        elif temp_c < 35.0:
            urgency_score += 30
            forced_urgent = True
            msg = f"Hypothermia: Temperature {temp_c}°C (<35°C). Critical metabolic or environmental failure."
            reasons.append({"rule": "RULE_HYPOTHERMIA", "weight": +30, "description": msg, "severity": "URGENT"})

        # F. Pain Score (1-10)
        if pain >= 8:
            urgency_score += 20
            forced_urgent = True
            msg = f"Intense Acute Pain: Rated {pain}/10 on visual analog scale. Expedited clinical review and analgesia indicated."
            reasons.append({"rule": "RULE_SEVERE_PAIN", "weight": +20, "description": msg, "severity": "URGENT"})
        elif pain >= 5:
            urgency_score += 10
            reasons.append({"rule": "RULE_MODERATE_PAIN", "weight": +10, "description": f"Moderate pain reported ({pain}/10).", "severity": "ROUTINE"})

        # -------------------------------------------------------------
        # STEP 2: Clinical Symptoms & Red Flags
        # -------------------------------------------------------------
        RED_FLAG_CODES = {
            'CHEST_PAIN_SEVERE': ('Severe Cardiac Red Flag', 'Crushing chest pain radiating to left arm/jaw - Suspected Acute Coronary Syndrome (STEMI/NSTEMI).', 45, True),
            'SPO2_HYPOXIA': ('Respiratory Emergency', 'Severe shortness of breath with cyanosis/hypoxia.', 40, True),
            'STROKE_SIGNS': ('Acute Neuro Stroke Alert', 'Sudden FAST signs (facial droop, arm weakness, slurred speech) - Time-critical thrombolysis window.', 50, True),
            'UNCONSCIOUS': ('Coma / Severe CNS Depression', 'Unresponsive or altered consciousness (GCS < 10).', 50, True),
            'ANAPHYLAXIS': ('Acute Anaphylaxis Red Flag', 'Stridor, facial angioedema, airway compromise after allergen exposure.', 45, True),
            'ACTIVE_HEMORRHAGE': ('Major Hemorrhage Alert', 'Active arterial or massive blood loss requiring immediate hemostasis.', 45, True)
        }

        symptom_scores = {
            'HIGH_FEVER_RIGORS': ('High Fever with Rigors', 25, False),
            'ACUTE_FRACTURE': ('Suspected Acute Bone Fracture', 25, False),
            'ABDOMINAL_PAIN_ACUTE': ('Acute Peritoneal Abdominal Pain', 30, False),
            'ASTHMA_WHEEZE': ('Acute Bronchospasm / Asthma Flare', 25, False),
            'MILD_COUGH_COLD': ('Mild Upper Respiratory Symptoms', 5, False),
            'ANKLE_SPRAIN_MILD': ('Mild Ankle Sprain', 5, False),
            'SKIN_RASH_LOCAL': ('Localized Dermatitis / Rash', 5, False),
            'MEDICATION_REFILL': ('Medication Refill Request', 2, False),
            'HEADACHE_MILD': ('Tension Headache', 8, False)
        }

        for code in selected_symptom_codes:
            if code in RED_FLAG_CODES:
                title, desc, weight, is_crit = RED_FLAG_CODES[code]
                urgency_score += weight
                forced_critical = True
                red_flags_found.append(title)
                reasons.append({
                    "rule": f"RED_FLAG_{code}",
                    "weight": +weight,
                    "description": f"CRITICAL RED FLAG: {desc}",
                    "severity": "CRITICAL"
                })
            elif code in symptom_scores:
                name, weight, _ = symptom_scores[code]
                urgency_score += weight
                if weight >= 25:
                    forced_urgent = True
                reasons.append({
                    "rule": f"SYMPTOM_{code}",
                    "weight": +weight,
                    "description": f"Clinical Finding: {name} (+{weight} urgency points)",
                    "severity": "URGENT" if weight >= 25 else "ROUTINE"
                })

        # -------------------------------------------------------------
        # STEP 3: Age & Comorbidity Risk Amplifiers
        # -------------------------------------------------------------
        if age >= 65 and (vitals_warnings or urgency_score >= 20):
            urgency_score += 15
            forced_urgent = True
            reasons.append({
                "rule": "RULE_GERIATRIC_COMORBIDITY",
                "weight": +15,
                "description": f"Geriatric Risk Factor: Patient is {age} years old with deranged physiological signs.",
                "severity": "URGENT"
            })
        elif age <= 2 and temp_c >= 38.5:
            urgency_score += 20
            forced_urgent = True
            reasons.append({
                "rule": "RULE_NEONATAL_FEVER",
                "weight": +20,
                "description": f"Pediatric Risk: Infant/toddler age {age} with high pyrexia.",
                "severity": "URGENT"
            })

        if ('cardiac' in chronic or 'coronary' in chronic or 'heart' in chronic) and any('CHEST' in c for c in selected_symptom_codes):
            urgency_score += 20
            forced_critical = True
            reasons.append({
                "rule": "RULE_CARDIAC_HISTORY_CHEST_PAIN",
                "weight": +20,
                "description": "Pre-existing Coronary Artery Disease combined with current chest discomfort.",
                "severity": "CRITICAL"
            })

        # -------------------------------------------------------------
        # STEP 4: Final Priority Determination & Normalization
        # -------------------------------------------------------------
        # Cap score between 0 and 100
        urgency_score = min(max(urgency_score, 0), 100)

        if forced_critical or urgency_score >= 60:
            final_priority = ClinicalTriageEngine.PRIORITY_CRITICAL
        elif forced_urgent or urgency_score >= 25:
            final_priority = ClinicalTriageEngine.PRIORITY_URGENT
        else:
            final_priority = ClinicalTriageEngine.PRIORITY_ROUTINE
            if not reasons:
                reasons.append({
                    "rule": "BASELINE_NORMAL",
                    "weight": 0,
                    "description": "All monitored vitals within normal clinical limits; no emergency red flags reported.",
                    "severity": "ROUTINE"
                })

        # Estimated wait time guide in minutes based on triage level
        wait_estimates = {
            ClinicalTriageEngine.PRIORITY_CRITICAL: 0,   # Immediate / Resuscitation bay
            ClinicalTriageEngine.PRIORITY_URGENT: 15,    # Emergent target: <15 mins
            ClinicalTriageEngine.PRIORITY_ROUTINE: 45    # Non-urgent target: 30-60 mins
        }

        return {
            "priority_level": final_priority,
            "urgency_score": urgency_score,
            "reasons": reasons,
            "red_flags": red_flags_found,
            "vitals_warnings": vitals_warnings,
            "recommended_wait_mins": wait_estimates[final_priority],
            "evaluated_at": datetime.now().isoformat(),
            "disclaimer": "CLINICAL DECISION SUPPORT NOTICE: This automated recommendation is generated to assist clinical prioritization and does NOT replace doctor or triage nurse clinical assessment. Authorised clinicians may review and override."
        }
