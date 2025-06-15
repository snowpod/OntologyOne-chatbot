# utils.config.py

import ast
import configparser
from pathlib import Path

from utils.logging import get_stdout_logger

class Config:
    _instance = None
    _bootstrap_logger = get_stdout_logger("config-bootstrap")

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        self.config = configparser.ConfigParser()
        config_file_path = Path(__file__).resolve().parents[1] / 'config.ini'

        if config_file_path.exists():
            try:
                self.config.read(config_file_path)
            except Exception as e:
                self._bootstrap_logger.error(f"Error reading config: {e}")
                raise
        else:
            self._bootstrap_logger.error(f"{config_file_path} not found.")
            raise FileNotFoundError(f"{config_file_path} not found.")

    def get(self, section, option, fallback=None):
        try:
            return self.config.get(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def fetch_dict(self, section, option, fallback=None):
        value = self.get(section, option, fallback)
        if value:
            try:
                return ast.literal_eval(value)
            except (SyntaxError, ValueError):
                self.app_logger.error(f"{self.__class__.__name__} Invalid dictionary format for [{section}][{option}]")
        return fallback

    def getint(self, section, option, fallback=None):
        try:
            return self.config.getint(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getboolean(self, section, option, fallback=None):
        try:
            return self.config.getboolean(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def getfloat(self, section, option, fallback=None):
        try:
            return self.config.getfloat(section, option)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback