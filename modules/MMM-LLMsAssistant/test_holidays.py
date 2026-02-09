
import sys
import os
import json
import datetime
import pytz

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_tools import AgentTools

def test_holidays():
    print("Testing AgentTools Holidays...")
    
    # Initialize tools with mock config if needed
    tools = AgentTools({
        "timezone": "Asia/Ho_Chi_Minh"
    })
    
    # 1. Test get_holidays for current year (2026)
    print("\n--- get_holidays() ---")
    result = tools.get_holidays()
    if result["success"]:
        holidays = result["data"]["holidays"]
        print(f"Total holidays found: {len(holidays)}")
        tet_found = False
        for h in holidays:
            if "tet" in h["name"].lower():
                print(f"Found Tet: {h['name']} on {h['date']}")
                tet_found = True
        
        if not tet_found:
            print("WARNING: Tet not found in holiday list!")
    else:
        print(f"Error: {result.get('error')}")

    # 2. Test get_upcoming_holidays (30 days from now 2026-02-07)
    print("\n--- get_upcoming_holidays(30) ---")
    result = tools.get_upcoming_holidays(30)
    if result["success"]:
        holidays = result["data"]["holidays"]
        print(f"Upcoming holidays: {len(holidays)}")
        for h in holidays:
            print(f"- {h['name']} ({h['date']}) in {h['days_until']} days")
    else:
        print(f"Error: {result.get('error')}")

if __name__ == "__main__":
    test_holidays()
