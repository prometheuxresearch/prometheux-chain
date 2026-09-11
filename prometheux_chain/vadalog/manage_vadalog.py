"""
Vadalog Authoring Module

Static analysis and direct evaluation of Vadalog programs (authoring helpers).

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

from ..client.jarvispy_client import JarvisPyClient


def _check(response, action="operation"):
    """Raise on error, return data on success."""
    if response.get('status') != 'success':
        raise Exception(f"Vadalog {action} failed: {response.get('message', 'Unknown error')}")
    return response.get('data')


def analyze_program(program, concept_type="logic", concept_name=""):
    """Analyze a Vadalog program, returning its input and head predicates."""
    return _check(JarvisPyClient.analyze_program(
        program=program, concept_type=concept_type, concept_name=concept_name,
    ), "analyze")


def build_bind(bind_annotation, predicate_name, is_output=False):
    """Build a new bind annotation by replacing the predicate name in an existing one."""
    return _check(JarvisPyClient.build_bind(
        bind_annotation=bind_annotation, predicate_name=predicate_name, is_output=is_output,
    ), "build bind")


def parse_binds(program, output_predicate=""):
    """Parse a Vadalog program into structured code plus input/output binds."""
    return _check(JarvisPyClient.parse_binds(
        program=program, output_predicate=output_predicate,
    ), "parse binds")


def evaluate_program(program, params=None, compute=None):
    """Evaluate a Vadalog program directly with the given parameters."""
    return _check(JarvisPyClient.evaluate_program(
        program=program, params=params, compute=compute,
    ), "evaluate")


def validate_concept(definition, concept_type="logic", concept_name="",
                     ontology_id=None, concept_config=None):
    """Validate a concept body without persisting it.

    Returns ``{'valid': True/False, ...}``. Unlike ``analyze_program``, this is
    a verdict (compile / syntax / structural), not predicate structure.
    """
    return _check(JarvisPyClient.validate_concept(
        definition=definition, concept_type=concept_type, concept_name=concept_name,
        ontology_id=ontology_id, concept_config=concept_config,
    ), "validate")
