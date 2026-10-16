import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

USER_ID = os.getenv("BHOONIDHI_USER_ID")
PASSWORD = os.getenv("BHOONIDHI_PASSWORD")
TOKEN_URL = os.getenv("BHOONIDHI_TOKEN_URL", "https://bhoonidhi-api.nrsc.gov.in/auth/token")

def mask_token(token_str):
    if not token_str or len(token_str) < 20:
        return token_str
    # Keep first 15 and last 10 characters, mask the rest
    return f"{token_str[:15]}...[MASKED]...{token_str[-10:]}"

def test_refresh_token():
    # Step 1: Get initial tokens using password
    auth_payload = {
        "userId": USER_ID,
        "password": PASSWORD,
        "grant_type": "password"
    }
    headers = {"Content-Type": "application/json"}
    
    print("Token URL:", TOKEN_URL)
    print("Step 1: Authenticating to get initial tokens...")
    response = requests.post(TOKEN_URL, json=auth_payload, headers=headers, timeout=30)
    
    if response.status_code != 200:
        print("Failed to get initial tokens:", response.status_code)
        try:
            print("Response:", response.json())
        except ValueError:
            print("Response:", response.text)
        return
        
    initial_data = response.json()
    refresh_token = initial_data.get("refresh_token")
    
    if not refresh_token:
        print("No refresh token received in the initial auth response!")
        return
        
    print("Success! Got initial refresh_token.")
    print("-" * 50)
    
    # Step 2: Use the refresh token to get a new access token
    print("Step 2: Requesting new access token using the refresh_token...")
    refresh_payload = {
        "userId": USER_ID,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    refresh_response = requests.post(TOKEN_URL, json=refresh_payload, headers=headers, timeout=30)
    
    if refresh_response.status_code == 200:
        print("\nRefresh Token Flow Successful!")
        print("HTTP Status: 200\n")
        
        refresh_data = refresh_response.json()
        
        # Masking the actual tokens for security before printing the JSON structure
        safe_data = {
            "userId": refresh_data.get("userId"),
            "access_token": mask_token(refresh_data.get("access_token")),
            "token_type": refresh_data.get("token_type"),
            "expires_in": refresh_data.get("expires_in"),
            "refresh_token": mask_token(refresh_data.get("refresh_token"))
        }
        
        print("Output JSON Object for Refresh Token:")
        print(json.dumps(safe_data, indent=4))
    else:
        print("Refresh Token Flow Failed!")
        print("HTTP Status:", refresh_response.status_code)
        try:
            print(refresh_response.json())
        except ValueError:
            print(refresh_response.text)

if __name__ == "__main__":
    test_refresh_token()
