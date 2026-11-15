"""
GEC Hackathon 2026: Problem Statement 01
Healthcare - Patient Triage & Queue Management System
Main Application Server (Flask + REST APIs + Web UI)
"""

import os
import json
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response, stream_with_context

from database import get_db, init_db, seed_initial_data, DB_PATH
from triage_engine import ClinicalTriageEngine
from event_bus import EventBus

app = Flask(__name__)
app.secret_key = 'gec_hackathon_2026_triage_secret_key_prod_grade'

# Initialize database and event bus
init_db()
seed_initial_data()
event_bus = EventBus(DB_PATH)

# Helper: Log audit trail
def log_audit(action, resource_type, resource_id, details):
    user_name = session.get('user_name', 'Anonymous')
    user_role = session.get('user_role', 'GUEST')
    ip = request.remote_addr or '127.0.0.1'
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO audit_logs (user_name, user_role, action, resource_type, resource_id, details, ip_address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_name, user_role, action, resource_type, str(resource_id), details, ip))
    conn.commit()
    conn.close()

# Context processor for templates (passes active session info)
@app.context_processor
def inject_user_context():
    return {
        'current_user': session.get('user_name', 'Guest'),
        'current_role': session.get('user_role', 'DOCTOR'),
        'current_dept_id': session.get('department_id', 1),
        'current_doctor_id': session.get('doctor_id', 1)
    }

# -----------------------------------------------------------------------------
# Web Page UI Routes
# -----------------------------------------------------------------------------

@app.route('/')
def dashboard_view():
    """Operations Dashboard: Executive view of queue, triage stats, doctor load."""
    conn = get_db()
    cursor = conn.cursor()

    # Metrics
    cursor.execute("SELECT COUNT(*) FROM visits WHERE status IN ('WAITING_TRIAGE', 'TRIAGED_WAITING', 'CALLED', 'IN_CONSULTATION')")
    active_visits_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM visits WHERE priority_level = 'CRITICAL' AND status IN ('WAITING_TRIAGE', 'TRIAGED_WAITING')")
    critical_waiting_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM visits WHERE priority_level = 'URGENT' AND status IN ('WAITING_TRIAGE', 'TRIAGED_WAITING')")
    urgent_waiting_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM visits WHERE priority_level = 'ROUTINE' AND status IN ('WAITING_TRIAGE', 'TRIAGED_WAITING')")
    routine_waiting_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM doctors WHERE status = 'AVAILABLE'")
    available_doctors_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM visits WHERE status = 'COMPLETED'")
    completed_today_count = cursor.fetchone()[0]

    # Active doctors list
    cursor.execute('''
        SELECT d.id, d.name, d.specialization, d.room_no, d.status, dep.name as dept_name,
               v.token_no as active_token, p.name as active_patient_name
        FROM doctors d
        JOIN departments dep ON d.department_id = dep.id
        LEFT JOIN visits v ON d.current_visit_id = v.id
        LEFT JOIN patients p ON v.patient_id = p.id
        ORDER BY d.department_id ASC
    ''')
    doctors = cursor.fetchall()

    # Recent Audit activity
    cursor.execute('''
        SELECT user_name, user_role, action, details, created_at
        FROM audit_logs
        ORDER BY id DESC LIMIT 6
    ''')
    recent_audits = cursor.fetchall()

    conn.close()

    return render_template('dashboard.html',
                           active_visits=active_visits_count,
                           critical_waiting=critical_waiting_count,
                           urgent_waiting=urgent_waiting_count,
                           routine_waiting=routine_waiting_count,
                           available_doctors=available_doctors_count,
                           completed_today=completed_today_count,
                           doctors=doctors,
                           recent_audits=recent_audits)

@app.route('/triage')
def triage_view():
    """Triage Station: Nurse assessment, intake vitals, AI preview & manual override."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, code FROM departments ORDER BY id ASC")
    departments = cursor.fetchall()

    cursor.execute("SELECT code, name, category, default_score, is_red_flag FROM symptoms_catalog ORDER BY is_red_flag DESC, category ASC")
    symptoms = cursor.fetchall()

    cursor.execute('''
        SELECT v.id, v.token_no, v.chief_complaint, v.arrival_time, v.status, p.patient_code, p.name as patient_name, p.age, p.gender
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.status = 'WAITING_TRIAGE'
        ORDER BY v.arrival_time ASC
    ''')
    pending_triage = cursor.fetchall()

    conn.close()
    return render_template('triage.html', departments=departments, symptoms=symptoms, pending_triage=pending_triage)

@app.route('/queue')
def queue_view():
    """Urgency-Sorted Hospital Queue & Doctor Allocation Console."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, code, name FROM departments ORDER BY id ASC")
    departments = cursor.fetchall()

    conn.close()
    return render_template('queue.html', departments=departments)

