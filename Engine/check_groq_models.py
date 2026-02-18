from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

print("Modelos disponibles en Groq:\n")
models = client.models.list()

for model in models.data:
    print(f"  → {model.id}")
    if hasattr(model, 'context_window'):
        print(f"     Context: {model.context_window} tokens")
    print()
