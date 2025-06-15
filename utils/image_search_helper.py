# image_search_helper.py

import json
import os
import re

from utils.config import Config
from utils.logging import get_logger

class ImageSearchHelper:

    def __init__(self):
        config = Config()
        self.debug = config.get("hr-demo", "debug").lower() == "true"
        self.app_name = config.get("hr-demo", "name")

        self.app_logger = get_logger(config.get("log", "app"))

        self.config = config
        self.clip = None
        self.torch = None
        self.model = None
        self.preprocess = None
        self.device = None

        image_metadata_path = config.get("embedding", "image_metadata_path")
        image_search_config_path = config.get("embedding", "image_search_config_path")

        self.metadata = None
        try:
            self.metadata = self.load_metadata(image_metadata_path)
        except Exception as e:
            raise

        self.image_search_config = self.load_metadata(image_search_config_path)
        self.ontology_keywords = set(self.image_search_config.get("ONTOLOGY_KEYWORDS", []))
        self.focus_keywords = set(self.image_search_config.get("FOCUS_KEYWORDS", []))
        self.canonical_keywords = sorted(self.ontology_keywords | self.focus_keywords)
        self.stopwords = set(self.image_search_config.get("STOPWORDS", []))
        self.manual_corrections = self.image_search_config.get("MANUAL_CORRECTIONS", {})

        self.context = {}

    def _load_clip_model(self):
        if self.clip is None or self.torch is None:
            import clip
            import torch
            self.clip = clip
            self.torch = torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            image_model_name = self.config.get("embedding", "image_model")
            self.model, self.preprocess = clip.load(image_model_name, device=self.device)

    def get_ontology_keywords(self):
        return self.ontology_keywords

    def get_focus_keywords(self):
        return self.focus_keywords

    def get_metadata(self):
        return self.metadata

    def load_metadata(self, json_file_path):
        full_path = os.path.abspath(json_file_path)
        if self.debug:
            print(f"{self.__class__.__name__} Resolved full path to image metadata: {full_path}")

        if not os.path.isfile(json_file_path):
            raise FileNotFoundError(f"{self.__class__.__name__} Image config file not found: {json_file_path}")

        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"{self.__class__.__name__} Error decoding JSON from {json_file_path}: {e}")

    def _extract_keywords(self, text, score_threshold=90):
        import re
        from rapidfuzz import fuzz, process

        words = re.findall(r'\b\w+\b', text.lower())
        keywords = []

        for word in words:
            if word in self.manual_corrections:
                keywords.append(self.manual_corrections[word])
                continue
            if word in self.stopwords or len(word) <= 2:
                continue

            best_match = process.extractOne(
                word,
                self.canonical_keywords,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=score_threshold
            )
            keywords.append(best_match[0] if best_match else word)

        return keywords

    def update_context(self, user_query):
        keywords = self._extract_keywords(user_query)

        matched_locations = [k for k in keywords if k in self.ontology_keywords]
        if matched_locations:
            self.context["last_location"] = matched_locations[-1]

        matched_focus = [k for k in keywords if k in self.focus_keywords]
        if matched_focus:
            self.context["last_focus"] = matched_focus[-1]

    def enrich_query(self, user_query):
        tokens = re.findall(r"\w+|[^\w\s]", user_query, re.UNICODE)
        corrected_tokens = [
            self.manual_corrections.get(token.lower(), token) if token.isalnum() else token
            for token in tokens
        ]
        corrected_query = " ".join(corrected_tokens)

        keywords = self._extract_keywords(corrected_query)

        parts = []
        query_lower = corrected_query.lower()
        pattern = rf"\b{re.escape(self.app_name.lower())}('s)?\b"
        has_location_keyword = any(k in self.ontology_keywords for k in keywords)
        should_inject_ontology = not has_location_keyword

        if should_inject_ontology and not has_location_keyword:
            if self.context.get("last_location"):
                parts.append(self.context["last_location"])

        parts.append(corrected_query)

        if not any(k in self.focus_keywords for k in keywords):
            if self.context.get("last_focus"):
                parts.append(self.context["last_focus"])

        return " ".join(parts)

    def _embed_texts(self, texts):
        self._load_clip_model()
        with self.torch.no_grad():
            tokens = self.clip.tokenize(texts).to(self.device)
            embeddings = self.model.encode_text(tokens)
            embeddings /= embeddings.norm(dim=-1, keepdim=True)
        return embeddings

    def search(self, enriched_query: str, top_k_hits: int = None):
        top_k_score_threshold = self.image_search_config.get("TOP_K_SCORE_THRESHOLD", 0.8)
        if top_k_hits is None:
            top_k_hits = self.image_search_config.get("TOP_K_HITS", 3)

        query_embedding = self._embed_texts([enriched_query])[0]
        tag_texts = [item["description"] for item in self.metadata]
        tag_embeddings = self._embed_texts(tag_texts)
        similarities = (tag_embeddings @ query_embedding).cpu().numpy()

        scored_results = [
            (item["file_name"], float(score), item["description"])
            for item, score in zip(self.metadata, similarities)
        ]
        sorted_results = sorted(scored_results, key=lambda x: x[1], reverse=True)
        filtered = [r for r in sorted_results if r[1] >= top_k_score_threshold]

        return (filtered[:top_k_hits] if len(filtered) > top_k_hits else filtered, sorted_results)

    def get_acceptable_k_hits(self):
        return self.image_search_config.get("ACCEPTABLE_K_HITS")

    def get_acceptable_score_threshold(self):
        return self.image_search_config.get("ACCEPTABLE_SCORE_THRESHOLD")

    def get_acceptable_matches(self, all_matches: list[tuple]) -> list[tuple]:
        acceptable_k_hits = self.get_acceptable_k_hits()
        acceptable_score_threshold = self.get_acceptable_score_threshold()

        filtered_matches = []
        for match in all_matches:
            if match[1] >= acceptable_score_threshold:
                filtered_matches.append(match)
                if len(filtered_matches) == acceptable_k_hits:
                    break
            else:
                break

        return filtered_matches

    def simple_print_result(self, result: list[dict]):
        if result:
            for file_name, score, description in result:
                print(f"{self.__class__.__name__} {file_name}, score: {score:.4f}")
        else:
            print(f"{self.__class__.__name__} ⚠️ No image matches found.")