@app.route('/doctor')
def doctor_view():
    """Doctor Consultation Room: Active Patient, Call Next, Clinical Notes, Discharge."""
    conn = get_db()
    cursor = conn.cursor()

    doctor_id = session.get('doctor_id', 1)
    cursor.execute('''
        SELECT d.id, d.name, d.specialization, d.room_no, d.status, d.department_id, dep.name as dept_name
        FROM doctors d
        JOIN departments dep ON d.department_id = dep.id
        WHERE d.id = ?
    ''', (doctor_id,))
    doctor = cursor.fetchone()

    # Active consultation if any
    active_visit = None
    if doctor and doctor['status'] == 'BUSY':
        cursor.execute('''
            SELECT v.*, p.patient_code, p.name as patient_name, p.age, p.gender, p.blood_group,
                   p.known_allergies, p.chronic_conditions
            FROM visits v
            JOIN patients p ON v.patient_id = p.id
            WHERE v.assigned_doctor_id = ? AND v.status = 'IN_CONSULTATION'
        ''', (doctor_id,))
        active_visit = cursor.fetchone()

    # Waiting queue for this doctor's department
    dept_id = doctor['department_id'] if doctor else 1
    cursor.execute('''
        SELECT v.*, p.name as patient_name, p.age, p.gender
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.department_id = ? AND v.status = 'TRIAGED_WAITING'
        ORDER BY
            CASE v.priority_level
                WHEN 'CRITICAL' THEN 1
                WHEN 'URGENT' THEN 2
                WHEN 'ROUTINE' THEN 3
                ELSE 4
            END ASC,
            v.priority_score DESC,
            v.arrival_time ASC
    ''', (dept_id,))
    dept_queue = cursor.fetchall()

    cursor.execute("SELECT id, name, specialization, room_no FROM doctors ORDER BY id ASC")
    all_doctors = cursor.fetchall()

    conn.close()
    return render_template('doctor.html', doctor=doctor, active_visit=active_visit, dept_queue=dept_queue, all_doctors=all_doctors)

@app.route('/doctor-board')
@app.route('/doctor_board.html')
@app.route('/doctor_boad.html')
def doctor_board_view():
    """Doctor Availability & Roster Display Board."""
    return render_template('doctor_board.html')

@app.route('/display')
def public_display_view():
    """Public / Patient Waiting Room TV Display with Audio/Visual alerts."""
    return render_template('public_board.html')

@app.route('/rules')
def rules_view():
    """Configurable Triage Rules & Urgency Thresholds Configuration (Admin)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM triage_rules ORDER BY category ASC, score_weight DESC")
    rules = cursor.fetchall()
    conn.close()
    return render_template('rules.html', rules=rules)

@app.route('/audit')
def audit_view():
    """Audit Hub: Tamper-evident Audit Records & Synchronous/Asynchronous Event Log."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50")
    audit_logs = cursor.fetchall()

    cursor.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT 50")
    event_logs = cursor.fetchall()

    cursor.execute("SELECT * FROM notifications_queue ORDER BY id DESC LIMIT 50")
    notifications = cursor.fetchall()

    conn.close()
    return render_template('audit.html', audit_logs=audit_logs, event_logs=event_logs, notifications=notifications)

