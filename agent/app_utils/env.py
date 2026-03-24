import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
MEMORY_BANK_ID = os.getenv("MEMORY_BANK_ID", "")
AI_ASSETS_BUCKET = os.getenv("AI_ASSETS_BUCKET", "")
