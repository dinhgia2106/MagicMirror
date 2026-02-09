
import requests
import json
import datetime

def check_holidays():
    url = "http://192.168.1.11:8000/api/holidays"
    try:
        print(f"Fetching from {url}...")
        response = requests.get(url, timeout=5)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            holidays = data.get("data", [])
            print(f"Total holidays returned: {len(holidays)}")
            
            # Check for Tet/Lunar New Year
            found_tet = False
            for h in holidays:
                name = h.get("name", "").lower()
                date = h.get("date", "")
                print(f" - {date}: {h.get('name')}")
                
                if "tet" in name or "lunar" in name or "nguyen dan" in name:
                    found_tet = True
                    print(f"   => FOUND TET HERE!")
            
            if not found_tet:
                print("\nWARNING: No Tet/Lunar New Year found in API response for default query.")
                
            # Check current year coverage
            years = set()
            for h in holidays:
                try:
                    y = int(h.get("date", "")[:4])
                    years.add(y)
                except:
                    pass
            print(f"\nYears covers: {sorted(list(years))}")
            
        else:
            print(f"Error response: {response.text}")
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    check_holidays()
