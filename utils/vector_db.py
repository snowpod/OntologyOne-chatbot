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
        self.config = Config()
        self.app_logger = get_logger(self.config.get("log", "app"))
        self.debug = self.config.get("hr-demo", "debug").lower() == "true"

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._text_model = None
        self._image_model = None

        # Pinecone initialization
        pinecone_api_key = os.environ.get("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise ValueError(f"{self.__class__.__name__} Missing Pinecone API credentials.")

        self.pinecone = Pinecone(api_key=pinecone_api_key)
        self.text_index = self.pinecone.Index(self.config.get("vectordb", "text_index"))
        self.image_index = self.pinecone.Index(self.config.get("vectordb", "image_index"))

    # --- Lazy-loaded models ---
    @property
    def text_model(self):
        if self._text_model is None:
            model_name = self.config.get("embedding", "text_model")
            self._text_model = SentenceTransformer(model_name)
            if self.debug:
                print(f"{self.__class__.__name__} loaded text model: {model_name}")
        return self._text_model

    @property
    def image_model(self):
        if self._image_model is None:
            model_name = self.config.get("embedding", "image_model")
            self._image_model, _ = clip.load(model_name, device=self.device)
            if self.debug:
                print(f"{self.__class__.__name__} loaded image model: {model_name}")
        return self._image_model

    # --- Embedding methods ---
    def generate_embedding_for_text(self, text: str, normalize: bool = True) -> list[float]:
        clean_text = text.strip() if normalize else text
        return self.text_model.encode(clean_text).tolist()

    def generate_text_embedding_for_image(self, text: str) -> list[float]:
        with torch.no_grad():
            tokens = clip.tokenize([text]).to(self.device)
            embedding = self.image_model.encode_text(tokens)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
        return embedding[0].cpu().tolist()

    # --- Pinecone search ---
    def search_text(self, namespace: str, query_vector: list[float],
                    top_k: int = 3, metadata_filter: dict = None) -> list[dict]:
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

        try:
            result = self.text_index.query(**query_params)
            return result.get('matches', [])
        except Exception as e:
            self.app_logger.error(f"{self.__class__.__name__} Pinecone text query failed: {e}")
            return []

    def search_image(self, namespace: str, query_vector: list[float],
                     top_k: int = 5, metadata_filter: dict = None) -> list[dict]:
        query_params = {
            "vector": query_vector,
            "top_k": top_k,
            "include_metadata": True,
            "namespace": namespace
        }
        if metadata_filter:
            query_params["filter"] = metadata_filter

        if self.debug:
            print(f"{self.__class__.__name__} search_image metadata_filter: {metadata_filter}")

        try:
            result = self.image_index.query(**query_params)
            matches = result.get("matches", [])
            for match in matches:
                metadata = match.get("metadata", {})
                if "id" in match:
                    metadata["file_name"] = os.path.basename(match["id"])
            return [match.get("metadata", {}) for match in matches]
        except Exception as e:
            self.app_logger.error(f"{self.__class__.__name__} Pinecone image query failed: {e}")
            return []

    # --- Utilities ---
    def filter_matches_by_score(self, matches: list[dict], threshold: float) -> list[dict]:
        if not matches:
            return []
        return [
            match for match in matches
            if isinstance(match.get("score"), (float, int)) and match["score"] >= threshold
        ]

    def simple_print_result(self, result: list[dict]):
        if not result:
            print(f"{self.__class__.__name__} ⚠️ No matches found.")
            return

        for match in result:
            metadata = match.get("metadata", {})
            file_name = metadata.get("file_name", "")
            score = match.get("score", 0.0)
            print(f"{self.__class__.__name__} {file_name}, score: {score:.4f}")