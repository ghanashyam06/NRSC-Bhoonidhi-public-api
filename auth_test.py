import os
import requests
from dotenv import load_dotenv

load_dotenv()

USER_ID = os.getenv("BHOONIDHI_USER_ID")
PASSWORD = os.getenv("BHOONIDHI_PASSWORD")
TOKEN_URL = os.getenv("BHOONIDHI_TOKEN_URL", "https://bhoonidhi-api.nrsc.gov.in/auth/token")

payload = {
    "userId": USER_ID,
    "password": PASSWORD,
    "grant_type": "password"
}

headers = {
    "Content-Type": "application/json"
}

print("Token URL:", TOKEN_URL)
print(f"Authenticating as: '{USER_ID}' ...")

try:
    response = requests.post(
        TOKEN_URL,
        json=payload,
        headers=headers,
        timeout=30
    )

    print("\nHTTP Status:", response.status_code)
    print("Response:")

    data = response.json()

    # Never print the actual tokens
    if "access_token" in data:
        print("Authentication successful!")
        print("Token type:", data.get("token_type"))
        print("Expires in:", data.get("expires_in"))
        print("Refresh token received:", bool(data.get("refresh_token")))
    else:
        print(data)

except requests.exceptions.RequestException as e:
    print("Request failed:", e)
except ValueError:
    print(response.text)
