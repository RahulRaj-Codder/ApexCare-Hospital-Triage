"""
Interactive Project Overview & CLI Guide
GEC Hackathon 2026: Problem Statement 01
Healthcare - Patient Triage & Queue Management System (ApexCare Flow)
"""

import sys
import os
import subprocess

PROJECT_INFO = {
    "title": "ApexCare Flow: Urgency-Aware Patient Triage & Queue Management",
    "hackathon": "GEC HACKATHON 2026",
    "problem_statement": "Problem Statement 01: Healthcare",
    "institution": "Gandhi Engineering College, Bhubaneswar",
    "author": "Hackathon Development Team"
}

FEATURES = [
    ("1. Data Models", "Relational schema for patients, visits, symptoms catalog, doctors, and departments (SQLite)."),
    ("2. RESTful APIs", "Full APIs for intake, triage evaluation, live queue retrieval, and doctor allocation."),
    ("3. AI Clinical Triage", "MTS & ESI scoring analyzing SpO2, BP, Heart Rate, Respiratory Rate, and Red Flag symptoms."),
    ("4. Decision Transparency", "Explainable clinical rationale showing triggered rules, point weights, and non-diagnostic safe harbor."),
    ("5. Clinician Override", "Mandatory audited manual review path for nurses/doctors to adjust priority levels."),
    ("6. Dual-Pipeline Events", "Synchronous critical priority elevation vs Asynchronous daemon notifications (SMS/Email simulation)."),
    ("7. Role-Based Access", "Granular roles (Doctor, Nurse, Admin, Kiosk) with 1-click evaluator switcher."),
    ("8. Urgent Preemption Demo", "Proves the core hackathon deliverable: emergency patient dynamically overtakes routine cases to #1.")
]

PORTALS = [
    ("Executive Dashboard", "http://localhost:5000/", "Live queue metrics, doctor load, and 1-Click Preemption Demo."),
    ("Nurse Triage Station", "http://localhost:5000/triage", "Intake vitals, red-flag symptoms, live AI score preview & override."),
    ("Live Hospital Queue", "http://localhost:5000/queue", "Department and priority-sorted queue with doctor allocation modal."),
    ("Doctor Workstation", "http://localhost:5000/doctor", "Active consultation room, call next patient, clinical notes & discharge."),
    ("Waiting Room TV Display", "http://localhost:5000/display", "Fullscreen dark display with live token announcements and audio chime."),
    ("Configurable Rules Engine", "http://localhost:5000/rules", "Admin panel to customize triage weights and toggle clinical rules."),
    ("Audit & Event Hub", "http://localhost:5000/audit", "Tamper-evident clinical audit logs and sync vs async event viewer.")
]

def print_banner():
    print("=" * 80)
    print(f" {PROJECT_INFO['hackathon']} — {PROJECT_INFO['problem_statement'].upper()}")
    print(f" {PROJECT_INFO['title']}")
    print(f" {PROJECT_INFO['institution']}")
    print("=" * 80)

def show_overview():
    print_banner()
    print("\n[+] CORE CAPABILITIES & COMPLIANCE:")
    for title, desc in FEATURES:
        print(f"  • {title:<25} : {desc}")

    print("\n[+] AVAILABLE WEB PORTALS & URLS:")
    for name, url, desc in PORTALS:
        print(f"  • {name:<25} : {url}")
        print(f"    └── {desc}")

    print("\n[+] QUICK COMMANDS:")
    print("  1. Run Server        : python app.py")
    print("  2. Run Tests         : python test_system.py")
    print("  3. Check Dependencies: python requirements.py")
    print("=" * 80)

def main():
    show_overview()
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == 'test':
            print("\nRunning automated test suite...")
            subprocess.call([sys.executable, "test_system.py"])
        elif arg == 'run':
            print("\nStarting ApexCare web server...")
            subprocess.call([sys.executable, "app.py"])

if __name__ == '__main__':
    main()
