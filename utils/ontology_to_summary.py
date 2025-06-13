# utils/ontology_to_summmary.py

import re

from pathlib import Path

# require to extract ontology summary
from rdflib import Graph, RDF, RDFS, OWL, URIRef
from rdflib.term import URIRef

from utils.config import Config

def _get_inverse_properties(g: Graph):
    inverse_map = {}
    for s, _, o in g.triples((None, OWL.inverseOf, None)):
        inverse_map[s] = o
        inverse_map[o] = s  # bi-directional
    return inverse_map

def _update_domain_range(g: Graph, prop_uri, inv_prop_uri):
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
        
def get_ontology_folder() -> str:
    config = Config()
    relative_folder = config.get('ontology', 'folder')

    # Get the current working directory as a Path object
    current_working_directory = Path.cwd()
    summary_folder = current_working_directory / relative_folder
    print(f"current_working_directory: {current_working_directory}, summary_folder: {summary_folder}")

    return str(summary_folder)

def get_used_namespaces(g:Graph):
    # Collect all namespaces actually used in the RDF triples
    used_namespaces = set()

    for s, p, o in g:
        for term in [s, p, o]:
            if isinstance(term, URIRef):
                term_str = str(term)
                if '#' in term_str:
                    ns_uri = term_str.rsplit('#', 1)[0] + '#'
                else:
                    ns_uri = term_str.rsplit('/', 1)[0] + '/'
                # Exclude swrl-related namespaces early
                if 'swrl' not in ns_uri.lower():
                    used_namespaces.add(ns_uri)
    
    return used_namespaces

def _remove_rules_section(content: str) -> str:
    """
    Removes everything from the start of the Rules comment block to EOF,
    then appends </rdf:RDF> to ensure valid RDF/XML.
    """
    # Find the position of the line containing "// Rules"
    match = re.search(r'^\s*//\s*Rules\s*$', content, re.MULTILINE)
    if match:
        # Get start index of that line in content
        start_index = match.start()
        print(f"start_index = {start_index}")

        # Slice content before "// Rules" line
        trimmed_content = content[:start_index]
        # Append closing comment and rdf tag
        trimmed_content += " -->\n</rdf:RDF>"

        return trimmed_content

    # If no Rules comment is found, return content unchanged
    return content

def remove_swrl_namespaces(rdf_content:str) -> str:
    # Regex to find xmlns attributes for 'swrl', 'swrla', 'swrlb'
    # This pattern looks for "xmlns:swrl", "xmlns:swrla", or "xmlns:swrlb"
    # followed by '="...' and a closing quote, capturing the whole attribute.
    # It handles optional spaces and newlines around the attribute.
    # The 're.DOTALL' flag allows '.' to match newlines, which is useful
    # if the attributes are spread across multiple lines within the tag.
    pattern = re.compile(
        r'\s*xmlns:swrl(?:a|b)?="[^"]*?"',
        re.DOTALL
    )

    # Use re.sub to replace the matched xmlns attributes with an empty string
    cleaned_rdf_content = pattern.sub("", rdf_content)

    return cleaned_rdf_content

def compact_ontology(content:str) -> str:
    """
    Compact rdf/xml content by removing HTML-style comments and collapsing multiple newlines.
    """
    # Normalize line endings
    compact_content = content.replace('\r\n', '\n')

    # remove SWRL rule section and swrl-related namespaces
    compact_content = remove_swrl_namespaces(compact_content)
    # NOTE: this follows Protege's habit of outputting the swrl rules at the end
    compact_content = _remove_rules_section(compact_content)

    # remove HTML comments
    pattern = r'<!--.*?-->'
    compact_content = re.sub(pattern, '', compact_content, flags=re.DOTALL)

    # collapse multiple newlines into a single newline
    compact_content = re.sub(r'\n\s*\n+', '\n', compact_content.strip())

    return compact_content

import re

def replace_iris_with_prefixes(content: str) -> str:
    # Match the opening <rdf:RDF ...> tag (including newlines)
    match = re.search(r'<rdf:RDF[^>]*>', content, re.DOTALL)
    if not match:
        return content  # No match, return original

    header = match.group(0)
    header_end = match.end()
    body = content[header_end:]

    # Extract xmlns definitions from header only
    xmlns_pattern = r'xmlns:(\w+)="([^"]+)"'
    prefix_map = dict(re.findall(xmlns_pattern, header))

    # Sort namespaces by length (desc) to avoid prefixing partial matches
    sorted_namespaces = sorted(prefix_map.items(), key=lambda x: len(x[1]), reverse=True)

    # Apply replacements only in the body
    for prefix, ns in sorted_namespaces:
        if not ns.endswith(('#', '/')):
            ns += '#'
        body = body.replace(ns, f"{prefix}:")

    return header + body

def extract_ontology_summary(rdf_file:str) -> dict:
    g = Graph()
    g.parse(rdf_file)

    ontology_summary = {
        "prefixes": {},
        "classes": {},
        "properties": {}
    }

    # Extract namespaces
    ns_manager = g.namespace_manager
    used_namespaces = get_used_namespaces(g)
    for prefix, ns in ns_manager.namespaces():
        if str(ns) in used_namespaces:
            ontology_summary["prefixes"][prefix] = str(ns)
    #for prefix, ns in ns_manager.namespaces():
    #    ontology_summary["prefixes"][prefix] = str(ns)

    inverse_props = _get_inverse_properties(g)
    for prop, inv_prop in inverse_props.items():
        _update_domain_range(g, prop, inv_prop)

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