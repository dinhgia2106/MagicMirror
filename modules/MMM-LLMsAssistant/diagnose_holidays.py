
import requests
import json
import sys
import os
import datetime

# Add parent directory to path to import agent_tools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_tools import AgentTools

def log(msg):
    print(msg)
    with open("diagnosis.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def diagnose():
    with open("diagnosis.txt", "w", encoding="utf-8") as f:
        f.write("Starting Diagnosis at " + str(datetime.datetime.now()) + "\n")

    # 1. Test Direct API usage for 2026
    url = "http://192.168.1.11:8000/api/holidays"
    params = {"year": 2026}
    try:
        log(f"1. Calling API: {url} with params {params}")
        response = requests.get(url, params=params, timeout=5)
        log(f"   Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            holidays = data.get("data", [])
            log(f"   Holidays count: {len(holidays)}")
            
            tet_found_api = False
            for h in holidays:
                name = h.get("name", "").lower()
                date = h.get("date", "")
                if "tet" in name or "nguyen dan" in name:
                    log(f"   FOUND TET IN API: {date} - {h['name']}")
                    tet_found_api = True
            
            if not tet_found_api:
                log("   WARNING: Tet NOT found in API response for 2026")
        else:
            log(f"   Error Response: {response.text}")
            
    except Exception as e:
        log(f"   API Exception: {e}")

    # 2. Test AgentTools.get_upcoming_holidays
    try:
        log("\n2. Testing AgentTools.get_upcoming_holidays()")
        tools = AgentTools()
        result = tools.get_upcoming_holidays(days=365)
        
        if result["success"]:
            upcoming = result["data"]["holidays"]
            log(f"   AgentTools returned {len(upcoming)} holidays")
            
            tet_found_tool = False
            for h in upcoming:
                name = h.get("name", "").lower()
                date = h.get("date", "")
                days = h.get("days_until")
                log(f"   - {date} (+{days}d): {h.get('name')}")
                if "tet" in name or "nguyen dan" in name:
                    tet_found_tool = True
            
            if not tet_found_tool:
                log("   WARNING: Tet NOT found in AgentTools result")
        else:
            log(f"   AgentTools Failed: {result.get('error')}")
            
    except Exception as e:
        log(f"   AgentTools Exception: {e}")

if __name__ == "__main__":
    diagnose()
