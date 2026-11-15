"""
Dependency & Environment Checker for GEC Hackathon 2026:
Healthcare - Patient Triage & Queue Management System
"""

import sys
import subprocess

REQUIRED_PACKAGES = [
    "flask",
    "requests"
]

def check_and_install():
    print("=" * 60)
    print("ApexCare Hospital Triage System: Dependency Verification")
    print("=" * 60)
    print(f"Python Version: {sys.version.split()[0]}")

    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
            print(f"[OK] {pkg} is installed.")
        except ImportError:
            print(f"[MISSING] {pkg} is not installed.")
            missing.append(pkg)

    if missing:
        print(f"\nInstalling missing dependencies: {', '.join(missing)}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("[SUCCESS] All required dependencies have been installed!")
        except Exception as e:
            print(f"[ERROR] Failed to install packages automatically: {e}")
            print(f"Please run manually: pip install -r requirements.txt")
            sys.exit(1)
    else:
        print("\nAll required packages are satisfied! You are ready to run:")
        print("  python app.py")

if __name__ == '__main__':
    check_and_install()
