# utils/ai_client.py

import google.generativeai as genai
import os
import re

from google.api_core import exceptions as google_exceptions
from googleapiclient.discovery import build

from utils.config import Config
from utils.logging import get_logger
from utils.chatbot_prompt_builder import ChatbotPromptBuilder
from utils.exceptions import TooManyRequestsError

class AIClient:
    GEMINI_API_KEY = 'AI_API_KEY'

    def __init__(self):
        self.config = Config()
        self.debug = self.config.get("hr-demo", "debug").lower() == "true"
        self.app_logger = get_logger(self.config.get("log", "app"))

        self.model_name = self.config.get('ai', 'model')

        self.chatbot = ChatbotPromptBuilder()
        self.mode = ChatbotPromptBuilder.get_app_mode()

        gemini_api_key = os.environ.get(AIClient.GEMINI_API_KEY)
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self._genai = genai
        else:
            error_msg = f"__init__() {AIClient.GEMINI_API_KEY} is missing."
            self.app_logger.error(f"{self.__class__.__name__} {error_msg}")
            raise ValueError(error_msg)

    @classmethod
    def is_request_for_app_info(cls, mode:str) -> bool:
        return (mode == ChatbotPromptBuilder.MODE_APP)
    
    @classmethod
    def is_request_for_tech_info(cls, mode:str) -> bool:
        return (mode == ChatbotPromptBuilder.MODE_TECHNICAL)
    
    @classmethod
    def is_request_for_chatbot_convo(cls, mode:str) -> bool:
        return (mode == ChatbotPromptBuilder.MODE_PERSONA)
    
    def infer_mode_from_input(self, input: str) -> str:
        input_lower = input.lower()
        words = set(re.findall(r'\w+', input_lower))

        app_specific_keywords = {
            "advisor", "alarie", "aligning", "alignment", "america", "american", "app", 
            "china", "chinese", "demo", "developer", "developers", "document", "documents", 
            "documentation", "endpoint", "engineer", "engineers", "german", "germany", 
            "globaltech", "member", "members", "motivation", "ontologyone", "ontologyone's", 
            "project", "role", "roles", "singapore", "team", "timeline", "unified", "unifying", 
            "us", "usa", "version", 
        }

        app_related_phrases = {
            "full stack", "the states", "use case"
        }

        technical_keywords = {
            "advantage", "advantages", "ai", "api", "architecture", "backend", "chatbot", 
            "cloud", "code", "database", "databases", "diagram", "diagrams", "disadvantage", 
            "disadvantages", "embedding", "embeddings", "fastapi", "framework", "frontend", 
            "graph", "image", "images", "inference", "knowledge", "language", "languages", 
            "layer", "layers", "llm", "markdown", "model", "models", "ontology", "ontologies", 
            "openai", "owl", "pic", "picture", "pictures", "prompt", "python", "quadstore", 
            "query", "rag", "rdf", "rdfs", "react", "reasoning", "semantic", "shacl", "sparql", 
            "store", "system", "swrl", "tech", "technical", "technology", "technologies", 
            "token", "tools", "triplestore", "turtle", "ui", "ux", "vector"
        }

        mode = ChatbotPromptBuilder.get_persona_mode()
        if words & app_specific_keywords or any(phrase in input_lower for phrase in app_related_phrases):
            mode = ChatbotPromptBuilder.get_app_mode()
        elif words & technical_keywords:
            mode = ChatbotPromptBuilder.get_technical_mode()

        if self.debug:
            print("=========> AIClient infer_mode mode = ", mode)

        return mode
        
    def get_chatbot_profile(self, mode) -> str:
        if mode != self.mode:
            self.mode = mode

        system_prompt = ""
        if self.mode == ChatbotPromptBuilder.MODE_APP:
            system_prompt = self.chatbot.build_app_prompt()
        elif self.mode == ChatbotPromptBuilder.MODE_TECHNICAL:
            system_prompt = self.chatbot.build_technical_prompt()
        elif self.mode == ChatbotPromptBuilder.MODE_PERSONA:
            system_prompt = self.chatbot.build_persona_prompt()
        else:
            raise ValueError(f"AIClient get_system_prompt Unknown mode: {mode}")

        return f"### Assistant_Profile\n{system_prompt}"

    def get_user_prompt(self, user_message:str, doc_context:str, story_context:str, image_context, chat_history_context:str) -> str:
        """
        the user prompt will comprise:
        doc_context: contents of RAG docs - ontology narratives, use case description
        story context: contents of origin stories
        image_context: image url and description used to generate image thumbnails
        chat history: currently 2 pairs of previous user-bot message to provide historical context
        """
        user_message = f"### Current_User_Question\n{user_message}"

        if doc_context:
            doc_context = f"### Document_Context\n{doc_context}"
        else:
            doc_context = None

        if story_context:
            story_context = f"### Story_Context\n{story_context}"
        else:
            story_context = None

        if image_context:
            image_context = f"### Diagram_Context\n{image_context}"
        else:
            image_context = None

        if chat_history_context:
            chat_history_context = f"### Conversation_History\n{chat_history_context}"
        else:
            chat_history_context = None

        # user_prompt = rag text context + stories context (if keywords detected) + chat history + user query
        context_list = [image_context, doc_context, story_context, chat_history_context, user_message]
        user_prompt = "\n\n".join(filter(None, context_list))  # filter out None values

        return user_prompt

    def generate_content(self, prompt:str) -> str:
        if self.debug:
            print(f"\n\n ==========> {self.__class__.__name__} prompt:\n{prompt}")

        try:
            model = self._genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)

            return response.text
        
        except (google_exceptions.GoogleAPIError, google_exceptions.RetryError) as e:
            err_msg = f"{self.__class__.__name__} Google API error during AI generation: {e}"
            self.app_logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        except Exception as e:
            # Detected a 429 error
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 429:
                err_msg = f"{self.__class__.__name__} 429 Too Many Requests: {e}"
                self.app_logger.warning(err_msg)
                raise TooManyRequestsError(err_msg)
            
            err_msg = f"{self.__class__.__name__} AI generation failed: {e}"
            self.app_logger.error(err_msg)
            raise RuntimeError(err_msg)