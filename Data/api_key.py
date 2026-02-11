from dotenv import load_dotenv
import os

load_dotenv()  
key = os.getenv("OPENAI_API_KEY")

if key:
    print(f"API Key successfully loaded: {key}") 
else:
    print("API_KEY not found or loaded.")