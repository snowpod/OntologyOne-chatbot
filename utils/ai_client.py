# utils/ai_client.py

import google.generativeai as genai
import os

from google.api_core import exceptions as google_exceptions
from googleapiclient.discovery import build

from utils.config import Config
from utils.logging import get_logger

class AIClient:
    GEMINI_API_KEY = 'AI_API_KEY'

    def __init__(self):
        self.config = Config()
        self.debug = self.config.get("hr-demo", "debug").lower() == "true"
        self.app_logger = get_logger(self.config.get("log", "app"))

        self.model_name = self.config.get('ai', 'model')

        gemini_api_key = os.environ.get(AIClient.GEMINI_API_KEY)
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self._genai = genai
        else:
            error_msg = f"__init__() {AIClient.GEMINI_API_KEY} is missing."
            self.app_logger.error(f"{self.__class__.__name__} {error_msg}")
            raise ValueError(error_msg)

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
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 429:
                err_msg = f"{self.__class__.__name__} 429 Too Many Requests: {e}"
                self.app_logger.warning(err_msg)
                raise RuntimeError(err_msg)
            
            err_msg = f"{self.__class__.__name__} AI generation failed: {e}"
            self.app_logger.error(err_msg)
            raise RuntimeError(err_msg)