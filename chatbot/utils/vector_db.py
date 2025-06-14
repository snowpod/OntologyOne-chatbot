# utils/vector_db.py

import os
import torch
import clip
import numpy as np

from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

from utils.config import Config
from utils.logging import get_logger

class VectorDB:

    def __init__(self):
        config = Config()
        self.app_logger = get_logger(config.get("log", "app"))
        self.debug = config.get("hr-demo", "debug").lower() == "true"

        # Init Pinecone
        pinecone_api_key = os.environ.get("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise ValueError(f"{self.__class__.__name__} Missing Pinecone API credentials.")
        pc = Pinecone(api_key=pinecone_api_key)

        self.text_model = SentenceTransformer(config.get("embedding", "text_model"))

        image_model_name = config.get("embedding", "image_model")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.image_model, _ = clip.load(image_model_name, device=self.device)

        text_index_name = config.get("vectordb", "text_index")
        image_index_name = config.get("vectordb", "image_index")

        self.text_index = pc.Index(text_index_name)
        self.image_index = pc.Index(image_index_name)

    def generate_embedding_for_text(self, text: str) -> list[float]:
        return self.text_model.encode(text).tolist()

    def generate_embedding_for_image(self, text: str) -> list[float]:
        return self.image_model.encode(text).tolist()
    
    def generate_text_embedding_for_image(self, text: str) -> list[float]:
        """Use OpenAI CLIP model to generate a shared embedding for text."""
        with torch.no_grad():
            tokens = clip.tokenize([text]).to(self.device)
            embedding = self.image_model.encode_text(tokens)
            embedding = embedding.norm(dim=-1, keepdim=True)

        return embedding[0].cpu().tolist()

    def filter_matches_by_score(self, matches: list[dict], threshold: float) -> list[dict]:
        """
        Filter matches by a minimum score threshold.

        Args:
            matches (list[dict]): List of matches from search_text().
            threshold (float): Minimum similarity score to include the match.

        Returns:
            list[dict]: Filtered list of matches with score >= threshold.
        """
        if not matches:
            return []

        filtered = []
        for match in matches:
            try:
                score = float(match.get("score", 0.0))
                if score >= threshold:
                    filtered.append(match)
            except (TypeError, ValueError):
                continue  # skip if score is not convertible to float

        return filtered

    def simple_print_result(self, result:list[dict]):
        if result:
            for match in result:
                file_name = match.get("metadata").get("file_name", "")
                score = match.get("score", 0.0)
                print(f"{self.__class__.__name__} {file_name}, score: {score:.4f}")
        else:
            print(f"{self.__class__.__name__} ⚠️ No matches found.")

    def search_text(self, namespace:str, query_vector: list[float],
                    top_k:int=3, metadata_filter:dict=None) -> list[dict]:
        """
        top_k results is returned from the text index sorted in descending order of score 
        but they may not be of acceptable quality.
        if score_threshold is specified, we will return results that are >= score_threshold.
        if score_threshold is None, then we will just return results as-is.
        """
        query_params = {
            "vector": query_vector,
            "top_k": top_k,
            "include_metadata": True,
            "namespace": namespace
        }
        if metadata_filter:
            query_params["filter"] = metadata_filter
        
        if self.debug:
            print(f"{self.__class__.__name__} search_text metadata_filter: {metadata_filter}")

        result = self.text_index.query(**query_params)

        return result['matches']