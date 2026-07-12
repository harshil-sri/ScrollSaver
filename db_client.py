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
    if "URL" in data or video_url:
        properties["URL"] = {
            "url": data.get("URL") or video_url
        }

    # Custom properties based on category
    if category == "Tech":
        if "Description" in data:
            properties["Description"] = {
                "rich_text": [{"text": {"content": data["Description"][:2000]}}]
            }
    elif category == "Recipe":
        if "Ingredients" in data:
            properties["Ingredients"] = {
                "rich_text": [{"text": {"content": data["Ingredients"][:2000]}}]
            }
        if "Instructions" in data:
            properties["Instructions"] = {
                "rich_text": [{"text": {"content": data["Instructions"][:2000]}}]
            }

    payload = {
        "parent": {"database_id": db_id},
        "properties": properties
    }

    response = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=payload)
    if response.status_code != 200:
        raise Exception(f"Notion API Error: {response.text}")
    return response.json()
