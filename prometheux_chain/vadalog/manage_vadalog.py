"""
Vadalog Authoring Module

Static analysis and direct evaluation of Vadalog programs (authoring helpers).

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

import re

from ..client.jarvispy_client import JarvisPyClient

_FENCED_BLOCK = re.compile(r"```(?:vadalog|prolog)?[ \t]*\n([\s\S]*?)```")


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
    """Evaluate a Vadalog program directly with the given parameters.

    When the workspace is already running as many evaluations as it takes, the
    call waits and is sent again, for up to ``ENGINE_BUSY_RETRY_SECONDS``
    (config or environment, default 120; 0 disables) before raising.
    """
    return _check(JarvisPyClient.evaluate_program(
        program=program, params=params, compute=compute,
    ), "evaluate")


def generate_program(question, context=None):
    """Translate a natural-language question into a Vadalog program.

    Returns ``{'program', 'model', 'response'}``: the program, the
    ``provider/model`` that wrote it, and the translator's full markdown answer.
    Each call is metered as one program generation. Raises when the answer
    holds no program.
    """
    data = JarvisPyClient.generate_program(query=question, context=context)
    if not isinstance(data, dict):
        raise Exception("Vadalog program generation failed: unexpected response from the translator")
    program = _program_from_translation(data)
    if not program:
        raise Exception("Vadalog program generation failed: the translator returned no Vadalog program")
    meta = data.get('metadata') or {}
    return {
        'program': program,
        'model': f"{meta.get('provider', '?')}/{meta.get('model', '?')}",
        'response': data.get('response', ''),
    }


def _program_from_translation(data):
    """The structured code example, else the longest fenced block in the answer."""
    examples = data.get('code_examples') or []
    if examples and isinstance(examples[0], dict) and (examples[0].get('code') or '').strip():
        return examples[0]['code'].strip()
    blocks = sorted((b.strip() for b in _FENCED_BLOCK.findall(data.get('response') or '')),
                    key=len, reverse=True)
    return blocks[0] if blocks else ''


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
