"""
Project Management Module

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

from ..client.jarvispy_client import JarvisPyClient


def _check(response, action="operation"):
    """Raise on error, return data on success."""
    if response.get('status') != 'success':
        raise Exception(f"Project {action} failed: {response.get('message', 'Unknown error')}")
    return response.get('data')


def save_ontology(ontology_id=None, ontology_name=None, description=None):
    """Save or create a project."""
    data = _check(JarvisPyClient.save_ontology(
        ontology_id=ontology_id, ontology_name=ontology_name, description=description), "save")
    # The save endpoint returns the (server-generated on create) id under
    # 'ontology_id'; older servers used 'project_id'. Read either so a create
    # never silently yields None (which downstream turns into concepts_None).
    if isinstance(data, dict):
        return data.get('ontology_id') or data.get('project_id')
    return data


def list_ontologies():
    """List all projects."""
    return _check(JarvisPyClient.list_ontologies(), "list")


def load_ontology(ontology_id):
    """Load a project by ID."""
    return _check(JarvisPyClient.load_ontology(ontology_id=ontology_id), "load")


def cleanup_ontologies(ontology_id=None):
    """Delete a project and its resources."""
    response = JarvisPyClient.cleanup_ontologies(ontology_id=ontology_id)
    if response.get('status') != 'success':
        raise Exception(f"Project cleanup failed: {response.get('message', 'Unknown error')}")


def copy_ontology(ontology_id, new_ontology_name=None, compute=None):
    """Copy a project."""
    return _check(JarvisPyClient.copy_ontology(
        ontology_id=ontology_id, new_ontology_name=new_ontology_name, compute=compute), "copy")


def export_tree(ontology_id, slug=None):
    """Export a project as a file tree: ``{"ontology", "files", "warnings"}``.

    ``files`` is a list of ``{"path", "content"}`` — the same tree the app's
    Export downloads as a .zip. ``slug`` names the directory under ``ontologies/``.
    """
    return _check(JarvisPyClient.export_tree(ontology_id=ontology_id, slug=slug), "export tree")


def export_ontology(ontology_id=None):
    """Export a single project."""
    return _check(JarvisPyClient.export_ontology(ontology_id=ontology_id), "export")


def import_ontology(export_data, force_new_id=False, compute=None):
    """Import a project from exported data."""
    if not export_data or not isinstance(export_data, dict):
        raise ValueError("export_data must be a non-empty dictionary")
    return _check(JarvisPyClient.import_ontology(
        export_data=export_data, force_new_id=force_new_id, compute=compute), "import")


def export_workspace():
    """Export the entire workspace."""
    return _check(JarvisPyClient.export_workspace(), "workspace export")


def import_workspace(export_data):
    """Import an entire workspace from exported data."""
    if not export_data or not isinstance(export_data, dict):
        raise ValueError("export_data must be a non-empty dictionary")
    return _check(JarvisPyClient.import_workspace(export_data=export_data), "workspace import")


# ── Templates ─────────────────────────────────────────────────────────────

def list_templates():
    """List the available project templates from the marketplace."""
    return _check(JarvisPyClient.list_templates(), "list templates")


def import_template(template_id, new_ontology_name=None, compute=None):
    """Create a new project from a marketplace template."""
    return _check(JarvisPyClient.import_template(
        template_id=template_id, new_ontology_name=new_ontology_name, compute=compute), "import template")


def create_ontology_from_context(context, concept_names=None, file_paths=None):
    """Create a project from free-text context and optional file attachments.

    ``file_paths`` is a list of local file paths to upload alongside the context.
    """
    return _check(JarvisPyClient.create_ontology_from_context(
        context=context, concept_names=concept_names, file_paths=file_paths), "create from context")


# ── Snapshots (versioning) ─────────────────────────────────────────────────

def create_snapshot(ontology_id, description=None):
    """Create a point-in-time snapshot of a project."""
    return _check(JarvisPyClient.create_snapshot(
        ontology_id=ontology_id, description=description), "create snapshot")


def list_snapshots(ontology_id):
    """List all snapshots for a project (metadata only)."""
    return _check(JarvisPyClient.list_snapshots(ontology_id=ontology_id), "list snapshots")


def restore_snapshot(snapshot_id, ontology_id, create_safety_snapshot=True):
    """Restore a project from a previously saved snapshot."""
    return _check(JarvisPyClient.restore_snapshot(
        snapshot_id=snapshot_id, ontology_id=ontology_id,
        create_safety_snapshot=create_safety_snapshot), "restore snapshot")


def delete_snapshot(snapshot_id, ontology_id):
    """Delete a single snapshot."""
    response = JarvisPyClient.delete_snapshot(snapshot_id=snapshot_id, ontology_id=ontology_id)
    if response.get('status') != 'success':
        raise Exception(f"Project delete snapshot failed: {response.get('message', 'Unknown error')}")