@app.route('/login', methods=['GET', 'POST'])
def login_view():
    """Login and fast demo role switcher."""
    if request.method == 'POST':
        role = request.form.get('role', 'DOCTOR')
        conn = get_db()
        cursor = conn.cursor()

        if role == 'ADMIN':
            cursor.execute("SELECT * FROM users WHERE role = 'ADMIN' LIMIT 1")
        elif role == 'NURSE':
            cursor.execute("SELECT * FROM users WHERE role = 'NURSE' LIMIT 1")
        elif role == 'DOCTOR':
            doc_id = request.form.get('doctor_id') or 1
            cursor.execute("SELECT * FROM users WHERE doctor_id = ?", (doc_id,))
            if not cursor.fetchone():
                cursor.execute("SELECT * FROM users WHERE role = 'DOCTOR' LIMIT 1")
        else:
            cursor.execute("SELECT * FROM users LIMIT 1")

        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['user_role'] = user['role']
            session['department_id'] = user['department_id'] or 1
            session['doctor_id'] = user['doctor_id'] or 1
            log_audit('USER_LOGIN', 'SESSION', user['id'], f"Logged in as {user['role']} ({user['full_name']})")

        return redirect(url_for('dashboard_view'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, specialization FROM doctors")
    doctors = cursor.fetchall()
    conn.close()
    return render_template('login.html', doctors=doctors)

@app.route('/switch-role/<role>')
def switch_role(role):
    """1-Click Fast role switcher for Hackathon evaluators."""
    conn = get_db()
    cursor = conn.cursor()
    if role == 'DOCTOR':
        cursor.execute("SELECT * FROM users WHERE role = 'DOCTOR' LIMIT 1")
    elif role == 'NURSE':
        cursor.execute("SELECT * FROM users WHERE role = 'NURSE' LIMIT 1")
    elif role == 'ADMIN':
        cursor.execute("SELECT * FROM users WHERE role = 'ADMIN' LIMIT 1")
    else:
        cursor.execute("SELECT * FROM users WHERE role = 'KIOSK' LIMIT 1")

    user = cursor.fetchone()
    conn.close()

    if user:
        session['user_id'] = user['id']
        session['user_name'] = user['full_name']
        session['user_role'] = user['role']
        session['department_id'] = user['department_id'] or 1
        session['doctor_id'] = user['doctor_id'] or 1
        log_audit('ROLE_SWITCH', 'SESSION', user['id'], f"Switched role to {user['role']}")

    return redirect(request.referrer or url_for('dashboard_view'))

# -----------------------------------------------------------------------------
# REST APIs: Functional Requirements 1 - 6
# -----------------------------------------------------------------------------

# 1. Patient Registration & Intake API
@app.route('/api/patients', methods=['GET', 'POST'])
def api_patients():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        name = data.get('name', '').strip()
        age = int(data.get('age', 0))
        gender = data.get('gender', 'Other')
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        blood_group = data.get('blood_group', '')
        known_allergies = data.get('known_allergies', 'None')
        chronic_conditions = data.get('chronic_conditions', 'None')
        emergency_contact = data.get('emergency_contact', '')

        if not name or age <= 0 or not phone:
            conn.close()
            return jsonify({'success': False, 'error': 'Name, valid age and phone number are required.'}), 400

        patient_code = f"PAT-{uuid.uuid4().hex[:6].upper()}"

        cursor.execute('''
            INSERT INTO patients (patient_code, name, age, gender, phone, email, blood_group, known_allergies, chronic_conditions, emergency_contact)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (patient_code, name, age, gender, phone, email, blood_group, known_allergies, chronic_conditions, emergency_contact))
        patient_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log_audit('PATIENT_REGISTER', 'PATIENT', patient_id, f"Registered new patient {name} ({patient_code})")
        return jsonify({'success': True, 'patient_id': patient_id, 'patient_code': patient_code, 'name': name})

    # GET: Search / list
    query = request.args.get('q', '').strip()
    if query:
        cursor.execute('''
            SELECT * FROM patients
            WHERE name LIKE ? OR patient_code LIKE ? OR phone LIKE ?
            ORDER BY id DESC LIMIT 20
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
    else:
        cursor.execute("SELECT * FROM patients ORDER BY id DESC LIMIT 20")

    patients = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'patients': patients})

# 2. Visit Registration (Arrival Intake)
@app.route('/api/visits/register', methods=['POST'])
def api_register_visit():
    data = request.json or {}
    patient_id = data.get('patient_id')
    department_id = data.get('department_id', 1)
    chief_complaint = data.get('chief_complaint', 'Walk-in arrival').strip()

    if not patient_id:
        return jsonify({'success': False, 'error': 'Patient ID is required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Generate Token
    cursor.execute("SELECT COUNT(*) FROM visits")
    count = cursor.fetchone()[0] + 1
    token_no = f"TKN-{100 + count}"

    cursor.execute('''
        INSERT INTO visits (token_no, patient_id, department_id, chief_complaint, status)
        VALUES (?, ?, ?, ?, 'WAITING_TRIAGE')
    ''', (token_no, patient_id, department_id, chief_complaint))
    visit_id = cursor.lastrowid
    conn.commit()

    # Fetch patient details for notification
    cursor.execute("SELECT name, phone FROM patients WHERE id = ?", (patient_id,))
    pat = cursor.fetchone()
    conn.close()

    # Event Generation: Patient Registered
    event_payload = {
        'visit_id': visit_id,
        'token_no': token_no,
        'patient_id': patient_id,
        'patient_name': pat['name'] if pat else 'Patient',
        'department_id': department_id,
        'chief_complaint': chief_complaint
    }

    # Dispatch Synchronous event to update queue displays
    event_bus.dispatch_sync('PATIENT_REGISTERED', 'VISIT', visit_id, event_payload)

    # Dispatch Asynchronous routine intake notification (Simulated SMS to patient)
    notifs = [{
        'recipient': pat['phone'] if pat else 'Unknown',
        'role': 'PATIENT',
        'channel': 'SMS',
        'message': f"Welcome to ApexCare. Your Token No is {token_no}. Please proceed to Triage Station 1 for vital signs check.",
        'priority': 'ROUTINE'
    }]
    event_bus.dispatch_async('VISIT_INTAKE_NOTIFICATION', 'VISIT', visit_id, event_payload, notifications=notifs)

    log_audit('VISIT_INTAKE', 'VISIT', visit_id, f"Registered visit for {pat['name'] if pat else 'Patient'} (Token: {token_no})")

    return jsonify({'success': True, 'visit_id': visit_id, 'token_no': token_no})

# 3. Live AI Triage Preview (Calculates urgency dynamically as nurse types)
@app.route('/api/triage/preview', methods=['POST'])
def api_triage_preview():
    data = request.json or {}
    vitals = data.get('vitals', {})
    symptoms = data.get('symptoms', [])
    patient_info = data.get('patient_info', {})

    result = ClinicalTriageEngine.evaluate(patient_info, vitals, symptoms)
    return jsonify({'success': True, 'evaluation': result})

# 4. Triage Assessment Execution (Synchronous Critical Update + Decision Record)
@app.route('/api/triage/assess', methods=['POST'])
def api_triage_assess():
    data = request.json or {}
    visit_id = data.get('visit_id')
    vitals = data.get('vitals', {})
    symptoms = data.get('symptoms', [])
    triage_notes = data.get('triage_notes', '').strip()
    is_overridden = bool(data.get('is_overridden', False))
    override_level = data.get('override_level')
    override_reason = data.get('override_reason', '').strip()

    if not visit_id:
        return jsonify({'success': False, 'error': 'Visit ID is required.'}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT v.*, p.age, p.gender, p.chronic_conditions, p.name as patient_name, p.phone as patient_phone, dep.avg_consult_time_mins
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        JOIN departments dep ON v.department_id = dep.id
        WHERE v.id = ?
    ''', (visit_id,))
    visit = cursor.fetchone()

    if not visit:
        conn.close()
        return jsonify({'success': False, 'error': 'Visit not found.'}), 404

    # Run AI evaluation engine
    patient_info = {
        'age': visit['age'],
        'gender': visit['gender'],
        'chronic_conditions': visit['chronic_conditions']
    }
    ai_eval = ClinicalTriageEngine.evaluate(patient_info, vitals, symptoms)

    final_level = ai_eval['priority_level']
    final_score = ai_eval['urgency_score']

    if is_overridden and override_level in ['CRITICAL', 'URGENT', 'ROUTINE']:
        final_level = override_level
        # Adjust score according to level if overridden
        if final_level == 'CRITICAL':
            final_score = max(final_score, 85)
        elif final_level == 'URGENT':
            final_score = 50
        else:
            final_score = 15

    # Calculate estimated wait time based on queue ahead
    cursor.execute('''
        SELECT COUNT(*) FROM visits
        WHERE department_id = ? AND status = 'TRIAGED_WAITING'
        AND (
            CASE priority_level WHEN 'CRITICAL' THEN 1 WHEN 'URGENT' THEN 2 ELSE 3 END <
            CASE ? WHEN 'CRITICAL' THEN 1 WHEN 'URGENT' THEN 2 ELSE 3 END
            OR (priority_level = ? AND arrival_time < ?)
        )
    ''', (visit['department_id'], final_level, final_level, visit['arrival_time']))
    patients_ahead = cursor.fetchone()[0]

    wait_mins = 0 if final_level == 'CRITICAL' else (patients_ahead + 1) * visit['avg_consult_time_mins']

    # Update visit record
    cursor.execute('''
        UPDATE visits
        SET vitals_json = ?,
            symptoms_json = ?,
            priority_level = ?,
            priority_score = ?,
            status = 'TRIAGED_WAITING',
            triage_completed_at = CURRENT_TIMESTAMP,
            estimated_wait_mins = ?,
            triage_notes = ?
        WHERE id = ?
    ''', (
        json.dumps(vitals),
        json.dumps(symptoms),
        final_level,
        final_score,
        wait_mins,
        triage_notes,
        visit_id
    ))

    # Record Triage Assessment Decision Log for Transparency & Clinical Audit
    assessor_name = session.get('user_name', 'Nurse Kavita Nair')
    assessor_role = session.get('user_role', 'NURSE')
    cursor.execute('''
        INSERT INTO triage_assessments (
            visit_id, ai_recommended_level, ai_recommended_score, reasons_json,
            final_level, final_score, is_overridden, override_reason,
            assessed_by_name, assessed_by_role
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        visit_id,
        ai_eval['priority_level'],
        ai_eval['urgency_score'],
        json.dumps(ai_eval['reasons']),
        final_level,
        final_score,
        1 if is_overridden else 0,
        override_reason if is_overridden else None,
        assessor_name,
        assessor_role
    ))

    conn.commit()
    conn.close()

    # Event Payload
    event_payload = {
        'visit_id': visit_id,
        'token_no': visit['token_no'],
        'patient_name': visit['patient_name'],
        'department_id': visit['department_id'],
        'priority_level': final_level,
        'urgency_score': final_score,
        'is_overridden': is_overridden,
        'estimated_wait_mins': wait_mins,
        'reasons': ai_eval['reasons']
    }

    # Requirement 5: "Handle triage confirmation and critical queue updates synchronously"
    event_bus.dispatch_sync('TRIAGE_CONFIRMED', 'VISIT', visit_id, event_payload)
    if final_level in ['CRITICAL', 'URGENT']:
        event_bus.dispatch_sync('PRIORITY_ELEVATED', 'VISIT', visit_id, event_payload)

    # Requirement 5: "send routine notifications and reports asynchronously"
    notifs = []
    if final_level == 'CRITICAL':
        notifs.append({
            'recipient': 'Emergency Resuscitation Team',
            'role': 'DOCTOR',
            'channel': 'DASHBOARD_ALERT',
            'message': f"RED CODE ALERT: Patient {visit['patient_name']} ({visit['token_no']}) triaged as CRITICAL. Immediate doctor evaluation required.",
            'priority': 'CRITICAL'
        })
    else:
        notifs.append({
            'recipient': visit['patient_phone'],
            'role': 'PATIENT',
            'channel': 'SMS',
            'message': f"ApexCare Update: Token {visit['token_no']} triaged. Category: {final_level}. Est wait: ~{wait_mins} mins. Please watch the waiting hall display.",
            'priority': 'ROUTINE'
        })

    event_bus.dispatch_async('TRIAGE_NOTIFICATIONS', 'VISIT', visit_id, event_payload, notifications=notifs)

    log_audit('TRIAGE_ASSESSMENT', 'VISIT', visit_id,
              f"Triaged as {final_level} (Score {final_score}). Overridden: {is_overridden}. Reviewer: {assessor_name}")

    return jsonify({
        'success': True,
        'final_level': final_level,
        'final_score': final_score,
        'is_overridden': is_overridden,
        'wait_mins': wait_mins,
        'ai_eval': ai_eval
    })

# 5. Queue Status & Urgency-Ranked Listing API
@app.route('/api/queue', methods=['GET'])
def api_get_queue():
    dept_id = request.args.get('department_id')
    status_filter = request.args.get('status', 'ACTIVE')

    conn = get_db()
    cursor = conn.cursor()

    query = '''
        SELECT v.*, p.patient_code, p.name as patient_name, p.age, p.gender, p.known_allergies,
               dep.name as dept_name, dep.code as dept_code,
               d.name as assigned_doctor_name, d.room_no as assigned_room
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        JOIN departments dep ON v.department_id = dep.id
        LEFT JOIN doctors d ON v.assigned_doctor_id = d.id
        WHERE 1=1
    '''
    params = []

    if status_filter == 'ACTIVE':
        query += " AND v.status IN ('WAITING_TRIAGE', 'TRIAGED_WAITING', 'CALLED', 'IN_CONSULTATION')"
    elif status_filter:
        query += " AND v.status = ?"
        params.append(status_filter)

    if dept_id and dept_id.isdigit():
        query += " AND v.department_id = ?"
        params.append(int(dept_id))

    # Priority Queue Ordering:
    # 1. In consultation / Called first
    # 2. Priority: CRITICAL (1) > URGENT (2) > ROUTINE (3)
    # 3. Urgency Score descending
    # 4. Arrival time ascending (FIFO within same urgency)
    query += '''
        ORDER BY
            CASE v.status
                WHEN 'IN_CONSULTATION' THEN 1
                WHEN 'CALLED' THEN 2
                WHEN 'TRIAGED_WAITING' THEN 3
                WHEN 'WAITING_TRIAGE' THEN 4
                ELSE 5
            END ASC,
            CASE v.priority_level
                WHEN 'CRITICAL' THEN 1
                WHEN 'URGENT' THEN 2
                WHEN 'ROUTINE' THEN 3
                ELSE 4
            END ASC,
            v.priority_score DESC,
            v.arrival_time ASC
    '''

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    queue_list = []
    for idx, r in enumerate(rows, 1):
        item = dict(r)
        item['queue_position'] = idx
        if item.get('vitals_json'):
            try:
                item['vitals'] = json.loads(item['vitals_json'])
            except:
                item['vitals'] = {}
        if item.get('symptoms_json'):
            try:
                item['symptoms'] = json.loads(item['symptoms_json'])
            except:
                item['symptoms'] = []
        queue_list.append(item)

    return jsonify({'success': True, 'queue': queue_list, 'total': len(queue_list)})

# 6. Doctor Allocation & Status Management API
@app.route('/api/doctors', methods=['GET'])
def api_get_doctors():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT d.*, dep.name as dept_name, dep.code as dept_code,
               v.token_no as active_token, p.name as active_patient_name
        FROM doctors d
        JOIN departments dep ON d.department_id = dep.id
        LEFT JOIN visits v ON d.current_visit_id = v.id
        LEFT JOIN patients p ON v.patient_id = p.id
        ORDER BY d.department_id ASC, d.id ASC
    ''')
    doctors = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'doctors': doctors})

@app.route('/api/doctors/status', methods=['POST'])
def api_update_doctor_status():
    data = request.json or {}
    doctor_id = data.get('doctor_id')
    new_status = data.get('status') # AVAILABLE, ON_BREAK, OFF_DUTY

    if not doctor_id or new_status not in ['AVAILABLE', 'ON_BREAK', 'OFF_DUTY']:
        return jsonify({'success': False, 'error': 'Invalid doctor ID or status.'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE doctors SET status = ? WHERE id = ?", (new_status, doctor_id))
    cursor.execute("SELECT d.name, dep.name as dept_name, d.department_id FROM doctors d JOIN departments dep ON d.department_id = dep.id WHERE d.id = ?", (doctor_id,))
    doc = cursor.fetchone()
    conn.commit()
    conn.close()

    # Event Generation: Doctor status changed
    event_payload = {
        'doctor_id': doctor_id,
        'doctor_name': doc['name'],
        'new_status': new_status,
        'department_id': doc['department_id']
    }

    if new_status == 'AVAILABLE':
        # Synchronous event to allow immediate next-patient dispatch
        event_bus.dispatch_sync('DOCTOR_AVAILABLE', 'DOCTOR', doctor_id, event_payload)
    else:
        event_bus.dispatch_async('DOCTOR_STATUS_CHANGED', 'DOCTOR', doctor_id, event_payload)

    log_audit('DOCTOR_STATUS_CHANGE', 'DOCTOR', doctor_id, f"{doc['name']} status updated to {new_status}")
    return jsonify({'success': True, 'doctor_id': doctor_id, 'status': new_status})

@app.route('/api/doctors/call-next', methods=['POST'])
def api_call_next_patient():
    """Allocates the highest-priority waiting patient in the department to the calling doctor."""
    data = request.json or {}
    doctor_id = data.get('doctor_id')
    visit_id = data.get('visit_id') # Optional direct pick

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT d.*, dep.name as dept_name FROM doctors d JOIN departments dep ON d.department_id = dep.id WHERE d.id = ?", (doctor_id,))
    doctor = cursor.fetchone()
    if not doctor:
        conn.close()
        return jsonify({'success': False, 'error': 'Doctor not found.'}), 404

    # If visit_id not specified, find top priority patient in this doctor's department or emergency
    if not visit_id:
        cursor.execute('''
            SELECT v.id FROM visits v
            WHERE (v.department_id = ? OR v.priority_level = 'CRITICAL')
              AND v.status = 'TRIAGED_WAITING'
            ORDER BY
                CASE v.priority_level
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'URGENT' THEN 2
                    WHEN 'ROUTINE' THEN 3
                    ELSE 4
                END ASC,
                v.priority_score DESC,
                v.arrival_time ASC
            LIMIT 1
        ''', (doctor['department_id'],))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'No patients currently waiting in this department queue.'})
        visit_id = row['id']

    # Update visit to IN_CONSULTATION and doctor to BUSY
    cursor.execute('''
        UPDATE visits
        SET status = 'IN_CONSULTATION',
            assigned_doctor_id = ?,
            consultation_start_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (doctor_id, visit_id))

    cursor.execute('''
        UPDATE doctors
        SET status = 'BUSY',
            current_visit_id = ?
        WHERE id = ?
    ''', (visit_id, doctor_id))

    cursor.execute('''
        SELECT v.*, p.name as patient_name, p.phone as patient_phone
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        WHERE v.id = ?
    ''', (visit_id,))
    visit = cursor.fetchone()

    conn.commit()
    conn.close()

    event_payload = {
        'doctor_id': doctor_id,
        'doctor_name': doctor['name'],
        'room_no': doctor['room_no'],
        'visit_id': visit_id,
        'token_no': visit['token_no'],
        'patient_name': visit['patient_name'],
        'priority_level': visit['priority_level']
    }

    # Synchronous event for immediate Public Display audio chime
    event_bus.dispatch_sync('PATIENT_CALLED', 'VISIT', visit_id, event_payload)

    # Async notification to patient
    notifs = [{
        'recipient': visit['patient_phone'],
        'role': 'PATIENT',
        'channel': 'SMS',
        'message': f"Token {visit['token_no']}: {visit['patient_name']}, please proceed to Room {doctor['room_no']} ({doctor['name']}) now for your consultation.",
        'priority': 'ROUTINE'
    }]
    event_bus.dispatch_async('PATIENT_CALLED_NOTIFICATION', 'VISIT', visit_id, event_payload, notifications=notifs)

    log_audit('PATIENT_CALLED', 'DOCTOR', doctor_id,
              f"{doctor['name']} called patient {visit['patient_name']} (Token: {visit['token_no']}) to Room {doctor['room_no']}")

    return jsonify({'success': True, 'visit_id': visit_id, 'token_no': visit['token_no'], 'patient_name': visit['patient_name']})

@app.route('/api/doctors/complete', methods=['POST'])
def api_complete_consultation():
    """Completes the consultation, adds clinical discharge notes, and marks doctor as AVAILABLE."""
    data = request.json or {}
    doctor_id = data.get('doctor_id')
    visit_id = data.get('visit_id')
    doctor_notes = data.get('doctor_notes', 'Consultation complete. Prescribed appropriate medication and outpatient review.').strip()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE visits
        SET status = 'COMPLETED',
            completed_at = CURRENT_TIMESTAMP,
            doctor_notes = ?
        WHERE id = ?
    ''', (doctor_notes, visit_id))

    cursor.execute('''
        UPDATE doctors
        SET status = 'AVAILABLE',
            current_visit_id = NULL
        WHERE id = ?
    ''', (doctor_id,))

    cursor.execute('''
        SELECT v.token_no, p.name as patient_name, d.name as doctor_name
        FROM visits v
        JOIN patients p ON v.patient_id = p.id
        JOIN doctors d ON d.id = ?
        WHERE v.id = ?
    ''', (doctor_id, visit_id))
    info = cursor.fetchone()

    conn.commit()
    conn.close()

    event_payload = {
        'doctor_id': doctor_id,
        'visit_id': visit_id,
        'token_no': info['token_no'] if info else '',
        'doctor_name': info['doctor_name'] if info else ''
    }

    # Synchronous event to refresh queue and trigger next allocation
    event_bus.dispatch_sync('VISIT_COMPLETED', 'VISIT', visit_id, event_payload)
    event_bus.dispatch_sync('DOCTOR_AVAILABLE', 'DOCTOR', doctor_id, event_payload)

    log_audit('CONSULTATION_COMPLETE', 'VISIT', visit_id, f"Consultation completed by {info['doctor_name'] if info else 'Doctor'}")

    return jsonify({'success': True, 'visit_id': visit_id, 'status': 'COMPLETED'})

# 7. Real-Time Server-Sent Events (SSE) Stream
@app.route('/api/events/stream')
def sse_event_stream():
    """Provides continuous server-sent events to browser clients for zero-latency dashboard updates."""
    def event_stream():
        q = event_bus.subscribe_sse()
        try:
            # Yield initial connection heartbeat
            yield f"data: {json.dumps({'type': 'CONNECTED', 'timestamp': datetime.now().isoformat()})}\n\n"
            while True:
                event_data = q.get()
                yield f"data: {json.dumps(event_data)}\n\n"
        except GeneratorExit:
            event_bus.unsubscribe_sse(q)

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

# 8. Audit Logs & System Activity API
@app.route('/api/audit-logs')
def api_audit_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100")
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'logs': logs})

# 9. Configurable Triage Rules API
@app.route('/api/rules', methods=['GET', 'POST'])
def api_manage_rules():
    conn = get_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.json or {}
        rule_id = data.get('rule_id')
        is_active = 1 if data.get('is_active') else 0
        score_weight = data.get('score_weight')

        if rule_id:
            if score_weight is not None:
                cursor.execute("UPDATE triage_rules SET score_weight = ?, is_active = ? WHERE id = ?", (score_weight, is_active, rule_id))
            else:
                cursor.execute("UPDATE triage_rules SET is_active = ? WHERE id = ?", (is_active, rule_id))
            conn.commit()
            log_audit('RULE_UPDATE', 'TRIAGE_RULE', rule_id, f"Updated rule {rule_id}: active={is_active}")

        conn.close()
        return jsonify({'success': True})

    cursor.execute("SELECT * FROM triage_rules ORDER BY category ASC, score_weight DESC")
    rules = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'rules': rules})

# -----------------------------------------------------------------------------
# 10. Interactive Hackathon Demonstration Scenario (Expected Deliverable)
# "Demonstrate at least one urgent case being prioritised ahead of routine cases."
# -----------------------------------------------------------------------------
@app.route('/api/demo/run-scenario', methods=['POST'])
def api_run_hackathon_demo():
    """
    Simulates the exact hackathon requirement:
    1. Arrive 3 Routine patients first with mild complaints.
    2. Then an acute CRITICAL patient (Chest Pain + Hypoxia) arrives.
    3. AI Triage automatically scores and flags the Critical patient.
    4. Synchronous Priority Queue updates instantly place the Critical patient
       at the top of the queue ahead of all 3 earlier routine cases!
    """
    conn = get_db()
    cursor = conn.cursor()

    # Step A: Register 3 Routine Cases
    routine_cases = [
        {
            'name': 'Rahul Sharma (Demo)',
            'age': 32,
            'gender': 'Male',
            'complaint': 'Mild seasonal allergy and sneezing for 3 days',
            'symptoms': ['MILD_COUGH_COLD'],
            'vitals': {'hr': 72, 'systolic_bp': 120, 'diastolic_bp': 80, 'spo2': 98, 'temp_c': 37.0, 'rr': 15, 'pain_score': 1},
            'dept': 4
        },
        {
            'name': 'Pooja Verma (Demo)',
            'age': 27,
            'gender': 'Female',
            'complaint': 'Twisted ankle while jogging, mild swelling, can bear weight',
            'symptoms': ['ANKLE_SPRAIN_MILD'],
            'vitals': {'hr': 76, 'systolic_bp': 118, 'diastolic_bp': 78, 'spo2': 99, 'temp_c': 36.8, 'rr': 16, 'pain_score': 3},
            'dept': 6
        },
        {
            'name': 'Suresh Menon (Demo)',
            'age': 48,
            'gender': 'Male',
            'complaint': 'Monthly blood pressure prescription refill',
            'symptoms': ['MEDICATION_REFILL'],
            'vitals': {'hr': 70, 'systolic_bp': 124, 'diastolic_bp': 82, 'spo2': 98, 'temp_c': 36.9, 'rr': 14, 'pain_score': 0},
            'dept': 4
        }
    ]

    routine_tokens = []
    for c in routine_cases:
        p_code = f"PAT-DEMO-{uuid.uuid4().hex[:4].upper()}"
        cursor.execute("INSERT INTO patients (patient_code, name, age, gender, phone, known_allergies, chronic_conditions) VALUES (?, ?, ?, ?, '+91 99999 11111', 'None', 'None')",
                       (p_code, c['name'], c['age'], c['gender']))
        p_id = cursor.lastrowid

        cursor.execute("SELECT COUNT(*) FROM visits")
        tkn = f"TKN-{100 + cursor.fetchone()[0] + 1}"

        eval_res = ClinicalTriageEngine.evaluate({'age': c['age']}, c['vitals'], c['symptoms'])

        cursor.execute('''
            INSERT INTO visits (
                token_no, patient_id, department_id, chief_complaint, symptoms_json, vitals_json,
                priority_level, priority_score, status, estimated_wait_mins, triage_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'TRIAGED_WAITING', ?, ?)
        ''', (
            tkn, p_id, c['dept'], c['complaint'], json.dumps(c['symptoms']), json.dumps(c['vitals']),
            eval_res['priority_level'], eval_res['urgency_score'], 30, 'Stable routine presentation.'
        ))
        v_id = cursor.lastrowid
        routine_tokens.append({'token': tkn, 'name': c['name'], 'priority': eval_res['priority_level']})

    # Step B: An Urgent/Critical Emergency Arrives
    critical_case = {
        'name': 'Bikramjit Patnaik (CRITICAL DEMO)',
        'age': 59,
        'gender': 'Male',
        'complaint': 'Sudden acute crushing chest pain radiating to left jaw, diaphoresis and severe shortness of breath',
        'symptoms': ['CHEST_PAIN_SEVERE', 'SPO2_HYPOXIA'],
        'vitals': {'hr': 134, 'systolic_bp': 88, 'diastolic_bp': 56, 'spo2': 87, 'temp_c': 37.1, 'rr': 30, 'pain_score': 9},
        'dept': 1 # Emergency / Resuscitation
    }

    crit_code = f"PAT-DEMO-{uuid.uuid4().hex[:4].upper()}"
    cursor.execute("INSERT INTO patients (patient_code, name, age, gender, phone, known_allergies, chronic_conditions) VALUES (?, ?, ?, ?, '+91 99999 99999', 'Aspirin', 'Coronary Artery Disease')",
                   (crit_code, critical_case['name'], critical_case['age'], critical_case['gender']))
    crit_pid = cursor.lastrowid

    cursor.execute("SELECT COUNT(*) FROM visits")
    crit_tkn = f"TKN-{100 + cursor.fetchone()[0] + 1}"

    crit_eval = ClinicalTriageEngine.evaluate({'age': critical_case['age'], 'chronic_conditions': 'Coronary Artery Disease'}, critical_case['vitals'], critical_case['symptoms'])

    cursor.execute('''
        INSERT INTO visits (
            token_no, patient_id, department_id, chief_complaint, symptoms_json, vitals_json,
            priority_level, priority_score, status, estimated_wait_mins, triage_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'TRIAGED_WAITING', 0, ?)
    ''', (
        crit_tkn, crit_pid, critical_case['dept'], critical_case['complaint'],
        json.dumps(critical_case['symptoms']), json.dumps(critical_case['vitals']),
        crit_eval['priority_level'], crit_eval['urgency_score'],
        'EMERGENCY RESUSCITATION: Crushing chest pain + SpO2 87% + Hypotension. EKG and crash cart alerted.'
    ))
    crit_vid = cursor.lastrowid

    # Record Triage Assessment Record
    cursor.execute('''
        INSERT INTO triage_assessments (
            visit_id, ai_recommended_level, ai_recommended_score, reasons_json,
            final_level, final_score, is_overridden, assessed_by_name, assessed_by_role
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 'Nurse Kavita Nair', 'NURSE')
    ''', (
        crit_vid, crit_eval['priority_level'], crit_eval['urgency_score'],
        json.dumps(crit_eval['reasons']), crit_eval['priority_level'], crit_eval['urgency_score']
    ))

    conn.commit()
    conn.close()

    # Synchronously broadcast Critical Priority Elevation
    demo_event = {
        'visit_id': crit_vid,
        'token_no': crit_tkn,
        'patient_name': critical_case['name'],
        'priority_level': 'CRITICAL',
        'urgency_score': crit_eval['urgency_score'],
        'reasons': crit_eval['reasons'],
        'preempted_cases': [r['token'] for r in routine_tokens]
    }
    event_bus.dispatch_sync('PRIORITY_ELEVATED', 'VISIT', crit_vid, demo_event)

    # Queue Async notification to Emergency Resuscitation team
    notifs = [{
        'recipient': 'Emergency Room Crash Team',
        'role': 'DOCTOR',
        'channel': 'DASHBOARD_ALERT',
        'message': f"CRITICAL RED ALERT: Patient {critical_case['name']} ({crit_tkn}) has acute STEMI / Hypoxia. Immediate priority preemption applied.",
        'priority': 'CRITICAL'
    }]
    event_bus.dispatch_async('CRITICAL_PREEMPTION_ALERT', 'VISIT', crit_vid, demo_event, notifications=notifs)

    log_audit('HACKATHON_DEMO', 'QUEUE', crit_vid,
              f"Preemption scenario executed: Critical patient {crit_tkn} prioritized ahead of routine tokens {[r['token'] for r in routine_tokens]}")

    return jsonify({
        'success': True,
        'message': 'Demonstration Scenario successfully executed! Urgent/Critical case prioritized to Position #1 ahead of routine cases.',
        'routine_tokens': routine_tokens,
        'critical_case': {
            'token': crit_tkn,
            'name': critical_case['name'],
            'priority': 'CRITICAL',
            'score': crit_eval['urgency_score'],
            'reasons': crit_eval['reasons']
        }
    })

@app.route('/api/demo/reset', methods=['POST'])
def api_reset_demo():
    """Resets database and re-seeds with clean baseline data."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM triage_assessments")
    cursor.execute("DELETE FROM notifications_queue")
    cursor.execute("DELETE FROM event_logs")
    cursor.execute("DELETE FROM visits")
    cursor.execute("DELETE FROM patients")
    cursor.execute("DELETE FROM doctors")
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM symptoms_catalog")
    cursor.execute("DELETE FROM triage_rules")
    cursor.execute("DELETE FROM departments")
    conn.commit()
    conn.close()

    seed_initial_data()
    log_audit('DEMO_RESET', 'SYSTEM', 'ALL', "Database reset and re-seeded to initial state.")
    return jsonify({'success': True, 'message': 'Database reset and re-seeded to clean hackathon baseline state.'})

if __name__ == '__main__':
    print("ApexCare Patient Triage & Queue Management Server running on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
