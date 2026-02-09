
import requests
import json

try:
    response = requests.get("http://192.168.1.11:8000/api/holidays", timeout=2)
    print(f"Status: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
