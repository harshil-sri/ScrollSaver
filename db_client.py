import os
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def check_if_exists(category: str, name: str) -> bool:
    db_map = {
        "Tech": os.getenv("NOTION_TECH_DB_ID"),
        "Recipe": os.getenv("NOTION_RECIPE_DB_ID"),
        "General": os.getenv("NOTION_GENERAL_DB_ID")
    }
    db_id = db_map.get(category)
    if not db_id:
        return False
        
    payload = {
        "filter": {
            "property": "Title",
            "title": {
                "equals": name
            }
        }
    }
    try:
        response = requests.post(f"https://api.notion.com/v1/databases/{db_id}/query", headers=HEADERS, json=payload)
        response.raise_for_status()
        results = response.json().get("results", [])
        return len(results) > 0
    except Exception as e:
        print(f"Error checking duplicates: {e}")
        return False

def add_to_notion(category: str, data: dict, video_url: str):
    db_map = {
        "Tech": os.getenv("NOTION_TECH_DB_ID"),
        "Recipe": os.getenv("NOTION_RECIPE_DB_ID"),
        "General": os.getenv("NOTION_GENERAL_DB_ID")
    }
    db_id = db_map.get(category)
    if not db_id:
        raise ValueError(f"Database ID for category {category} not found. Check your .env file.")

    properties = {
        "Title": {
            "title": [{"text": {"content": data.get("Name", "Unknown Item")}}]
        }
    }
    
    # URL property
    resolved_url = data.get("URL", "")
    
    is_valid = isinstance(resolved_url, str) and len(resolved_url.strip()) > 3
    if is_valid:
        url_lower = resolved_url.lower().strip()
        # If it has spaces or common hallucinated placeholder words, it's not a real URL
        if " " in url_lower or "not" in url_lower or "n/a" in url_lower or "unknown" in url_lower:
            is_valid = False
            
    if not is_valid:
        resolved_url = video_url
    elif not resolved_url.strip().startswith("http"):
        resolved_url = f"https://{resolved_url.strip()}"
        
    if resolved_url and str(resolved_url).strip():
        properties["URL"] = {
            "url": str(resolved_url).strip()
        }

    def _format_text(val) -> str:
        if isinstance(val, list):
            return "\n".join(f"- {item}" for item in val)
        elif isinstance(val, dict):
            import json
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    # Custom properties based on category
    if category == "Tech":
        if "Description" in data:
            properties["Description"] = {
                "rich_text": [{"text": {"content": _format_text(data["Description"])[:2000]}}]
            }
    elif category == "Recipe":
        if "Ingredients" in data:
            properties["Ingredients"] = {
                "rich_text": [{"text": {"content": _format_text(data["Ingredients"])[:2000]}}]
            }
        if "Instructions" in data:
            properties["Instructions"] = {
                "rich_text": [{"text": {"content": _format_text(data["Instructions"])[:2000]}}]
            }

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties
    }

    response = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=payload)
    if response.status_code != 200:
        raise Exception(f"Notion API Error: {response.text}")
    return response.json()
