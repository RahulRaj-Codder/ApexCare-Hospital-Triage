# ApexCare: Patient Triage & Queue Management System
### A Smarter, Urgency-Aware Hospital Patient Flow System
**GEC HACKATHON 2026 — PROBLEM STATEMENT 01**  
*Gandhi Engineering College, Bhubaneswar*

---

## 🏥 Problem Overview & Executive Summary

In emergency rooms and outpatient departments, managing patient arrivals and queues manually leads to overcrowding, prolonged delays, and the catastrophic risk of deteriorating acute patients going unrecognized. 

**ApexCare Flow** is an urgency-aware clinical decision-support and queue orchestration system that:
1. Registers patients and records objective vital signs and presenting symptoms.
2. Evaluates clinical urgency using an algorithmic triage engine compatible with the **Manchester Triage System (MTS)** and **Emergency Severity Index (ESI)**.
3. Automatically classifies patients into **CRITICAL (Priority 1)**, **URGENT (Priority 2)**, or **ROUTINE (Priority 3)** categories.
4. Explains the exact clinical rationale (hypoxia thresholds, hemodynamic collapse, chest pain red flags, comorbidity risk).
5. Provides authorised doctors and nurses with a mandatory-audited **manual review and override path**.
6. Employs a dual-pipeline architecture:
   - **Synchronous Critical Pipeline**: Immediate priority elevation, real-time queue reordering, and emergency buzzer alerts.
   - **Asynchronous Routine Pipeline**: Non-blocking background worker handling simulated SMS notifications, email reminders, and PA audio chimes.
7. Features a **1-Click Live Demonstration** proving the required deliverable: **urgent and critical cases dynamically pre-empting earlier routine patients to take Position #1 in the queue**.

---

## 🎯 Compliance Matrix: GEC Hackathon Requirements

| # | Requirement Specification | System Implementation Details | Verification Status |
|---|---------------------------|-------------------------------|---------------------|
| **1** | **Data Models** for patients, visits, symptoms, doctors, departments | Relational SQLite schema with `patients`, `visits`, `symptoms_catalog`, `doctors`, `departments`, `triage_assessments`, `triage_rules`, `audit_logs`, `event_logs`, and `notifications_queue`. | ✅ 100% Tested & Verified |
| **2** | **APIs** for registration, triage, queue status, doctor allocation | RESTful endpoints: `POST /api/patients`, `POST /api/visits/register`, `POST /api/triage/assess`, `GET /api/queue`, `POST /api/doctors/call-next`, `POST /api/doctors/complete`. | ✅ 100% Tested & Verified |
| **3** | **Configurable Rules & AI Priority Recommendation** | MTS/ESI triage engine scoring vitals (SpO2, BP, HR, RR, Temp, Pain) and red flags. Full clinician manual override modal with mandatory clinical rationale. | ✅ 100% Tested & Verified |
| **4** | **Event Generation** | Automated event dispatching on patient registration (`PATIENT_REGISTERED`), priority change (`PRIORITY_ELEVATED`), doctor availability (`DOCTOR_AVAILABLE`), and patient call (`PATIENT_CALLED`). | ✅ 100% Tested & Verified |
| **5** | **Sync vs Async Workflows** | Synchronous execution for critical triage confirmation and queue re-indexing; background daemon thread worker processing `notifications_queue` asynchronously. | ✅ 100% Tested & Verified |
| **6** | **Role-Based Access Control (RBAC) & Audit Records** | Granular roles (`DOCTOR`, `NURSE`, `ADMIN`, `KIOSK`) with 1-click evaluator switcher. Tamper-evident audit trail recording user, role, action, IP, and timestamps. | ✅ 100% Tested & Verified |
| **DELIV** | **Demonstrate Urgent Case Prioritised Ahead of Routine Cases** | Interactive 1-click live simulation: 3 routine patients arrive first (TKN-R1, TKN-R2, TKN-R3), followed by a critical chest pain/hypoxia emergency (TKN-Crit). Queue instantly re-sorts placing the critical case at Position #1! | ✅ 100% Tested & Verified |

---

## 📐 System Architecture

```
                          ┌────────────────────────┐
                          │   Patient Arrival /    │
                          │   Reception Intake     │
                          └───────────┬────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │    Nurse Triage Station   │
                        │ (Vitals & Symptoms Input) │
                        └─────────────┬─────────────┘
                                      │
                                      ▼
                      ┌───────────────────────────────┐
                      │    AI Clinical Triage Engine  │
                      │  - SpO2 / Hemodynamics Rules  │
                      │  - Red Flag Symptoms Catalog  │
                      │  - Age & Comorbidity Factors  │
                      └───────────────┬───────────────┘
                                      │
                        [ AI Recommendation & Score ]
                                      │
                                      ▼
                     ┌─────────────────────────────────┐
                     │    Clinician Decision Gate      │
                     │  - Accept AI Recommendation     │
                     │  - OR Manual Override (+Audit)  │
                     └────────────────┬────────────────┘
                                      │
            ┌─────────────────────────┴─────────────────────────┐
            │                                                   │
  [ Critical Path: Synchronous ]                     [ Routine Path: Asynchronous ]
            ▼                                                   ▼
┌──────────────────────────────┐                   ┌──────────────────────────────┐
│  Synchronous Event Dispatch  │                   │  Background Daemon Thread    │
│  - Real-time Queue Reorder   │                   │  - Notifications Queue       │
│  - Critical Priority Badge   │                   │  - Simulated Patient SMS     │
│  - SSE Push to Connected UIs │                   │  - PA Audio Chimes / Reports │
└──────────────┬───────────────┘                   └──────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Urgency-Aware Live Queue    │
│  (Critical > Urgent > Rout)  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Doctor Consultation Room    │
│  - Call Next Urgent Patient  │
│  - Complete & Discharge      │
└──────────────────────────────┘
```

