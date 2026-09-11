"""
Knowledge / Context Layer Management Module

CRUD + semantic search over context notes, document ingestion, the auto-seed
bootstrap (NDJSON stream), interviews, onboarding status, and project text.

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

from ..client.jarvispy_client import JarvisPyClient

# Sentinel for "argument not supplied" where None is a meaningful value
# (e.g. moving a note to global scope clears scope_id by passing None).
_UNSET = object()


def _check(response, action="operation"):
    """Raise on error, return data on success."""
    if response.get('status') != 'success':
        raise Exception(f"Knowledge {action} failed: {response.get('message', 'Unknown error')}")
    return response.get('data')


# ── Context notes ──────────────────────────────────────────────────────────

def list_context_notes(scope, scope_id=None, kinds=None):
    """List context notes for a scope ('global' or 'project')."""
    return _check(JarvisPyClient.list_context_notes(
        scope=scope, scope_id=scope_id, kinds=kinds,
    ), "list context notes")


def create_context_note(scope, kind, text, scope_id=None, source="user",
                        pinned=False, supersedes=None, activation="retrieved",
                        title=None, folder_path=None):
    """Create a single context note.

    ``activation`` is ``retrieved`` (default), ``always``, or ``on_demand``.
    """
    return _check(JarvisPyClient.create_context_note(
        scope=scope, kind=kind, text=text, scope_id=scope_id, source=source,
        pinned=pinned, supersedes=supersedes, activation=activation,
        title=title, folder_path=folder_path,
    ), "create context note")


def create_context_notes_from_file(file_path, scope="global", scope_id=None):
    """Ingest an already-uploaded disk/ file as context-layer document chunks.

    ``file_path`` is the ``disk/<name>`` path returned by ``upload_file``.
    """
    return _check(JarvisPyClient.create_context_notes_from_file(
        file_path=file_path, scope=scope, scope_id=scope_id,
    ), "create context notes from file")


def get_context_note(note_id):
    """Get a single context note by id."""
    return _check(JarvisPyClient.get_context_note(note_id), "get context note")


def update_context_note(note_id, text=None, kind=None, pinned=None,
                        scope=_UNSET, scope_id=_UNSET, activation=None,
                        title=None, folder_path=_UNSET):
    """Update a context note. Only provided fields are changed.

    To move a note's scope, pass ``scope`` (and ``scope_id``) explicitly;
    passing ``scope_id=None`` clears the project id (global scope).
    """
    kwargs = {'text': text, 'kind': kind, 'pinned': pinned, 'activation': activation,
              'title': title}
    if scope is not _UNSET:
        kwargs['scope'] = scope
    if scope_id is not _UNSET:
        kwargs['scope_id'] = scope_id
    if folder_path is not _UNSET:
        kwargs['folder_path'] = folder_path
    return _check(JarvisPyClient.update_context_note(note_id, **kwargs), "update context note")


def create_context_edge(src_type, src_id, dst_type, dst_id, relation="relates_to",
                        created_by="user"):
    """Create a context-layer edge. Duplicate triples return the existing edge."""
    return _check(JarvisPyClient.create_context_edge(
        src_type=src_type, src_id=src_id, dst_type=dst_type, dst_id=dst_id,
        relation=relation, created_by=created_by,
    ), "create context edge")


def delete_context_note(note_id):
    """Delete a context note by id."""
    response = JarvisPyClient.delete_context_note(note_id)
    if response.get('status') != 'success':
        raise Exception(f"Knowledge delete context note failed: {response.get('message', 'Unknown error')}")


def search_context_notes(query, scope, scope_id=None, kinds=None, top_k=10):
    """Semantic search over context notes."""
    return _check(JarvisPyClient.search_context_notes(
        query=query, scope=scope, scope_id=scope_id, kinds=kinds, top_k=top_k,
    ), "search context notes")


# ── Auto-seed (NDJSON stream) ──────────────────────────────────────────────

def auto_seed(scope="project", scope_id=None, datasource_ids=None):
    """Profile connected data sources and write observation notes.

    Returns a generator yielding NDJSON progress events.
    """
    return JarvisPyClient.auto_seed(scope=scope, scope_id=scope_id, datasource_ids=datasource_ids)


# ── Interview ──────────────────────────────────────────────────────────────

def interview_template(scope="global"):
    """Return the static interview question template for the given scope."""
    return _check(JarvisPyClient.interview_template(scope=scope), "interview template")


def submit_interview(scope, answers, scope_id=None):
    """Persist completed interview answers as context notes."""
    return _check(JarvisPyClient.submit_interview(
        scope=scope, answers=answers, scope_id=scope_id,
    ), "submit interview")


# ── Status / document view ─────────────────────────────────────────────────

def onboarding_status():
    """Return whether the workspace looks empty enough to warrant onboarding."""
    return _check(JarvisPyClient.onboarding_status(), "onboarding status")


def ontology_text(ontology_id, refresh=False):
    """Return the Document view payload (summary + rendered Vadalog) for a project."""
    return _check(JarvisPyClient.ontology_text(
        ontology_id=ontology_id, refresh=refresh,
    ), "project text")
