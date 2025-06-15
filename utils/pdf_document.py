# utils/pdf_document.py

import fitz  # PyMuPDF

from utils.config import Config
from utils.logging import get_logger
class PDFDocument:

    def __init__(self, pdf_bytes: bytes):
        # Load document from bytes
        config = Config()
        self.app_logger = get_logger(config.get("log", "app"))
        self.debug = self.config.get("hr-demo", "debug").lower() == "true"

        self.doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    def fetch_page_count(self) -> int:
        """Get the number of pages in the PDF."""
        return self.doc.page_count
   
    def extract_pages_text(self, pages: list[int], footer_text: str = None) -> str:
        text = ""
        for page_num in pages:
            page = self.doc.load_page(page_num - 1)  # 0-indexed
            page_text = page.fetch_text()
            if footer_text and footer_text in page_text:
                page_text = page_text.replace(footer_text, "").strip()
            text += page_text + "\n"

        if self.debug:
            print(f"{self.__class__.__name__} text: {text}")

        return text