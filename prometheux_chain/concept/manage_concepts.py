"""
Concept Management Module

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

from ..client.jarvispy_client import JarvisPyClient


def _check(response, action="operation"):
    """Raise on error, return data on success."""
    if response.get('status') != 'success':
        raise Exception(f"Concept {action} failed: {response.get('message', 'Unknown error')}")
    return response.get('data')


def save_concept(ontology_id, definition, python_scripts=None,
                 description=None, concept_type="logic", concept_name=None,
                 binds=None, output_predicate="", existing_name=None,
                 position=None, group="group_id", compute=None, force_overwrite=False,
                 concept_config=None):
    """Save a concept. Only ``definition`` is required; everything else has defaults."""
    return _check(JarvisPyClient.save_concept(
        ontology_id=ontology_id, definition=definition, python_scripts=python_scripts,
        description=description, concept_type=concept_type,
        concept_name=concept_name, binds=binds, output_predicate=output_predicate,
        existing_name=existing_name, position=position, group=group, compute=compute,
        force_overwrite=force_overwrite, concept_config=concept_config), "save")


def rename_concept(ontology_id, old_name, new_name):
    """Rename a concept and propagate the change to all dependents."""
    return _check(JarvisPyClient.rename_concept(
        ontology_id=ontology_id, old_name=old_name, new_name=new_name), "rename")


def run_concept(ontology_id, concept_name, params=None,
                force_rerun=True, persist_outputs=False, compute=None):
    """Run a concept. Only ``project_id`` and ``concept_name`` are required."""
    return _check(JarvisPyClient.run_concept(
        ontology_id=ontology_id, concept_name=concept_name,
        params=params or {}, force_rerun=force_rerun,
        persist_outputs=persist_outputs, compute=compute), "run")


def run_concept_stream(ontology_id, concept_name, params=None,
                       force_rerun=True, persist_outputs=False, compute=None):
    """Run a concept and yield streaming status events over a WebSocket.

    Yields the raw server messages (dicts with an ``event`` key, e.g.
    ``concept_status``, ``complete``, ``error``). Iteration ends after the
    terminal ``complete`` or ``error`` event.
    """
    return JarvisPyClient.run_concept_stream(
        ontology_id=ontology_id, concept_name=concept_name,
        params=params or {}, force_rerun=force_rerun,
        persist_outputs=persist_outputs, compute=compute)


def list_concepts(ontology_id):
    """List all concepts in a project."""
    return _check(JarvisPyClient.list_concepts(ontology_id=ontology_id), "list")


def cleanup_concepts(ontology_id, concept_names=None):
    """Delete concepts from a project. If ``concept_names`` is None, deletes all."""
    return _check(JarvisPyClient.cleanup_concepts(
        ontology_id=ontology_id, concept_names=concept_names), "cleanup")


def reorder_concepts(ontology_id, concept_names, group=None):
    """Reorder concepts within a project (optionally within a group)."""
    return _check(JarvisPyClient.reorder_concepts(
        ontology_id=ontology_id, concept_names=concept_names, group=group), "reorder")


def get_execution_statuses():
    """Return the latest non-idle run per project."""
    return _check(JarvisPyClient.get_execution_statuses(), "execution statuses")


def get_execution_status(ontology_id):
    """Return the latest concept-run snapshot for a project."""
    return _check(JarvisPyClient.get_execution_status(ontology_id=ontology_id), "execution status")


def generate_concept_description(ontology_id, concept_name):
    """Generate (and cache) a natural-language description for a concept."""
    return _check(JarvisPyClient.generate_concept_description(
        ontology_id=ontology_id, concept_name=concept_name), "generate description")


def get_concept_description(ontology_id, concept_name):
    """Read back a concept's description, regenerating it if stale."""
    return _check(JarvisPyClient.get_concept_description(
        ontology_id=ontology_id, concept_name=concept_name), "get description")


def fetch_results(ontology_id, output_predicate, page=1, page_size=10,
                  order_by=None, params=None, compute=None,
                  search_term=None, column_filters=None, total_count=None):
    """Fetch paginated results for a populated predicate.

    Optional ``search_term`` (free-text OR across columns) and ``column_filters``
    (operator-based) combine with ``params`` on the same ``/fetch`` route.
    """
    return _check(JarvisPyClient.fetch_results(
        ontology_id=ontology_id, output_predicate=output_predicate,
        page=page, page_size=page_size, order_by=order_by,
        params=params, compute=compute, search_term=search_term,
        column_filters=column_filters, total_count=total_count), "fetch")


def search_results(ontology_id, output_predicate, search_term=None, column_filters=None,
                   page=1, page_size=0, order_by=None, compute=None):
    """Search a populated predicate by free text and/or column filters.

    Convenience wrapper around ``fetch_results`` — the dedicated ``/search``
    route no longer exists.
    """
    return fetch_results(
        ontology_id=ontology_id, output_predicate=output_predicate,
        page=page, page_size=page_size, order_by=order_by,
        compute=compute, search_term=search_term, column_filters=column_filters,
    )


def query_concept(ontology_id, concept_name, sql, compute=None):
    """Run a read-only SQL SELECT over one populated concept."""
    return _check(JarvisPyClient.query_concept(
        ontology_id=ontology_id, concept_name=concept_name, sql=sql, compute=compute,
    ), "query")


def search_similar_concepts(query, top_k=0, exclude_ontology_id=None):
    """Find concepts across ontologies that are semantically similar to ``query``."""
    return _check(JarvisPyClient.search_similar_concepts(
        query=query, top_k=top_k, exclude_ontology_id=exclude_ontology_id,
    ), "search similar")


def llm_analysis(ontology_id, question, predicate_names=None, predicate_data=None,
                 params=None, prompt_tuning=None, prompt_tuning_name=None,
                 default_response=None, compute=None):
    """Ask an LLM a question grounded in one or more predicate tables."""
    return _check(JarvisPyClient.llm_analysis(
        ontology_id=ontology_id, question=question, predicate_names=predicate_names,
        predicate_data=predicate_data, params=params, prompt_tuning=prompt_tuning,
        prompt_tuning_name=prompt_tuning_name, default_response=default_response,
        compute=compute), "llm analysis")


def download_concept(ontology_id, path=None, export_csv=False, concept_name=None,
                     dest_path=None):
    """Download a project file, or export a concept to CSV and download it.

    Returns the local path the file was written to.
    """
    return JarvisPyClient.download_concept(
        ontology_id=ontology_id, path=path, export_csv=export_csv,
        concept_name=concept_name, dest_path=dest_path)
