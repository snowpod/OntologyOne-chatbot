# utils/embedding_service.py

from utils.chatbot_prompt_builder import ChatbotPromptBuilder
from utils.config import Config
from utils.image_search_helper import ImageSearchHelper
from utils.logging import get_logger
from utils.pdf_document import PDFDocument
from utils.vector_db import VectorDB

class EmbeddingService:

    def __init__(self):
        self.config = Config()
        self.debug = self.config.get("hr-demo", "debug").lower() == "true"
        self.app_logger = get_logger(self.config.get("log", "app"))

        self.vectordb = VectorDB()
        
        self.imageSearchHelper = ImageSearchHelper()

        self.chatbotPromptBuilder = ChatbotPromptBuilder()

    def set_document_text(self, file_bytes: str) -> str:
        """Extract all text from the entire document."""
        self.pdf_document = PDFDocument(pdf_bytes=file_bytes)

    def extract_page(self, start_page: int, end_page: int, headerFooterText:str = None) -> str:
        """Use PDFDocument to extract text from specific pages."""
        return self.pdf_document.extract_page_text(start_page, end_page, headerFooterText)
        
    def extract_pages(self, start_page: int, end_page: int, headerFooterText:str = None) -> str:
        """Use PDFDocument to extract text from specific pages."""
        return self.pdf_document.extract_pages_text(start_page, end_page, headerFooterText)

    def generate_text_embedding(self, text: str) -> list[float]:
        return self.vectordb.generate_embedding_for_text(text)
        
    def generate_image_embedding(self, text: str) -> list[float]:
        return self.vectordb.generate_embedding_for_image(text)
    
    def search_image_embeddings(self, query:str) -> list[tuple]:
        self.imageSearchHelper.update_context(query)
        enriched_query = self.imageSearchHelper.enrich_query(query)
        if self.debug:
            print(f"\n{self.__class__.__name__} 📝 Interpreting as: {enriched_query}")

        # top_k_matches only has the top-k image matches
        # sorted_images has the full list of images
        top_k_matches, sorted_images = self.imageSearchHelper.search(enriched_query)
        if self.debug:
            for file_name, score, description in sorted_images:
                print(f"{self.__class__.__name__} {file_name}: {score:.4f}")

        image_matches = []
        if top_k_matches:
            if self.debug:
                print(f"\n\n{self.__class__.__name__} 🔍 Top matching images:")
                for file_name, score, description in top_k_matches:
                    print(f"{file_name} (score: {score:.4f}) — tags: {description}")
            image_matches = top_k_matches
        else:
            # there are no good matches (i.e. no match with score > imageSearchHelper.TOP_K_SCORE_THRESHOLD)
            # check sorted_images for those with scores >= acceptable threshold
            # if found, we will return them since there is a chance that the images may be of acceptable accuracy 
            filteredMatches = self.imageSearchHelper.get_acceptable_matches(sorted_images)
            if self.debug:
                print(f"\n{self.__class__.__name__} ")
                print(f"🔍 Pick {self.imageSearchHelper.get_acceptable_k_hits()} images with acceptable score({self.imageSearchHelper.get_acceptable_score_threshold()}) from sorted images")
                self.imageSearchHelper.simple_print_result(filteredMatches)

            image_matches = filteredMatches

        return image_matches
           
    def get_doc_namespace(self):
        return self.config.get("vectordb", "doc_namespace")
    
    def get_stories_namespace(self):
        return self.config.get("vectordb", "stories_namespace")

    def get_top_k_text_embeddings(self, namespace:str, file_type:str, query:str, tags:list[str]=None) -> list[dict]:
        query_emb = self.generate_text_embedding(query)

        top_k_key = f"{file_type}_top_k"
        top_k = int(self.config.get("vectordb", top_k_key))

        metadata_filter = None
        if tags:
            metadata_filter = {
                "tags": {"$in": tags}
            }
            
        if self.debug:
            print(f"sending metadata_filter: {metadata_filter}")

        return self.vectordb.search_text(namespace, query_emb, top_k, metadata_filter)
    
    def get_pass_threshold_text_embeddings(self, file_type:str, matches:list[dict]) -> list[dict]:
        score_threshold_key = f"{file_type}_threshold"
        score_threshold = float(self.config.get("vectordb", score_threshold_key))

        return self.vectordb.filter_matches_by_score(matches, score_threshold)

    def search_text_embeddings(self, namespace:str, query:str, tags:list[str]=None) -> list[dict]:
        file_type = namespace
        if namespace == "OntologyOne":
            file_type = "doc"

        # get the top k number of hits from the vector db
        matches = self.get_top_k_text_embeddings(namespace, file_type, query, tags)
        if self.debug:
            print(f"\n{self.__class__.__name__} matched {file_type}:")
            self.vectordb.simple_print_result(matches)

        if not matches:
            return matches
        
        # we have hits but are they quality hits? get only those that pass the score threshold
        filtered_matches = self.get_pass_threshold_text_embeddings(file_type, matches)
        if self.debug:
            print(f"\n{self.__class__.__name__} filtered {file_type}:")
            self.vectordb.simple_print_result(filtered_matches)

        return filtered_matches