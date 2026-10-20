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


def evaluate_program(program, params=None, compute=None, execution_id=None):
    """Evaluate a Vadalog program directly with the given parameters.

    When the workspace is already running as many evaluations as it takes, the
    call waits and is sent again, for up to ``ENGINE_BUSY_RETRY_SECONDS``
    (config or environment, default 120; 0 disables) before raising.

    ``execution_id`` is an id of your choosing, shared by every evaluation you
    may want to stop together: ``stop_evaluation(execution_id)`` stops them
    and leaves everyone else's running.
    """
    return _check(JarvisPyClient.evaluate_program(
        program=program, params=params, compute=compute, execution_id=execution_id,
    ), "evaluate")


def stop_evaluation(execution_id=None):
    """Stop the evaluations sent with ``execution_id``, or a run with that id.

    A call waiting on them raises "Execution stopped by user." within a
    second, and later calls with the same id are refused for a few minutes.
    The engine itself is stopped only when nothing else is running on it.

    Without ``execution_id``     every evaluation and run on the workspace is
    stopped, other users' included: the Stop button's behaviour.
    """
    response = JarvisPyClient.stop_evaluation(execution_id=execution_id) or {}
    # When the engine is stopped too, its own answer comes back as is, without
    # the usual {status, data} envelope.
    if response.get('status') == 'error':
        raise Exception(f"Vadalog stop failed: {response.get('message', 'Unknown error')}")
    return response.get('data') if 'status' in response else response


def evaluation_status():
    """Whether the workspace takes a new evaluation now, and how many it takes at once.

    Returns ``status`` ("ready" or "busy"), ``runs_in_flight``,
    ``engine_calls_in_flight`` and, on platforms that report it,
    ``engine_call_capacity``: how many evaluations run at the same time, the
    useful upper bound for client-side parallelism. Calls past it are refused
    as busy (and retried by ``evaluate_program``).
    """
    return _check(JarvisPyClient.evaluation_status(), "status")


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