---

## 🚀 Quickstart Guide: Running the Application

### Prerequisites
- Python 3.9+ (Python 3.13 installed)
- Dependencies: `Flask` (already installed in local environment)

### Start the Server
```powershell
cd d:\gec_triage_queue_system
python app.py
```
Open your web browser and navigate to:
👉 **`http://localhost:5000`**

---

## 🖥️ User Interface Overview & Key Portals

1. **Operations Dashboard (`/`)**:
   - Executive metrics: Active Visits, Critical (P1) Waiting, Urgent (P2) Waiting, Routine (P3) Waiting, Available Doctors, Discharged.
   - **1-Click Hackathon Preemption Demo Button**: Instantly triggers the live demonstration scenario with explainable AI breakdowns.
   - Live Patient Urgency Queue table and Doctor Room Roster.

2. **Nurse Triage Station (`/triage`)**:
   - Select waiting patients from intake list.
   - Enter objective vitals: Heart Rate, Blood Pressure, SpO2 (%), Temperature, Respiratory Rate, Pain Score (0-10), GCS.
   - Checkbox catalog for clinical red flags (crushing chest pain, severe hypoxia, stroke FAST signs, anaphylaxis, active hemorrhage).
   - **Real-Time Live AI Preview Card**: Computes urgency score and renders transparent triggered rules dynamically as the nurse types.
   - **Clinician Override Box**: Authorised staff can override priority level with a mandatory justification note.

3. **Live Hospital Queue (`/queue`)**:
   - Urgency-ranked listing with color-coded badges (`CRITICAL` in Red, `URGENT` in Amber, `ROUTINE` in Emerald).
   - Filter by department (Emergency, Cardiology, Pulmonology, General Medicine, Pediatrics, Orthopedics) or priority level.
   - Allocate and call patients to consultation rooms.

4. **Doctor Workstation (`/doctor`)**:
   - Displays active patient under consultation, complete medical history, nurse triage notes, and vitals.
   - Doctor status toggle: `AVAILABLE`, `ON_BREAK`, `OFF_DUTY` (emits real-time availability event).
   - "Call Next Patient" button (auto-pulls top priority case in doctor's department).
   - Clinical consultation notes and discharge completion.

5. **Waiting Hall TV Board (`/display`)**:
   - High-contrast, privacy-preserving public display screen for waiting hall monitors.
   - Real-time token number, room assignment, and status.
   - Synthesised auditory chime via Web Audio API when a patient is called or emergency priority is elevated.

6. **Configurable Rules Engine (`/rules`)**:
   - Admin control panel to tweak physiological threshold score weights and toggle clinical rules.

7. **Audit & Event Hub (`/audit`)**:
   - Tamper-evident clinical audit log with user, role, action, and client IP.
   - Real-time event log distinguishing Synchronous Critical events from Asynchronous Routine events.
   - Background worker notification queue monitor.

---

## 🧪 Running the Automated Test Suite

A comprehensive test suite covering all 6 functional requirements and the urgent preemption deliverable is included:

```powershell
python d:\gec_triage_queue_system\test_system.py
```

### Test Results:
```text
Ran 7 tests in 0.857s

OK

[PASSED] Test 1: Data models and baseline catalog verified.
[PASSED] Test 2: Patient registration and visit intake APIs verified.
[PASSED] Test 3: AI Triage Engine clinical scoring & explainability verified.
[PASSED] Test 4: Clinician manual override & clinical audit logging verified.
[PASSED] Test 5: Urgent Preemption Deliverable Verified! Critical token at Position #1 ahead of routine positions.
[PASSED] Test 6: Sync vs Async event and notification workflows verified.
[PASSED] Test 7: Doctor allocation, patient calling & consultation discharge verified.
```

---

## 🔒 Security & Access Control (RBAC)

The application implements role-based access control with predefined user profiles:
- **`ADMIN`**: Full visibility, rules engine tuning, operational audit log review.
- **`NURSE`**: Patient arrival intake, vitals assessment, triage evaluation & override.
- **`DOCTOR`**: Consultation workstation, clinical examination notes, patient calling and discharge.
- **`KIOSK`**: Patient reception check-in.

*Quick Switcher*: For hackathon evaluators, a convenient role switcher in the top navigation header allows switching between roles with one click.
