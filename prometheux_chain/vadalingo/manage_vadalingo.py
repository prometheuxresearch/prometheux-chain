"""
Vadalingo Translation Module

Translate SQL, RDF, and OWL into Vadalog.

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

from ..client.jarvispy_client import JarvisPyClient


def _check(response, action="operation"):
    """Raise on error, return data on success."""
    if response.get('status') != 'success':
        raise Exception(f"Vadalingo {action} failed: {response.get('message', 'Unknown error')}")
    return response.get('data')


def translate_sql_to_vadalog(ontology_id, sql_data):
    """Translate a SQL query into Vadalog."""
    return _check(JarvisPyClient.translate_sql_to_vadalog(
        ontology_id=ontology_id, sql_data=sql_data,
    ), "translate sql")


def translate_rdf_to_vadalog(ontology_id, rdf_data):
    """Translate RDF data into Vadalog."""
    return _check(JarvisPyClient.translate_rdf_to_vadalog(
        ontology_id=ontology_id, rdf_data=rdf_data,
    ), "translate rdf")


def translate_owl_to_vadalog(ontology_id, owl_content, base_namespace, data_base_path=None,
                             options=None, add_concepts=False):
    """Translate an OWL ontology into Vadalog rules."""
    return _check(JarvisPyClient.translate_owl_to_vadalog(
        ontology_id=ontology_id, owl_content=owl_content, base_namespace=base_namespace,
        data_base_path=data_base_path, options=options, add_concepts=add_concepts,
    ), "translate owl")
