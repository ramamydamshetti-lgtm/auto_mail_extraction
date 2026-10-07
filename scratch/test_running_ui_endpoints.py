import urllib.request
import json
import sys

base_url = "http://127.0.0.1:5000"

print("1. Testing Health Endpoint...")
try:
    with urllib.request.urlopen(f"{base_url}/health", timeout=5) as r:
        print(f"  Status: {r.status}")
        print(f"  Data: {r.read().decode()[:200]}")
except Exception as e:
    print(f"  Health error: {e}")

print("\n2. Testing Frontend List Page (GET /)...")
try:
    with urllib.request.urlopen(f"{base_url}/", timeout=5) as r:
        content = r.read().decode()
        print(f"  Status: {r.status}")
        print(f"  HTML Length: {len(content)} bytes")
        print(f"  Title tag in HTML: {'<title>' in content}")
except Exception as e:
    print(f"  Frontend error: {e}")

print("\n3. Testing Backend API Requirements List (GET /api/requirements)...")
try:
    with urllib.request.urlopen(f"{base_url}/api/requirements?page_size=5", timeout=5) as r:
        data = json.loads(r.read().decode())
        print(f"  Status: {r.status}")
        print(f"  Total Count: {data.get('total_count')}")
        print(f"  Page Size: {data.get('page_size')}")
        print(f"  Sample req_id: {[item.get('req_id') for item in data.get('data', [])]}")
except Exception as e:
    print(f"  API error: {e}")
