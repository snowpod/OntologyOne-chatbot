# utils/text_file_helper.py

import os

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
    def file_exists(file_path):
        """Check if a file exists."""
        return os.path.isfile(file_path)