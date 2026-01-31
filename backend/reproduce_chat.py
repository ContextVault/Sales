import requests
import json

try:
    response = requests.post(
        "http://localhost:8000/chat",
        json={"question": "Who approved the highest discount?"},
        timeout=10
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
