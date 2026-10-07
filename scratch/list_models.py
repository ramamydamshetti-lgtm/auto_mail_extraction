import os
from dotenv import load_dotenv
import requests

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
resp = requests.get(url)
if resp.status_code == 200:
    models = [m["name"] for m in resp.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    print("Available models:", models)
else:
    print("Error:", resp.status_code, resp.text)
