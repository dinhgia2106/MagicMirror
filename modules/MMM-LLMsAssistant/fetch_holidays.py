
import requests
import json
import sys

def fetch():
    url = "http://192.168.1.11:8000/api/holidays"
    output_file = "api_response.json"
    
    try:
        with open("status.txt", "w") as f:
            f.write("Starting...\n")
            
        response = requests.get(url, timeout=10)
        
        with open("status.txt", "a") as f:
            f.write(f"Status Code: {response.status_code}\n")
            
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(response.text)
            
    except Exception as e:
        with open("error.txt", "w") as f:
            f.write(str(e))

if __name__ == "__main__":
    fetch()
