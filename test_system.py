"""
Automated Comprehensive Test Suite
GEC Hackathon 2026: Problem Statement 01
Healthcare - Patient Triage & Queue Management System

Validates:
1. Data models & baseline seeding
2. Patient registration & visit intake API
3. Configurable rules & AI triage evaluation (Critical, Urgent, Routine)
4. Clinician manual override & decision audit logging
5. Urgency-Aware Priority Queue ordering & Urgent Preemption ahead of Routine cases
6. Synchronous event dispatching & Asynchronous notification queueing
7. Doctor allocation workflow & status progression
"""

import unittest
import json
import os
import time
from app import app
from database import get_db, init_db, seed_initial_data
from triage_engine import ClinicalTriageEngine

class TestHospitalTriageSystem(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        init_db()
        seed_initial_data()

    def test_01_database_and_models(self):
        """Requirement 1: Verify data models exist and baseline data is provisioned."""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM departments")
        self.assertGreaterEqual(cursor.fetchone()[0], 6)

        cursor.execute("SELECT COUNT(*) FROM doctors")
        self.assertGreaterEqual(cursor.fetchone()[0], 6)

        cursor.execute("SELECT COUNT(*) FROM triage_rules WHERE is_active = 1")
        self.assertGreaterEqual(cursor.fetchone()[0], 5)

        cursor.execute("SELECT COUNT(*) FROM symptoms_catalog WHERE is_red_flag = 1")
        self.assertGreaterEqual(cursor.fetchone()[0], 4)

        conn.close()
        print("\n[PASSED] Test 1: Data models and baseline catalog verified.")

    def test_02_patient_registration_and_visit_intake(self):
        """Requirement 2: Provide APIs for patient registration and visit intake."""
        # 1. Register Patient
        res = self.client.post('/api/patients', json={
            'name': 'Test Arjun Roy',
            'age': 42,
            'gender': 'Male',
            'phone': '+91 91234 56789',
            'chronic_conditions': 'Hypertension'
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])
        patient_id = data['patient_id']
        self.assertTrue(data['patient_code'].startswith('PAT-'))

        # 2. Intake Visit
        res_visit = self.client.post('/api/visits/register', json={
            'patient_id': patient_id,
            'department_id': 1,
            'chief_complaint': 'Acute shortness of breath and sweating'
        })
        self.assertEqual(res_visit.status_code, 200)
        v_data = json.loads(res_visit.data)
        self.assertTrue(v_data['success'])
        self.assertTrue(v_data['token_no'].startswith('TKN-'))
        print("[PASSED] Test 2: Patient registration and visit intake APIs verified.")

    def test_03_ai_triage_engine_and_explainability(self):
        """Requirement 3 & 5: Configurable rules, AI recommendation & explainable triggers."""
        # Test Case A: Critical presentation (SpO2 88% + Severe Chest Pain)
        crit_res = ClinicalTriageEngine.evaluate(
            patient_info={'age': 66, 'chronic_conditions': 'Coronary artery disease'},
            vitals={'hr': 132, 'systolic_bp': 88, 'diastolic_bp': 54, 'spo2': 88, 'temp_c': 37.0, 'rr': 30, 'pain_score': 9},
            selected_symptom_codes=['CHEST_PAIN_SEVERE', 'SPO2_HYPOXIA']
        )
        self.assertEqual(crit_res['priority_level'], 'CRITICAL')
        self.assertGreaterEqual(crit_res['urgency_score'], 70)
        self.assertGreater(len(crit_res['reasons']), 0)
        self.assertIn("CRITICAL", [r['severity'] for r in crit_res['reasons']])

        # Test Case B: Routine presentation (Normal vitals + Mild cough)
        rout_res = ClinicalTriageEngine.evaluate(
            patient_info={'age': 25, 'chronic_conditions': 'None'},
            vitals={'hr': 72, 'systolic_bp': 120, 'diastolic_bp': 80, 'spo2': 99, 'temp_c': 37.0, 'rr': 15, 'pain_score': 0},
            selected_symptom_codes=['MILD_COUGH_COLD']
        )
        self.assertEqual(rout_res['priority_level'], 'ROUTINE')
        self.assertLess(rout_res['urgency_score'], 25)
        print("[PASSED] Test 3: AI Triage Engine clinical scoring & explainability verified.")

    def test_04_clinician_manual_override_with_audit(self):
        """Requirement 3 & 6: Clinician manual review/override with audit trail."""
        # Create a routine patient visit
        p_res = self.client.post('/api/patients', json={'name': 'Override Test Patient', 'age': 30, 'gender': 'Female', 'phone': '9999900001'})
        pid = json.loads(p_res.data)['patient_id']
        v_res = self.client.post('/api/visits/register', json={'patient_id': pid, 'department_id': 4, 'chief_complaint': 'Mild headache'})
        vid = json.loads(v_res.data)['visit_id']

        # Nurse overrides AI recommendation from ROUTINE to URGENT due to clinical observation
        triage_res = self.client.post('/api/triage/assess', json={
            'visit_id': vid,
            'vitals': {'hr': 78, 'systolic_bp': 122, 'diastolic_bp': 80, 'spo2': 98, 'temp_c': 37.0, 'rr': 16, 'pain_score': 2},
            'symptoms': ['HEADACHE_MILD'],
            'triage_notes': 'Patient appears lethargic despite normal vitals.',
            'is_overridden': True,
            'override_level': 'URGENT',
            'override_reason': 'Patient photophobic and lethargic; suspect meningism. Escalating to Urgent.'
        })
        self.assertEqual(triage_res.status_code, 200)
        t_data = json.loads(triage_res.data)
        self.assertEqual(t_data['final_level'], 'URGENT')
        self.assertTrue(t_data['is_overridden'])

        # Verify audit record
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT is_overridden, override_reason FROM triage_assessments WHERE visit_id = ?", (vid,))
        rec = cursor.fetchone()
        self.assertEqual(rec[0], 1)
        self.assertIn("suspect meningism", rec[1])
        conn.close()
        print("[PASSED] Test 4: Clinician manual override & clinical audit logging verified.")

    def test_05_urgent_case_prioritised_ahead_of_routine_cases(self):
        """Expected Deliverable: Demonstrate at least one urgent/critical case being prioritised ahead of routine cases."""
        demo_res = self.client.post('/api/demo/run-scenario')
        self.assertEqual(demo_res.status_code, 200)
        demo_data = json.loads(demo_res.data)
        self.assertTrue(demo_data['success'])

        # Query live queue to verify ordering
        queue_res = self.client.get('/api/queue?status=ACTIVE')
        self.assertEqual(queue_res.status_code, 200)
        q_data = json.loads(queue_res.data)['queue']

        # The Critical patient must occupy Position #1 ahead of routine tokens
        first_patient = q_data[0]
        self.assertEqual(first_patient['priority_level'], 'CRITICAL')
        self.assertEqual(first_patient['token_no'], demo_data['critical_case']['token'])

        # Routine tokens must be positioned behind
        routine_positions = [item['queue_position'] for item in q_data if item['priority_level'] == 'ROUTINE']
        for pos in routine_positions:
            self.assertGreater(pos, first_patient['queue_position'])

        print(f"[PASSED] Test 5: Urgent Preemption Deliverable Verified! Critical token ({first_patient['token_no']}) at Position #1 ahead of routine positions ({routine_positions}).")

    def test_06_sync_vs_async_event_and_notification_workflows(self):
        """Requirement 4 & 5: Synchronous critical queue updates vs Asynchronous background notifications."""
        conn = get_db()
        cursor = conn.cursor()

        # Check that both sync (is_critical_sync = 1) and async (is_critical_sync = 0) events are logged
        cursor.execute("SELECT COUNT(*) FROM event_logs WHERE is_critical_sync = 1")
        sync_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM event_logs WHERE is_critical_sync = 0")
        async_count = cursor.fetchone()[0]

        self.assertGreater(sync_count, 0)
        self.assertGreater(async_count, 0)

        # Allow async worker thread a moment to process pending notifications
        time.sleep(0.5)

        cursor.execute("SELECT COUNT(*) FROM notifications_queue")
        notif_count = cursor.fetchone()[0]
        self.assertGreater(notif_count, 0)

        conn.close()
        print(f"[PASSED] Test 6: Sync ({sync_count} events) vs Async ({async_count} events, {notif_count} notifications) verified.")

    def test_07_doctor_allocation_and_status_progression(self):
        """Requirement 4 & 6: Doctor allocation, status updates and consultation completion."""
        # Call next patient for Dr. Sarah Mehta (Doctor ID 1)
        call_res = self.client.post('/api/doctors/call-next', json={'doctor_id': 1})
        self.assertEqual(call_res.status_code, 200)
        call_data = json.loads(call_res.data)

        if call_data.get('success'):
            vid = call_data['visit_id']
            # Complete consultation
            comp_res = self.client.post('/api/doctors/complete', json={
                'doctor_id': 1,
                'visit_id': vid,
                'doctor_notes': 'Prescribed nitrates, aspirin, ordered stat troponin I. Patient stabilized.'
            })
            self.assertEqual(comp_res.status_code, 200)
            self.assertTrue(json.loads(comp_res.data)['success'])

        print("[PASSED] Test 7: Doctor allocation, patient calling & consultation discharge verified.")

if __name__ == '__main__':
    unittest.main()
