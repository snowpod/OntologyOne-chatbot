# utils/ontology_mapper.py

import json

from pathlib import Path
from typing import List

# require to extract ontology summary
from rdflib import Graph, RDF, RDFS, OWL
from rdflib.term import URIRef

from utils.config import Config
from utils.logging import get_logger
from utils.text_file_helper import TextFileHelper

class OntologyMapper:
    """Loads country-to-ontology mapping from JSON file."""
    _ontology_cache = {}  # class-level cache

    def __init__(self, ontology_mapping_file: str):
        self.config = Config()
        self.app_logger = get_logger(self.config.get("log", "app"))

        self.country_mappings = {}
        if TextFileHelper.file_exists(ontology_mapping_file):
            content = TextFileHelper.read_text(ontology_mapping_file)
            self.app_logger.info(f"{self.__class__.__name__} {ontology_mapping_file}")
            self.country_mappings = {k: v for k, v in json.loads(content).items()}

        if not self.country_mappings:
            err_msg = f"{self.__class__.__name__} {ontology_mapping_file} not found."
            self.app_logger.error(err_msg)
            raise FileNotFoundError(err_msg)
    
    def map_entities_to_ontologies(self, countries: List[str], persons: List[str]) -> List[str]:
        """Maps detected countries to ontology files."""
        mapped_ontologies = []
        if countries:
            for country in countries:
                country = country.lower()
                if country in self.country_mappings:
                    mapped_ontologies.append(self.country_mappings.get(country))

            mapped_ontologies.append(self.country_mappings.get("DEFAULT"))

        # If no mappings were found, return all ontologies including the DEFAULT ontology
        if not mapped_ontologies:
            mapped_ontologies = list(self.country_mappings.values())

        self.app_logger.info(f"{self.__class__.__name__} map_entities_to_ontologies(): {mapped_ontologies}")

        return mapped_ontologies
    
    def load_ontology_files(self, ontology_file_list):
        """Loads the contents of multiple ontology files."""
        ontology_text = []
        ontology_folder = Path(self.config.get('ontology', 'folder'))

        for ontology_file in ontology_file_list:
            full_path = ontology_folder / ontology_file

            if full_path in self._ontology_cache:
                text = self._ontology_cache[full_path]
                self.app_logger.info(f"{self.__class__.__name__} cache hit: {full_path}")
            else:
                if TextFileHelper.file_exists(full_path):
                    text = TextFileHelper.read_text(full_path)
                    self._ontology_cache[full_path] = text  # store in cache
                else:
                    err_msg = f"{self.__class__.__name__} Ontology file '{full_path}' not found."
                    self.app_logger.warning(err_msg)
                    raise FileNotFoundError(err_msg)

            file_name = Path(ontology_file).stem.capitalize().replace('_', ' ')
            ontology_text.append("## " + file_name + "\n" + text)

        return "\n\n".join(ontology_text)
    
    def _get_inverse_properties(self, g: Graph):
        inverse_map = {}
        for s, _, o in g.triples((None, OWL.inverseOf, None)):
            inverse_map[s] = o
            inverse_map[o] = s  # bi-directional
        return inverse_map

    def _update_domain_range(self, g: Graph, prop_uri, inv_prop_uri):
        prop_domain = next(g.objects(prop_uri, RDFS.domain), None)
        prop_range = next(g.objects(prop_uri, RDFS.range), None)

        if prop_domain and prop_range:
            g.add((inv_prop_uri, RDFS.domain, prop_range))
            g.add((inv_prop_uri, RDFS.range, prop_domain))
        else:
            inv_domain = next(g.objects(inv_prop_uri, RDFS.domain), None)
            inv_range = next(g.objects(inv_prop_uri, RDFS.range), None)
            if inv_domain and inv_range:
                g.add((prop_uri, RDFS.domain, inv_range))
                g.add((prop_uri, RDFS.range, inv_domain))

    def _extract_ontology_summary(self, rdf_file:str) -> dict:
        g = Graph()
        g.parse(rdf_file)

        ns_manager = g.namespace_manager
        ontology_summary = {
            "prefixes": {},
            "classes": {},
            "properties": {}
        }

        # Extract namespaces
        for prefix, ns in ns_manager.namespaces():
            ontology_summary["prefixes"][prefix] = str(ns)

        inverse_props = self._get_inverse_properties(g)
        for prop, inv_prop in inverse_props.items():
            self._update_domain_range(g, prop, inv_prop)

        # Helper to extract labels and comments
        def get_labels(entity):
            labels = {}
            for _, _, label in g.triples((entity, RDFS.label, None)):
                if hasattr(label, 'language'):
                    labels[label.language] = str(label)
                else:
                    labels["und"] = str(label)
            return labels

        def get_comment(entity):
            for _, _, comment in g.triples((entity, RDFS.comment, None)):
                return str(comment)
            return ""

        # Extract classes
        for cls in g.subjects(RDF.type, OWL.Class):
            uri = str(cls)
            qname = ns_manager.qname(cls)
            ontology_summary["classes"][qname] = {
                "labels": get_labels(cls),
                "comment": get_comment(cls)
            }

        # Extract properties
        for prop in g.subjects(RDF.type, OWL.ObjectProperty):
            qname = ns_manager.qname(prop)
            ontology_summary["properties"][qname] = {
                "type": "object",
                "domain": None,
                "range": None,
                "labels": get_labels(prop)
            }
        for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
            qname = ns_manager.qname(prop)
            ontology_summary["properties"][qname] = {
                "type": "datatype",
                "domain": None,
                "range": None,
                "labels": get_labels(prop)
            }

        # Domains and Ranges
        for prop_qname, prop_info in ontology_summary["properties"].items():
            try:
                prop_uri = g.namespace_manager.expand_curie(prop_qname)
            except ValueError:
                # fallback: try treating the prop_qname as a full URI
                prop_uri = URIRef(prop_qname)

            for _, _, domain in g.triples((prop_uri, RDFS.domain, None)):
                try:
                    prop_info["domain"] = ns_manager.qname(domain)
                except Exception:
                    prop_info["domain"] = str(domain)

            for _, _, range_ in g.triples((prop_uri, RDFS.range, None)):
                try:
                    prop_info["range"] = ns_manager.qname(range_)
                except Exception:
                    prop_info["range"] = str(range_)

        return ontology_summary