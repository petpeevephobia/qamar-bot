"""Print the web OAuth URL (run main.py first so :8080 is listening)."""

import os

from dotenv import load_dotenv

from drive_client import build_reauth_url

load_dotenv()

if __name__ == "__main__":
    url = build_reauth_url()
    print("Make sure Qamar is running (python main.py), then open this URL in your browser:")
    print(url)
