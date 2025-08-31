# In my_app/main.py
import importlib.resources
import json


def load_config():
    # This is the modern, correct way to read package data
    json_str = importlib.resources.read_text("my_app", "config.json")
    return json.loads(json_str)

config = load_config()
print(f"Loaded config: {config['setting']}")