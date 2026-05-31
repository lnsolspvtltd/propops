"""Seed PropOps with realistic demo data for investor presentations.

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py --api-url http://localhost:8000
"""
import argparse
import sys
import requests

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()

    print("PropOps Demo Seeder")
    print(f"Target: {args.api_url}")
    print()

    # Login
    try:
        r = requests.post(f"{args.api_url}/api/v1/auth/login",
                          json={"email": "demo@propops.app", "password": "propops2026"}, timeout=10)
        if not r.ok:
            print(f"Login failed: {r.status_code} — is the backend running at {args.api_url}?")
            sys.exit(1)
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("✓ Authenticated")
    except requests.exceptions.ConnectionError:
        print(f"Connection failed — is the backend running at {args.api_url}?")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Request timed out")
        sys.exit(1)
    except Exception as e:
        print(f"Authentication error: {e}")
        sys.exit(1)

    # Seed
    try:
        r = requests.post(f"{args.api_url}/api/v1/demo/seed", headers=headers, timeout=30)
        if not r.ok:
            print(f"Seed failed: {r.status_code} {r.text[:200]}")
            sys.exit(1)
        d = r.json()
        print(f"✓ {d['message']}")
        print(f"  Incidents created: {d['incidents_created']}")
        print(f"  Drafts created:    {d['drafts_created']}")
        print()
        print("Open http://localhost:3000 and log in with demo@propops.app / propops2026")
    except requests.exceptions.Timeout:
        print("Seed request timed out")
        sys.exit(1)
    except Exception as e:
        print(f"Seed error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()