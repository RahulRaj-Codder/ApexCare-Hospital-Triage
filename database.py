"""
Database models and initialization for GEC Hackathon 2026:
Healthcare - Patient Triage & Queue Management System
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'hospital_triage.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Departments Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        avg_consult_time_mins INTEGER DEFAULT 15,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 2. Doctors Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        department_id INTEGER NOT NULL,
        specialization TEXT NOT NULL,
        room_no TEXT NOT NULL,
        status TEXT DEFAULT 'AVAILABLE', -- 'AVAILABLE', 'BUSY', 'ON_BREAK', 'OFF_DUTY'
        current_visit_id INTEGER,
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    ''')

    # 3. Users Table (RBAC: DOCTOR, NURSE, ADMIN, KIOSK)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL, -- 'DOCTOR', 'NURSE', 'ADMIN', 'KIOSK'
        department_id INTEGER,
        doctor_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (department_id) REFERENCES departments (id),
        FOREIGN KEY (doctor_id) REFERENCES doctors (id)
    )
    ''')

    # 4. Patients Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT,
        blood_group TEXT,
        known_allergies TEXT,
        chronic_conditions TEXT,
        emergency_contact TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 5. Symptoms Catalog Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS symptoms_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        default_score INTEGER DEFAULT 10,
        is_red_flag INTEGER DEFAULT 0,
        recommended_dept_id INTEGER,
        FOREIGN KEY (recommended_dept_id) REFERENCES departments (id)
    )
    ''')

    # 6. Patient Visits & Queue Table
    # Priority Levels: 'CRITICAL' (Priority 1), 'URGENT' (Priority 2), 'ROUTINE' (Priority 3)
    # Status: 'WAITING_TRIAGE', 'TRIAGED_WAITING', 'CALLED', 'IN_CONSULTATION', 'COMPLETED', 'DISCHARGED', 'CANCELLED'
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_no TEXT UNIQUE NOT NULL,
        patient_id INTEGER NOT NULL,
        department_id INTEGER NOT NULL,
        assigned_doctor_id INTEGER,
        chief_complaint TEXT NOT NULL,
        symptoms_json TEXT, -- JSON array of symptom codes/names
        vitals_json TEXT,   -- JSON object: {hr, systolic_bp, diastolic_bp, spo2, temp_c, rr, pain_score}
        priority_level TEXT DEFAULT 'ROUTINE', -- 'CRITICAL', 'URGENT', 'ROUTINE'
        priority_score INTEGER DEFAULT 0,     -- higher score = higher priority
        status TEXT DEFAULT 'WAITING_TRIAGE',
        arrival_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        triage_completed_at TIMESTAMP,
        consultation_start_at TIMESTAMP,
        completed_at TIMESTAMP,
        estimated_wait_mins INTEGER DEFAULT 15,
        triage_notes TEXT,
        doctor_notes TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients (id),
        FOREIGN KEY (department_id) REFERENCES departments (id),
        FOREIGN KEY (assigned_doctor_id) REFERENCES doctors (id)
    )
    ''')

    # 7. Triage Assessments (Transparency & Explainability Records)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS triage_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id INTEGER NOT NULL,
        ai_recommended_level TEXT NOT NULL,
        ai_recommended_score INTEGER NOT NULL,
        reasons_json TEXT NOT NULL, -- JSON array of trigger explanations
        final_level TEXT NOT NULL,
        final_score INTEGER NOT NULL,
        is_overridden INTEGER DEFAULT 0,
        override_reason TEXT,
        assessed_by_user_id INTEGER,
        assessed_by_name TEXT,
        assessed_by_role TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (visit_id) REFERENCES visits (id),
        FOREIGN KEY (assessed_by_user_id) REFERENCES users (id)
    )
    ''')

    # 8. Configurable Triage Rules Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS triage_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_code TEXT UNIQUE NOT NULL,
        rule_name TEXT NOT NULL,
        category TEXT NOT NULL, -- 'VITALS', 'SYMPTOM', 'AGE_RISK', 'COMORBIDITY'
        condition_json TEXT NOT NULL, -- {metric: 'spo2', op: '<', val: 90}
        priority_result TEXT NOT NULL, -- 'CRITICAL', 'URGENT', 'ROUTINE'
        score_weight INTEGER NOT NULL,
        description TEXT NOT NULL,
        is_active INTEGER DEFAULT 1
    )
    ''')

    # 9. Events Log (Synchronous & Asynchronous Architecture)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS event_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_uuid TEXT NOT NULL,
        event_type TEXT NOT NULL, -- 'PATIENT_REGISTERED', 'TRIAGE_EVALUATED', 'PRIORITY_CHANGED', 'DOCTOR_AVAILABLE', 'PATIENT_CALLED', 'QUEUE_REORDERED'
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        is_critical_sync INTEGER DEFAULT 1, -- 1=Handled synchronously, 0=Asynchronous
        payload_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 10. Notifications Queue (Asynchronous simulated dispatch: SMS, Email, PA System)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notifications_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        recipient_role TEXT, -- 'PATIENT', 'DOCTOR', 'NURSE', 'ADMIN'
        channel TEXT NOT NULL, -- 'SMS', 'EMAIL', 'PA_AUDIO', 'DASHBOARD_ALERT'
        message TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING', -- 'PENDING', 'SENT', 'FAILED'
        priority TEXT DEFAULT 'ROUTINE', -- 'CRITICAL', 'ROUTINE'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sent_at TIMESTAMP
    )
    ''')

    # 11. Audit Records Table (Role-based access & clinical action auditing)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_name TEXT NOT NULL,
        user_role TEXT NOT NULL,
        action TEXT NOT NULL,
        resource_type TEXT NOT NULL,
        resource_id TEXT,
        details TEXT,
        ip_address TEXT DEFAULT '127.0.0.1',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    conn.commit()
    conn.close()

def seed_initial_data():
    conn = get_db()
    cursor = conn.cursor()

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) FROM departments")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # 1. Departments
    departments = [
        ('EMRG', 'Emergency & Trauma', 'Acute emergencies, resuscitation, and critical trauma care', 20),
        ('CARD', 'Cardiology', 'Heart and cardiovascular system conditions and evaluations', 15),
        ('PULM', 'Pulmonology', 'Respiratory illnesses, asthma, acute shortness of breath, COPD', 15),
        ('GENM', 'General Medicine', 'Internal medicine, fever, viral infections, general consultation', 12),
        ('PEDI', 'Pediatrics', 'Comprehensive infant, child, and adolescent healthcare', 15),
        ('ORTH', 'Orthopedics', 'Bones, joints, acute fractures, sprains, and musculoskeletal injuries', 15)
    ]
    cursor.executemany(
        "INSERT INTO departments (code, name, description, avg_consult_time_mins) VALUES (?, ?, ?, ?)",
        departments
    )

    # 2. Doctors
    doctors = [
        ('Dr. Sarah Mehta', 1, 'Emergency Medicine Specialist', 'ER-Bay-1', 'AVAILABLE', None),
        ('Dr. Rajesh Sharma', 1, 'Trauma & Resuscitation Surgeon', 'ER-Bay-2', 'AVAILABLE', None),
        ('Dr. Priya Venkat', 2, 'Interventional Cardiologist', 'OPD-201', 'AVAILABLE', None),
        ('Dr. Amit Patel', 3, 'Pulmonologist & Critical Care', 'OPD-305', 'AVAILABLE', None),
        ('Dr. Sunita Rao', 4, 'Senior General Physician', 'OPD-102', 'AVAILABLE', None),
        ('Dr. Vikram Joshi', 5, 'Pediatric Emergency Specialist', 'OPD-401', 'AVAILABLE', None),
        ('Dr. Ananya Sen', 6, 'Orthopedic Consultant', 'OPD-502', 'AVAILABLE', None)
    ]
    cursor.executemany(
        "INSERT INTO doctors (name, department_id, specialization, room_no, status, current_visit_id) VALUES (?, ?, ?, ?, ?, ?)",
        doctors
    )

    # 3. Default Users (Simple secure hash representation or plain demo hashes)
    # Password for demo accounts is 'admin123' or 'doctor123' or 'nurse123'
    # We will support standard authentication and instant demo role switching
    users = [
        ('admin', 'admin123', 'Hospital Administrator', 'ADMIN', None, None),
        ('dr_sarah', 'doctor123', 'Dr. Sarah Mehta', 'DOCTOR', 1, 1),
        ('dr_priya', 'doctor123', 'Dr. Priya Venkat', 'DOCTOR', 2, 3),
        ('dr_sunita', 'doctor123', 'Dr. Sunita Rao', 'DOCTOR', 4, 5),
        ('nurse_kavita', 'nurse123', 'Nurse Kavita Nair (Triage Lead)', 'NURSE', 1, None),
        ('nurse_rahul', 'nurse123', 'Nurse Rahul Verma', 'NURSE', 4, None),
        ('kiosk_desk', 'kiosk123', 'Front Reception Kiosk', 'KIOSK', None, None)
    ]
    cursor.executemany(
        "INSERT INTO users (username, password_hash, full_name, role, department_id, doctor_id) VALUES (?, ?, ?, ?, ?, ?)",
        users
    )

    # 4. Symptoms Catalog with Clinical Red Flags
    symptoms = [
        ('CHEST_PAIN_SEVERE', 'Crushing substernal chest pain radiating to left arm/jaw', 'Cardiovascular', 45, 1, 2),
        ('SPO2_HYPOXIA', 'Severe shortness of breath with cyanosis/hypoxia', 'Respiratory', 40, 1, 3),
        ('STROKE_SIGNS', 'Sudden facial droop, arm weakness or speech difficulty (FAST)', 'Neurological', 50, 1, 1),
        ('UNCONSCIOUS', 'Altered mental status / Unresponsive / GCS < 10', 'Neurological', 50, 1, 1),
        ('ANAPHYLAXIS', 'Severe allergic reaction, stridor, lip swelling', 'Immunological', 45, 1, 1),
        ('ACTIVE_HEMORRHAGE', 'Arterial or uncontrolled heavy bleeding', 'Trauma', 45, 1, 1),
        ('HIGH_FEVER_RIGORS', 'High fever (>103°F / 39.5°C) with severe chills/rigors', 'Systemic', 25, 0, 4),
        ('ACUTE_FRACTURE', 'Visible deformity, severe bone pain after fall', 'Musculoskeletal', 25, 0, 6),
        ('ABDOMINAL_PAIN_ACUTE', 'Acute severe abdominal pain with peritoneal signs', 'Gastrointestinal', 30, 0, 4),
        ('ASTHMA_WHEEZE', 'Moderate wheezing and breathlessness', 'Respiratory', 25, 0, 3),
        ('MILD_COUGH_COLD', 'Mild dry cough, runny nose, low grade fever', 'General', 5, 0, 4),
        ('ANKLE_SPRAIN_MILD', 'Mild ankle twisting pain, weight-bearing intact', 'Musculoskeletal', 5, 0, 6),
        ('SKIN_RASH_LOCAL', 'Mild localized itchy skin rash, no mucosal involvement', 'Dermatology', 5, 0, 4),
        ('MEDICATION_REFILL', 'Routine follow-up prescription renewal', 'General', 2, 0, 4),
        ('HEADACHE_MILD', 'Mild tension-type headache, normal vitals', 'Neurological', 8, 0, 4)
    ]
    cursor.executemany(
        "INSERT INTO symptoms_catalog (code, name, category, default_score, is_red_flag, recommended_dept_id) VALUES (?, ?, ?, ?, ?, ?)",
        symptoms
    )

    # 5. Configurable Triage Rules (ESI & Manchester Triage compliant)
    rules = [
        ('RULE_SPO2_CRITICAL', 'Critical Hypoxia (SpO2 < 90%)', 'VITALS', json.dumps({'metric': 'spo2', 'op': '<', 'val': 90}), 'CRITICAL', 50, 'SpO2 drops below 90% indicate acute respiratory failure or decompensation.', 1),
        ('RULE_SPO2_URGENT', 'Moderate Hypoxia (SpO2 90-94%)', 'VITALS', json.dumps({'metric': 'spo2', 'op': '<=', 'val': 94}), 'URGENT', 25, 'SpO2 between 90-94% requires prompt clinical supplemental oxygen therapy.', 1),
        ('RULE_HYPOTENSION', 'Hemodynamic Shock / Severe Hypotension (Systolic BP < 90)', 'VITALS', json.dumps({'metric': 'systolic_bp', 'op': '<', 'val': 90}), 'CRITICAL', 45, 'Severe hypotension suggests impending shock or severe sepsis.', 1),
        ('RULE_HYPERTENSIVE_CRISIS', 'Hypertensive Emergency (Systolic BP >= 190)', 'VITALS', json.dumps({'metric': 'systolic_bp', 'op': '>=', 'val': 190}), 'CRITICAL', 40, 'Extreme systolic elevation with organ compromise risk.', 1),
        ('RULE_TACHYCARDIA_EXTREME', 'Extreme Tachycardia (Heart Rate > 130 bpm)', 'VITALS', json.dumps({'metric': 'hr', 'op': '>', 'val': 130}), 'URGENT', 30, 'Significantly elevated heart rate requires urgent evaluation.', 1),
        ('RULE_RESPIRATORY_DISTRESS', 'Severe Tachypnea (Respiratory Rate > 28 /min)', 'VITALS', json.dumps({'metric': 'rr', 'op': '>', 'val': 28}), 'URGENT', 30, 'Respiratory rate > 28 reflects acute metabolic or ventilatory compromise.', 1),
        ('RULE_HIGH_FEVER_EXTREME', 'Hyperpyrexia (Temp >= 39.5°C)', 'VITALS', json.dumps({'metric': 'temp_c', 'op': '>=', 'val': 39.5}), 'URGENT', 20, 'Fever above 39.5°C poses risk of febrile seizure or severe infection.', 1),
        ('RULE_SEVERE_PAIN', 'Intense Pain Scale (Pain Score >= 8)', 'VITALS', json.dumps({'metric': 'pain_score', 'op': '>=', 'val': 8}), 'URGENT', 20, 'Severe pain score (8-10/10) warrants expedited analgesia and doctor review.', 1),
        ('RULE_RED_FLAG_SYMPTOM', 'Red Flag Clinical Symptom Present', 'SYMPTOM', json.dumps({'metric': 'has_red_flag', 'op': '==', 'val': True}), 'CRITICAL', 45, 'Presence of any emergency red-flag symptom escalates triage priority.', 1),
        ('RULE_GERIATRIC_COMORBIDITY', 'High-Risk Geriatric Alert (Age >= 65 with Vitals Derangement)', 'AGE_RISK', json.dumps({'metric': 'age', 'op': '>=', 'val': 65}), 'URGENT', 15, 'Elderly patients with clinical instability are at heightened risk of rapid decline.', 1)
    ]
    cursor.executemany(
        "INSERT INTO triage_rules (rule_code, rule_name, category, condition_json, priority_result, score_weight, description, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rules
    )

    # 6. Sample Patients
    patients = [
        ('PAT-1001', 'Ramesh Kumar Patel', 68, 'Male', '+91 98765 43210', 'ramesh.patel@example.com', 'B+', 'Penicillin', 'Hypertension, Type-2 Diabetes', 'Wife: Sunita Patel (+91 98765 43211)'),
        ('PAT-1002', 'Anjali Sharma', 29, 'Female', '+91 98765 43220', 'anjali.s@example.com', 'O+', 'None', 'None', 'Brother: Rohan (+91 98765 43221)'),
        ('PAT-1003', 'Vikramaditya Das', 45, 'Male', '+91 98765 43230', 'v.das@example.com', 'A+', 'Sulfa drugs', 'Asthma', 'Spouse: Meera (+91 98765 43231)'),
        ('PAT-1004', 'Pooja Mohanty', 22, 'Female', '+91 98765 43240', 'pooja.m@example.com', 'AB+', 'None', 'None', 'Father: Ashok (+91 98765 43241)'),
        ('PAT-1005', 'Santosh Tripathy', 52, 'Male', '+91 98765 43250', 'santosh.t@example.com', 'O-', 'Aspirin', 'Coronary Artery Disease', 'Son: Amit (+91 98765 43251)')
    ]
    cursor.executemany(
        "INSERT INTO patients (patient_code, name, age, gender, phone, email, blood_group, known_allergies, chronic_conditions, emergency_contact) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        patients
    )

    # 7. Seed Initial Visits to illustrate realistic queue state
    # Visit 1: Routine Cough/Cold (Patient 2) -> Arrived 25 mins ago
    cursor.execute('''
    INSERT INTO visits (
        token_no, patient_id, department_id, assigned_doctor_id, chief_complaint,
        symptoms_json, vitals_json, priority_level, priority_score, status,
        arrival_time, triage_completed_at, estimated_wait_mins, triage_notes
    ) VALUES (
        'TKN-101', 2, 4, NULL, 'Mild dry cough and slight throat irritation for 2 days',
        ?, ?, 'ROUTINE', 10, 'TRIAGED_WAITING',
        datetime('now', '-25 minutes'), datetime('now', '-20 minutes'), 20,
        'Patient alert and oriented. Mild pharyngeal redness. Clear lung fields.'
    )
    ''', (
        json.dumps(['MILD_COUGH_COLD']),
        json.dumps({'hr': 74, 'systolic_bp': 118, 'diastolic_bp': 76, 'spo2': 98, 'temp_c': 37.0, 'rr': 16, 'pain_score': 1})
    ))

    # Triage assessment record for Visit 1
    cursor.execute('''
    INSERT INTO triage_assessments (
        visit_id, ai_recommended_level, ai_recommended_score, reasons_json,
        final_level, final_score, is_overridden, assessed_by_name, assessed_by_role
    ) VALUES (
        1, 'ROUTINE', 10,
        ?,
        'ROUTINE', 10, 0, 'Nurse Kavita Nair', 'NURSE'
    )
    ''', (json.dumps(["Normal vitals across all parameters", "Non-emergency presentation: Mild dry cough"]),))

    # Visit 2: Routine Ankle Sprain (Patient 4) -> Arrived 15 mins ago
    cursor.execute('''
    INSERT INTO visits (
        token_no, patient_id, department_id, assigned_doctor_id, chief_complaint,
        symptoms_json, vitals_json, priority_level, priority_score, status,
        arrival_time, triage_completed_at, estimated_wait_mins, triage_notes
    ) VALUES (
        'TKN-102', 4, 6, NULL, 'Mild ankle twist while descending staircase, able to bear weight',
        ?, ?, 'ROUTINE', 15, 'TRIAGED_WAITING',
        datetime('now', '-15 minutes'), datetime('now', '-10 minutes'), 25,
        'Mild lateral malleolus tenderness. No gross deformity. Intact neurovascular.'
    )
    ''', (
        json.dumps(['ANKLE_SPRAIN_MILD']),
        json.dumps({'hr': 80, 'systolic_bp': 122, 'diastolic_bp': 78, 'spo2': 99, 'temp_c': 36.8, 'rr': 15, 'pain_score': 3})
    ))

    cursor.execute('''
    INSERT INTO triage_assessments (
        visit_id, ai_recommended_level, ai_recommended_score, reasons_json,
        final_level, final_score, is_overridden, assessed_by_name, assessed_by_role
    ) VALUES (
        2, 'ROUTINE', 15,
        ?,
        'ROUTINE', 15, 0, 'Nurse Kavita Nair', 'NURSE'
    )
    ''', (json.dumps(["Normal hemodynamic status", "Isolated mild musculoskeletal complaint with weight bearing preserved"]),))

    # Audit log initialization
    cursor.execute('''
    INSERT INTO audit_logs (user_name, user_role, action, resource_type, resource_id, details)
    VALUES ('SYSTEM', 'SYSTEM', 'SYSTEM_INITIALIZATION', 'DATABASE', 'ALL', 'Initial schema created, baseline synthetic patients and triage rules provisioned.')
    ''')

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    seed_initial_data()
    print("Database initialized and seeded successfully.")
