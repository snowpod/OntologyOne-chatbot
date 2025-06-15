import httpx
import json
import os
import re
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from utils.ai_client import AIClient
from utils.chat_session_db import Database
from utils.chatbot_config import ChatbotConfig
from utils.chatbot_prompt_builder import ChatbotPromptBuilder
from utils.config import Config
from utils.embedding_service import EmbeddingService
from utils.gibberish_detector import GibberishDetector
from utils.github_store_client import fetch_cached_doc_path, fetch_cached_story_file_path, fetch_image_url, extract_pages_from_doc
from utils.logging import get_logger

# ---------- Pydantic Models ----------
class ChatMessage(BaseModel):
    user_message: str = ""
    bot_response: str = ""

class ChatRequest(BaseModel):
    user_message: str

class ChatSession(BaseModel):
    session_id: str
    history: list[ChatMessage] = []

# ---------- FastAPI Setup ----------
app = FastAPI()

env = os.getenv("ENV", "dev")  # default to "dev" if ENV is not set
if env == "dev":
    origins = ["http://localhost:3000"]  # your React dev server
else:
    origins = ["https://ontologyone-frontend.onrender.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if Path("build").exists():
    app.mount("/static", StaticFiles(directory="build", html=True), name="static")

# ---------- Initializations ----------
MAX_HISTORY_PAIRS = 2

config = Config()
debug = config.get("hr-demo", "debug").lower() == "true"
app_name = config.get('hr-demo', 'name')
bot_name = config.get('chatbot', 'name')
image_search_config_path = config.get("embedding", "image_search_config_path")

min_relevant_score = float(config.get("hr-demo", "min_relevant_score"))
ai_model = config.get('ai', 'model')
doc_store_project = config.get("documentstore", "project")
doc_store_default_folder = config.get("documentstore", "default_folder")
doc_store_stories_folder = config.get("documentstore", "stories_folder")
max_history_pairs = int(config.get("chatbot", "max_history_pairs"))

app_logger = get_logger(config.get("log", "app"))
feedback_logger = get_logger(config.get("log", "chatbot_feedback"))

database = Database()
database.create_tables()

embedding_service = EmbeddingService()
gibberish_detector = GibberishDetector()

prompt_builder = ChatbotPromptBuilder()
chat_mode = prompt_builder.get_mode()

chatbot_config = ChatbotConfig()
ai_client = AIClient()

# ---------- Functions ----------

def load_metadata(json_file_path):
    full_path = os.path.abspath(json_file_path)
    if debug:
        print("Resolved full path to image metadata:", full_path)

    if not os.path.isfile(json_file_path):
        raise FileNotFoundError(f"Image config file not found: {json_file_path}")

    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON from {json_file_path}: {e}")

def _process_matches(text_matches, top_n_text_hits, extract_pages_from_doc)-> list[str]:
    text_contents = []

    for match in text_matches[:top_n_text_hits]:
        file_name = match['metadata'].get("file_name")
        pages = match['metadata'].get("pages")

        if not file_name:
            app_logger.error(f"Skipping file_name: {file_name}: missing file_name")
            continue

        cached_doc_path = fetch_cached_doc_path(doc_store_project, file_name)

        if pages:
            # Deduplicate pages while preserving original order
            seen_pages = set()
            page_list = []
            for page_num in pages:
                page_num = int(page_num)
                if page_num not in seen_pages:
                    seen_pages.add(page_num)
                    page_list.append(page_num - 1)  # convert to 0-based indexing

            if debug:
                print(f"file_name: {file_name}, unique pages: {page_list}")
            text_chunk = extract_pages_from_doc(cached_doc_path, page_list)
        else:
            if debug:
                print(f"file_name: {file_name}, no pages specified, extracting entire file")

            file_name = Path(file_name).stem.capitalize().replace('_', ' ')
            text_chunk = extract_pages_from_doc(cached_doc_path, None)
            text_chunk = f"## {file_name}\n{text_chunk}"

        text_contents.append(text_chunk)

    return text_contents

def _generate_AI_response(chatbot_profile:str, user_prompt:str) -> str:
    try:
        """ Gemini does not natively distinguish between system and user roles the way 
            OpenAI or Claude does, so we are essentially sending a single unified prompt. """
        prompt = f"{chatbot_profile}\n\n{user_prompt}"
        bot_response = ai_client.generate_content(prompt)
        return bot_response
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

def _get_chat_history_context(session_id:str) -> str:
    # Prep chat history to be included in user prompt for chat coherence
    all_history = database.fetch_session(session_id)["history"]

    # Only include non-feedback messages
    filtered_history = [
        ChatMessage(**msg)
        for msg in all_history
        if not msg.get("is_feedback")  # assumes feedback flag exists
    ]

    recent_history = filtered_history[-max_history_pairs:]
    if not recent_history:
        return ""

    chat_history_context = "\n".join(
        f"User: {msg.user_message}\nBot: {msg.bot_response}"
        for msg in recent_history
    )

    return chat_history_context

def get_shortened_image_description(description:str) -> str:
    """ Drop text after ' in' to shorten image description for display in bot's response """
    return description.split(" in ")[0] if " in " in description else description

def _update_session_and_store_chat_history(session_id:str, user_message:str, bot_response:str, is_feedback:bool=False):
    # 5. Retrieve session & append new message
    session_data = database.fetch_session(session_id)
    session = ChatSession(**session_data)
    session.history.append(ChatMessage(user_message=user_message, bot_response=bot_response))

    # 6. Store chat history
    database.store_message(session_id, "user", user_message, is_feedback)
    database.store_message(session_id, "bot", bot_response, is_feedback)

def _get_story_context(story_matches:list[dict]) -> str:
    story_context = None
    if not story_matches:
        return story_context
    
    story_context = ""
    for match in story_matches:
        file_name = match['metadata'].get("file_name")
        cached_file_path = fetch_cached_story_file_path(doc_store_project, file_name)

        story_name = Path(file_name).stem.capitalize().replace('_', ' ')
        text_chunk = extract_pages_from_doc(cached_file_path)
        
        # no longer required since the app_name and bot_name are hardcoded
        # to enable the search for text embedding to work better in pinecone.
        # I dont want to maintain 2 separate versions just for naming flexibility.
        #text_chunk = text_chunk.format(app_name=app_name, bot_name=bot_name)  # replace {app_name} with the actual app name

        if story_context:
            story_context += "\n\n"
        story_context += f"## {story_name}\n{text_chunk}"

    return story_context

def _get_doc_context(session_id: str, user_message:str, tags:list[str]):
    doc_context = None

    # 1. Search Pinecone for text matches
    namespace = embedding_service.get_doc_namespace()
    doc_matches = embedding_service.search_text_embeddings(namespace, user_message, tags)

    if not doc_matches:
        return doc_context
        
    # 3. Fetch relevant content from GitHub OntologyOne folder
    top_n_doc_hits = 2      # use only the top 2 quality hits in order not to bloat the prompt
    doc_contents = _process_matches(doc_matches, top_n_doc_hits, extract_pages_from_doc)
    doc_contents = "\n\n".join(doc_contents)
    
    return doc_contents

def _get_image_context(session_id: str, user_message:str):
    image_context = None

    # 1. Pseudo-search for image matches, currently compare user message vs image metadata file
    image_matches = embedding_service.search_image_embeddings(user_message)
    if not image_matches:
        return image_context
    
    # 2. Fetch the image urls for the image hits
    image_context = ""
    for file_name, score, description in image_matches:
        image_url = fetch_image_url(file_name)
        description = get_shortened_image_description(description)
        image_str = "\n" if image_context else ""
        image_str += f"- image_url: {image_url}, description: {description}"

        image_context += image_str
            
    return image_context

def enrich_query(session_id: str, user_message: str) -> tuple[str, list[str]]:
    ONTOLOGY_KEYWORDS = {"china", "germany", "ontologyone", "singapore", "usa", "unified"}
    FOCUS_KEYWORDS = {"class", "cpf", "department", "employee", "entities", "entity", "individual", "instance", "object", "role", "position"}

    def extract_keywords(text: str, keyword_set: set) -> set:
        return {word for word in re.findall(r"\w+", text.lower()) if word in keyword_set}

    # Step 1: Extract from current message
    current_ontology = extract_keywords(user_message, ONTOLOGY_KEYWORDS)
    current_focus = extract_keywords(user_message, FOCUS_KEYWORDS)

    # Step 2: Get most recent *non-feedback* user message from chat history
    all_history = database.fetch_session(session_id)["history"]
    last_user_message = None
    for msg in reversed(all_history):
        if msg.get("is_feedback"):
            continue
        if msg.get("user_message"):
            last_user_message = msg["user_message"]
            break

    # Step 3: Extract from previous message
    previous_ontology = extract_keywords(last_user_message, ONTOLOGY_KEYWORDS) if last_user_message else set()
    previous_focus = extract_keywords(last_user_message, FOCUS_KEYWORDS) if last_user_message else set()

    # Step 4: Determine what to use for tags
    tags = []

    if current_ontology or current_focus:
        tags.extend(sorted(current_ontology))
        tags.extend(sorted(current_focus))
    else:
        tags.extend(sorted(previous_ontology))
        tags.extend(sorted(previous_focus))

    # Step 5: Enrich the query with any missing (but found previously) keywords
    missing_ontology = previous_ontology - current_ontology
    missing_focus = previous_focus - current_focus

    enriched_parts = [user_message]
    if missing_ontology:
        enriched_parts.append(" ".join(missing_ontology))
    if missing_focus:
        enriched_parts.append(" ".join(missing_focus))

    enriched_query = " ".join(enriched_parts)
    return enriched_query, tags

# ---------- Routes ----------
@app.get("/")
def read_root():
    return {"message": "chatbot is working"}

@app.post("/chat/start")
async def start_chat():
    session_id = str(uuid.uuid4())
    database.create_session(session_id)

    return {"session_id": session_id}

@app.post("/chat/{session_id}")
async def chat_with_bot(session_id: str, request: ChatRequest):
    # await asyncio.sleep(15)   # for debugging bot thinking and typing animation
    
    try:
        user_message = request.user_message

        # check if user message is giiberish, if so, return early
        if gibberish_detector.is_gibberish(user_message):
            bot_response = chatbot_config.get("chatbot_interactions","gibberish_found_response")
           
            _update_session_and_store_chat_history(session_id, user_message, bot_response)
            return {
                "session_id": session_id,
                "user_message": user_message,
                "bot_response": bot_response,
                "history": database.fetch_session(session_id)["history"],
            }

        # now that we have established the user message is not gibberish, 
        # categorize its mode and build the chatbot profile for inclusion in the prompt.
        enriched_user_message, tags = enrich_query(session_id, user_message)
        if debug:
            print(f"chatbot enriched_user_message: {enriched_user_message}, tags: {tags}")
        
        chat_mode = prompt_builder.infer_mode_from_input(enriched_user_message)
        chatbot_profile = prompt_builder.get_profile(chat_mode)

        # get stories context regardless of mode
        story_context = None
        namespace = embedding_service.get_stories_namespace()
        story_matches = embedding_service.search_text_embeddings(namespace, user_message)
            
        # get chat history context regardless of mode
        chat_history_context = _get_chat_history_context(session_id)

        # get doc and image context for app mode only; technical/persona mode => None
        doc_context, image_context = None, None
        if prompt_builder.is_request_for_app_info(chat_mode):
            doc_context = _get_doc_context(session_id, user_message, tags)

            # if app mode, we will use all the matched stories
            if story_matches:
                story_context = _get_story_context(story_matches)

            image_context = _get_image_context(session_id, user_message)

        elif prompt_builder.is_request_for_tech_info(chat_mode):
            # if technical mode, we will use only the first matched stories since
            # it is unlikely that the stories will be required but just in case
            if story_matches:
                story_context = _get_story_context([story_matches[0]])
        
        elif prompt_builder.is_request_for_chatbot_convo(chat_mode):
            # if persona mode, we will use all the matched stories
            if story_matches:
                story_context = _get_story_context(story_matches)
        
        # now that we have assembled all the required context, call the LLM
        user_prompt = prompt_builder.get_user_prompt(user_message, doc_context, story_context, image_context, chat_history_context)
        bot_response = _generate_AI_response(chatbot_profile, user_prompt)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:   # 429: Too Many Requests error (aka hit Gemini quota)
            app_logger.error(f"HTTP error occurred: {e.response.text}")
            bot_response = chatbot_config.get("chatbot_interactions", "retry_later_response")
            pass
    
    # 5. Update chat history
    _update_session_and_store_chat_history(session_id, user_message, bot_response)
    return {
        "session_id": session_id,
        "user_message": user_message,
        "bot_response": bot_response,
        "history": database.fetch_session(session_id)["history"],
    }
class FeedbackPayload(BaseModel):
    session_id: str
    feedback: str
    user: str

@app.post("/submit_feedback")
async def submit_feedback(payload: FeedbackPayload):
    feedback_entry = f"[Session ID: {payload.session_id}] [User: {payload.user}] Feedback: {payload.feedback}"
    feedback_logger.info(payload.feedback)

    return {"status": "success", "message": "Feedback logged"}

@app.get("/chat_history/{session_id}")
async def fetch_chat_history(session_id: str):
    return ChatSession(**database.fetch_session(session_id))

@app.post("/reload_config/")
async def reload_chatbot_config():
    chatbot_config.reload()
    global ai_client
    ai_client = AIClient(persona=chatbot_config.get("persona"))
    return {"message": "Chatbot configuration reloaded successfully."}