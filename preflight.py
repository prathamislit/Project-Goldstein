"""
preflight.py — Pre-run diagnostics for the Goldstein pipeline.

Checks everything that can fail BEFORE any BigQuery or yfinance calls,
so failures are caught in 2 seconds instead of mid-pipeline.

Called by Run_All_regions.sh before the region loop.
Can also be run standalone: python3 preflight.py

Exit code 0 = all checks passed, safe to run pipeline.
Exit code 1 = critical failure, do not proceed.
"""

import sys
import os
import importlib

REQUIRED_PACKAGES = [
    ("google.cloud.bigquery", "google-cloud-bigquery"),
    ("google.oauth2.service_account", "google-auth"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("yfinance", "yfinance"),
    ("scipy", "scipy"),
    ("statsmodels", "statsmodels"),
    ("arch", "arch"),
    ("plotly", "plotly"),
    ("dash", "dash"),
    ("dash_bootstrap_components", "dash-bootstrap-components"),
    ("dotenv", "python-dotenv"),
]

REQUIRED_FILES = [
    ".env",
    "config.py",
    "gdelt_fetcher.py",
    "market_data.py",
    "preprocessor.py",
    "scorer.py",
    "garch_model.py",
    "data_quality.py",
    "backtest.py",
    "generate_insights.py",
    "merge_reports.py",
    "Dashboard.py",
]


def check_python_version():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print(f"  \u2717 Python {v.major}.{v.minor}.{v.micro} \u2014 need \u22653.10")
        return False
    print(f"  \u2713 Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_venv():
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    if not in_venv:
        print("  \u2717 Not running inside a virtual environment")
        print("    Fix: source venv/bin/activate")
        return False
    print(f"  \u2713 Virtual environment active ({sys.prefix})")
    return True


def check_packages():
    ok = True
    for module_name, pip_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            print(f"  \u2717 Missing: {pip_name}  (pip install {pip_name})")
            ok = False
    if ok:
        print(f"  \u2713 All {len(REQUIRED_PACKAGES)} required packages installed")
    return ok


def check_env_vars():
    from dotenv import load_dotenv
    load_dotenv()

    ok = True
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        print("  \u2717 GCP_PROJECT_ID not set in .env")
        ok = False
    else:
        print(f"  \u2713 GCP_PROJECT_ID = {project_id}")

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if creds_path and os.path.exists(creds_path):
        print(f"  \u2713 GCP credentials file exists: {creds_path}")
    elif creds_path:
        print(f"  \u2717 GCP credentials file NOT FOUND: {creds_path}")
        ok = False
    else:
        print("  \u26a0 No GOOGLE_APPLICATION_CREDENTIALS \u2014 will try ADC")

    return ok


def check_files():
    ok = True
    for f in REQUIRED_FILES:
        if not os.path.exists(f):
            print(f"  \u2717 Missing: {f}")
            ok = False
    if ok:
        print(f"  \u2713 All {len(REQUIRED_FILES)} pipeline files present")
    return ok


def check_directories():
    for d in ["data", "outputs", "logs"]:
        os.makedirs(d, exist_ok=True)
    print("  \u2713 data/, outputs/, logs/ directories exist")
    return True


def check_port(port=8050):
    """Check if port 8050 is available (non-blocking)."""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        print(f"  \u2713 Port {port} available for dashboard")
        return True
    except OSError:
        print(f"  \u26a0 Port {port} in use \u2014 dashboard may fail to start")
        print(f"    Fix: lsof -ti :{port} | xargs kill -9")
        return True  # warning, not fatal


def main():
    print("\u2550" * 51)
    print("  Project Goldstein \u2014 Preflight Check")
    print("\u2550" * 51)
    print()

    checks = [
        ("Python version",  check_python_version),
        ("Virtual env",     check_venv),
        ("Packages",        check_packages),
        ("Environment",     check_env_vars),
        ("Pipeline files",  check_files),
        ("Directories",     check_directories),
        ("Dashboard port",  check_port),
    ]

    all_ok = True
    for name, fn in checks:
        print(f"[{name}]")
        try:
            result = fn()
            if not result:
                all_ok = False
        except Exception as e:
            print(f"  \u2717 Check failed with error: {e}")
            all_ok = False
        print()

    if all_ok:
        print("\u2713 All preflight checks passed. Safe to run pipeline.")
        sys.exit(0)
    else:
        print("\u2717 Preflight failed. Fix the issues above before running.")
        sys.exit(1)


if __name__ == "__main__":
    main()
