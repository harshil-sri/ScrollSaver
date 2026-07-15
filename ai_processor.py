import os
import time
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

def process_media(file_paths: list[str], category: str, content_type: str, custom_instructions: str = None, caption_text: str = "", extract_frames: bool = False) -> dict:
    import requests
    import json
    import time
    import cv2
    from PIL import Image
    
    gemini_contents = []
    audio_paths = []
    video_paths = []
    
    if file_paths:
        for fp in file_paths:
            ext = fp.lower()
            if ext.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                gemini_contents.append(Image.open(fp))
            elif ext.endswith(('.mp4', '.webm', '.mkv', '.mov')):
                audio_paths.append(fp)
                video_paths.append(fp)
            else:
                audio_paths.append(fp)
            
    # STEP 1: Understanding / Transcription
    transcript = ""
    ocr_text = ""
    
    if video_paths and extract_frames:
        try:
            for vp in video_paths:
                cap = cv2.VideoCapture(vp)
                fps = cap.get(cv2.CAP_PROP_FPS)
                if not fps or fps <= 0:
                    fps = 30
                frame_interval = int(fps * 3) # 1 frame every 3 seconds
                
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    for idx in range(0, total_frames, frame_interval):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                        ret, frame = cap.read()
                        if ret:
                            # Resize to max 800px width/height to save memory/API payload
                            h, w = frame.shape[:2]
                            scale = min(800/w, 800/h)
                            if scale < 1:
                                frame = cv2.resize(frame, (int(w*scale), int(h*scale)))
                            # Convert to PIL Image for Gemini
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            pil_img = Image.fromarray(rgb_frame)
                            gemini_contents.append(pil_img)
                cap.release()
        except Exception as e:
            print(f"Frame Extraction Error: {e}")

    transcription_prompt = "You are an AI that understands media. If this is audio/video, provide a verbatim word-for-word transcript. If these are images, extract all text and describe any tools or recipes shown in them."

    if audio_paths:
        # Groq Whisper API for Audio
        groq_api_key = os.environ.get("GROQ_API_KEY")
        if not groq_api_key:
            raise Exception("GROQ_API_KEY is missing from .env")
            
        for ap in audio_paths:
            headers = {"Authorization": f"Bearer {groq_api_key}"}
            with open(ap, "rb") as audio_file:
                files = {"file": (os.path.basename(ap), audio_file)}
                data = {
                    "model": "whisper-large-v3-turbo", 
                    "response_format": "text",
                    "prompt": "The audio may be in English, Hindi, or a mix. If English, transcribe normally in English. If Hindi, transcribe in Hinglish (Roman/English alphabet, jaise main abhi likh raha hoon)."
                }
                res_groq = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
                res_groq.raise_for_status()
                transcript += res_groq.text + "\n"

    if gemini_contents:
        # Gemini Vision for Images
        for attempt in range(3):
            try:
                res_understand = client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=gemini_contents + [transcription_prompt]
                )
                transcript += res_understand.text.strip() + "\n"
                break
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    time.sleep(30)
                else:
                    raise e
        
    # STEP 2: Web Grounding (Tavily Search)
    search_results = ""
    if custom_instructions and custom_instructions.lower() != "skip":
        try:
            tavily_api_key = os.environ.get("TAVILY_API_KEY")
            if tavily_api_key:
                tavily_data = {
                    "api_key": tavily_api_key,
                    "query": f"{custom_instructions} software tool github",
                    "search_depth": "basic",
                    "include_answer": False,
                    "max_results": 3
                }
                res_tavily = requests.post("https://api.tavily.com/search", json=tavily_data, timeout=15)
                res_tavily.raise_for_status()
                results = res_tavily.json().get("results", [])
                
                search_results = "TAVILY WEB SEARCH RESULTS:\n"
                for r in results:
                    search_results += f"- Title: {r.get('title')}\n  URL: {r.get('url')}\n  Content: {r.get('content')}\n\n"
        except Exception as e:
            print(f"Tavily Search Error: {e}")

    # STEP 3: Reasoning and Extraction
    base_prompts = {
        "Tech": {
            "Tool": "You are a tech assistant. Extract the PRIMARY tool/skill/repo discussed in the transcript. You MUST return a SINGLE JSON OBJECT with exact keys: 'Name', 'URL', 'Description'. Do not extract secondary comparisons.",
            "Guide": "You are a tech assistant. Summarize the step-by-step guide discussed. You MUST return a SINGLE JSON OBJECT with exact keys: 'Name', 'URL', 'Description'. Put the entire step-by-step summary inside the 'Description' field."
        },
        "Recipe": {
            "Tool": "You are a culinary assistant. Extract the PRIMARY recipe discussed. You MUST return a SINGLE JSON OBJECT with exact keys: 'Name', 'Ingredients', 'Instructions'.",
            "Guide": "You are a culinary assistant. Extract the PRIMARY recipe discussed. You MUST return a SINGLE JSON OBJECT with exact keys: 'Name', 'Ingredients', 'Instructions'."
        },
        "General": {
            "Tool": "Extract key details into a SINGLE JSON OBJECT.",
            "Guide": "Extract key details into a SINGLE JSON OBJECT."
        }
    }
    
    cat_prompts = base_prompts.get(category, base_prompts["General"])
    extraction_prompt = cat_prompts.get(content_type, cat_prompts["Tool"])
    system_prompt = f"{extraction_prompt}\nCRITICAL: Return ONLY a SINGLE JSON object representing the PRIMARY subject. Do not return a list. Do not return multiple objects."
    
    user_prompt = "Below are the extracted text sources from the media. The tool or recipe name might be in any one of these (e.g. spoken, written in the caption, or burned into the video as on-screen text). Please combine context from ALL sources to answer accurately.\n\n"
    if caption_text:
        user_prompt += f"--- CAPTION / DESCRIPTION ---\n{caption_text}\n\n"
    if transcript:
        user_prompt += f"--- AUDIO TRANSCRIPTION AND GEMINI VISION ---\n{transcript}\n\n"
        
    if custom_instructions and custom_instructions.lower() != "skip":
        user_prompt += f"USER CUSTOM INSTRUCTIONS: {custom_instructions}\n"
        user_prompt += f"CRITICAL INSTRUCTION: If there is a contradiction between the transcript/OCR and the User Custom Instructions, YOU MUST ABSOLUTELY TRUST THE USER CUSTOM INSTRUCTIONS. The user is always right.\n\n"
        
    if search_results:
        user_prompt += f"{search_results}\n"
        user_prompt += "Use the search results to correct yourself and find the exact official Name, URL, and Description.\n"

    final_prompt = system_prompt + "\n\n" + user_prompt
    
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
    if not openrouter_api_key:
        raise Exception("OPENROUTER_API_KEY is missing from .env")
        
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json"
    }
    
    # Ensure JSON extraction works by explicitly telling it in the prompt
    final_prompt = system_prompt + "\n\nCRITICAL: YOU MUST OUTPUT ONLY VALID RAW JSON. Do NOT wrap it in markdown block quotes (```json ... ```). OUTPUT RAW JSON ONLY.\n\n" + user_prompt
    
    payload = {
        "model": "openrouter/free",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_prompt}
        ]
    }
    
    res_or = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
    res_or.raise_for_status()
    
    text = res_or.json()["choices"][0]["message"]["content"].strip()
    
    # Clean markdown if the model hallucinated it anyway
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0] # Grab the first object just in case it ignored instructions
        return data
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON. Raw output: {text[:100]}") from e
