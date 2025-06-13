# utils/text_file_helper.py

import os
from pathlib import Path

class TextFileHelper:
    """Generic file utility class for reading, writing, listing, and deleting files."""

    @staticmethod
    def read_text(file_path, encoding="utf-8"):
        """Read the contents of a text file."""
        with open(file_path, "r", encoding=encoding) as f:
            return f.read()

    @staticmethod
    def write_text(file_path, content, encoding="utf-8"):
        """Write text content to a file (overwrite if exists)."""
        with open(file_path, "w", encoding=encoding) as f:
            f.write(content)

    @staticmethod
    def append_text(file_path, content, encoding="utf-8"):
        """Append text to a file."""
        with open(file_path, "a", encoding=encoding) as f:
            f.write(content)

    @staticmethod
    def file_exists(file_path):
        """Check if a file exists."""
        return os.path.isfile(file_path)

    @staticmethod
    def ensure_dir(directory):
        """Create directory if it doesn't exist."""
        os.makedirs(directory, exist_ok=True)
