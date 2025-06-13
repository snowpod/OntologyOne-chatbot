# utils/graph_db.py

import os
import requests

from utils.config import Config
from utils.logging import get_logger

class GraphDB:

    def __init__(self):
        config = Config()
        self.app_logger = get_logger(config.get("log", "app"))
        self.debug = config.get("hr-demo", "debug").lower() == "true"

        host_key = 'host_dev'
        repository_key = 'repository_dev'
        if os.getenv("ENV") == "prod":
            host_key = 'host_prod'
            repository_key = 'repository_prod'

        self.host = config.get('graphdb', host_key)
        self.repository = config.get('graphdb', repository_key)
        self.endpoint = f"{self.host}/repositories/{self.repository}"

        self.app_logger.info(f"{self.__class__.__name__} endpoint: {self.endpoint}")

    def query_graph_db(self, sparql_query):
        """Send the SPARQL query to GraphDB and return results."""
        params = {"query": sparql_query}
        headers = {"Accept": "application/json"}

        try:
            response = requests.post(self.endpoint, data=params, headers=headers, timeout=10)
            response.raise_for_status()  # Ensure HTTP 200-299
            self.app_logger.info(f"{self.__class__.__name__} Received response from GraphDB.")

            return response.json()

        except requests.exceptions.RequestException as e:
            err_msg = f"{self.__class__.__name__} Error while querying GraphDB: {e}"
            if self.debug:
                print(err_msg)
            self.app_logger.error(err_msg)
            return {"error": str(e)}