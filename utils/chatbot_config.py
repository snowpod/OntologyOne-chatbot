# utils/chatbot_config.py

import json
import os
import threading

from utils.config import Config 
from utils.logging import get_logger

class ChatbotConfig:
    _instance = None
    _lock = threading.Lock()  # Ensure thread safety

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # Double-check inside the lock
                    cls._instance = super(ChatbotConfig, cls).__new__(cls)
                    cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Load chatbot configuration from a JSON file, with filename from config.ini."""
        config = Config()  # Load system-wide config
        chatbot_config_file = config.get("hr-demo", "chatbot_config_file", fallback="chatbot_config.json")

        config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'chatbot_config.json')
        self.app_logger = get_logger(config.get("log", "app"))
        
        self.app_logger.info(f"_load_config() config_file_path: {config_file_path}")
        if not os.path.exists(config_file_path):
            raise FileNotFoundError(f"_load_config() Chatbot config file {config_file_path} not found.")

        self._load_json(config_file_path)

    def _load_json(self, config_file_path:str):
        """(Re)load chatbot config JSON."""
        if os.path.exists(config_file_path):
            try:
                with open(config_file_path, 'r', encoding='utf-8') as file:
                    self.config = json.load(file)
                    self.app_logger.info(f"{self.__class__.__name__} Chatbot config loaded from {config_file_path}")
            except json.JSONDecodeError as e:
                self.app_logger.error(f"{self.__class__.__name__} Invalid JSON in {config_file_path}: {e}")
                raise ValueError(f"{self.__class__.__name__} Invalid JSON format in {config_file_path}")
        else:
            raise FileNotFoundError(f"{self.__class__.__name__} Chatbot config file {config_file_path} not found.")

    def get(self, *keys, fallback=None):
        """
        Retrieve nested values from the chatbot JSON config.
        Example:
            chatbot_config.get("persona", "name")  # Returns "Harper"
        """
        try:
            value = self.config
            for key in keys:
                value = value[key]
            return value
        except KeyError:
            return fallback

    def reload(self):
        """Reload chatbot configuration at runtime."""
        with self._lock:
            self.app_logger.info("{self.__class__.__name__} reload() Reloading chatbot configuration...")
            self._load_json()
            self.app_logger.info("{self.__class__.__name__} reload() Chatbot configuration reloaded successfully.")