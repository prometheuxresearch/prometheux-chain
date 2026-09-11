# Underscore aliases: every name bound here lands in the package's public
# namespace, which is this SDK's entire API surface.
from importlib.metadata import PackageNotFoundError as _NoDistribution
from importlib.metadata import version as _distribution_version
from pathlib import Path as _Path

try:
    __version__ = _distribution_version("prometheux_chain")
except _NoDistribution:
    # Not installed, so there is no distribution metadata to read — a source
    # checkout being imported directly. Fall back to the file setup.py stamps
    # into that metadata at build time, so both paths report the same number.
    _version_file = _Path(__file__).resolve().parents[1] / "version.txt"
    __version__ = (
        _version_file.read_text(encoding="utf-8").strip()
        if _version_file.is_file()
        else "0.0.0+unknown"
    )

from .config import config

from .data.database import Database

# ── Projects ────────────────────────────────────────────────────────────────
from .ontology.manage_ontologies import cleanup_ontologies
from .ontology.manage_ontologies import save_ontology
from .ontology.manage_ontologies import list_ontologies
from .ontology.manage_ontologies import load_ontology
from .ontology.manage_ontologies import copy_ontology
from .ontology.manage_ontologies import export_ontology
from .ontology.manage_ontologies import import_ontology
from .ontology.manage_ontologies import export_workspace
from .ontology.manage_ontologies import import_workspace
from .ontology.manage_ontologies import list_templates
from .ontology.manage_ontologies import import_template
from .ontology.manage_ontologies import create_ontology_from_context
from .ontology.manage_ontologies import create_snapshot
from .ontology.manage_ontologies import list_snapshots
from .ontology.manage_ontologies import restore_snapshot
from .ontology.manage_ontologies import delete_snapshot

# ── Data ────────────────────────────────────────────────────────────────────
from .data.manage_data import cleanup_sources
from .data.manage_data import connect_sources
from .data.manage_data import list_sources
from .data.manage_data import infer_schema
from .data.manage_data import list_sheets
from .data.manage_data import list_demo_sources
from .data.manage_data import refresh_sources
from .data.manage_data import preview_datasource
from .data.manage_data import all_pairs_join
from .data.manage_data import upload_file
from .data.manage_data import list_files
from .data.manage_data import make_directory
from .data.manage_data import delete_files
from .data.manage_data import move_file
from .data.manage_data import download_file

# ── Concepts ────────────────────────────────────────────────────────────────
from .concept.manage_concepts import cleanup_concepts
from .concept.manage_concepts import list_concepts
from .concept.manage_concepts import run_concept
from .concept.manage_concepts import run_concept_stream
from .concept.manage_concepts import save_concept
from .concept.manage_concepts import rename_concept
from .concept.manage_concepts import reorder_concepts
from .concept.manage_concepts import fetch_results
from .concept.manage_concepts import search_results
from .concept.manage_concepts import query_concept
from .concept.manage_concepts import search_similar_concepts
from .concept.manage_concepts import llm_analysis
from .concept.manage_concepts import download_concept
from .concept.manage_concepts import get_execution_statuses
from .concept.manage_concepts import get_execution_status
from .concept.manage_concepts import generate_concept_description
from .concept.manage_concepts import get_concept_description

# ── Users ───────────────────────────────────────────────────────────────────
from .user.manage_users import save_user_config
from .user.manage_users import load_user_config
from .user.manage_users import get_role
from .user.manage_users import get_login_activity
from .user.manage_users import list_llm_models
from .user.manage_users import get_usage_status

# ── Knowledge Graphs ────────────────────────────────────────────────────────
from .kg.manage_kgs import visualize_concept_lineage
from .kg.manage_kgs import build_graph
from .kg.manage_kgs import list_graph_functions
from .kg.manage_kgs import run_graph_analytics

# ── Auth / tokens ───────────────────────────────────────────────────────────
from .auth.manage_auth import issue_token
from .auth.manage_auth import list_tokens
from .auth.manage_auth import revoke_token
from .auth.manage_auth import revoke_specific_token
from .auth.manage_auth import revoke_all_tokens

# ── Ontology ────────────────────────────────────────────────────────────────
from .ontology_schema.manage_ontology_schema import save_ontology_schema
from .ontology_schema.manage_ontology_schema import load_ontology_schema
from .ontology_schema.manage_ontology_schema import update_concept_ontology_schema_type
from .ontology_schema.manage_ontology_schema import add_to_lineage
from .ontology_schema.manage_ontology_schema import import_owl

# ── Knowledge / Context Layer ───────────────────────────────────────────────
from .knowledge.manage_knowledge import list_context_notes
from .knowledge.manage_knowledge import create_context_note
from .knowledge.manage_knowledge import create_context_notes_from_file
from .knowledge.manage_knowledge import get_context_note
from .knowledge.manage_knowledge import update_context_note
from .knowledge.manage_knowledge import create_context_edge
from .knowledge.manage_knowledge import delete_context_note
from .knowledge.manage_knowledge import search_context_notes
from .knowledge.manage_knowledge import auto_seed
from .knowledge.manage_knowledge import interview_template
from .knowledge.manage_knowledge import submit_interview
from .knowledge.manage_knowledge import onboarding_status
from .knowledge.manage_knowledge import ontology_text

# ── Agent ───────────────────────────────────────────────────────────────────
from .agent.manage_agent import agent_chat
from .agent.manage_agent import agent_reset

# ── Assistant helpers ───────────────────────────────────────────────────────
from .assistant.manage_assistant import list_skills
from .assistant.manage_assistant import get_skill
from .assistant.manage_assistant import get_company_info

# ── Project sharing ─────────────────────────────────────────────────────────
from .share.manage_share import create_share
from .share.manage_share import revoke_share
from .share.manage_share import update_share_role
from .share.manage_share import list_shares
from .share.manage_share import list_inbox
from .share.manage_share import accept_share
from .share.manage_share import leave_share
from .share.manage_share import sync_inbox

# ── Apps ────────────────────────────────────────────────────────────────────
from .app.manage_apps import list_all_apps
from .app.manage_apps import list_apps
from .app.manage_apps import get_app
from .app.manage_apps import save_app
from .app.manage_apps import delete_app
from .app.manage_apps import publish_app
from .app.manage_apps import unpublish_app

# ── Schedules ───────────────────────────────────────────────────────────────
from .schedule.manage_schedules import create_policy
from .schedule.manage_schedules import list_policies
from .schedule.manage_schedules import get_policy
from .schedule.manage_schedules import update_policy
from .schedule.manage_schedules import delete_policy
from .schedule.manage_schedules import trigger_policy
from .schedule.manage_schedules import get_run_history

# ── Alerts ──────────────────────────────────────────────────────────────────
from .alert.manage_alerts import get_alert_history
from .alert.manage_alerts import reprocess_alert

# ── Chat history ────────────────────────────────────────────────────────────
from .chat_history.manage_chat_history import list_sessions
from .chat_history.manage_chat_history import get_session
from .chat_history.manage_chat_history import rename_session
from .chat_history.manage_chat_history import delete_session

# ── Compute ─────────────────────────────────────────────────────────────────
from .compute.manage_compute import check_compute_availability
from .compute.manage_compute import list_machines_combined
from .compute.manage_compute import set_machine_active
from .compute.manage_compute import get_machine_status
from .compute.manage_compute import use_machine
from .compute.manage_compute import delete_user_machine

# ── Vadalog authoring ───────────────────────────────────────────────────────
from .vadalog.manage_vadalog import analyze_program
from .vadalog.manage_vadalog import build_bind
from .vadalog.manage_vadalog import parse_binds
from .vadalog.manage_vadalog import evaluate_program
from .vadalog.manage_vadalog import validate_concept

# ── Vadalingo translation ───────────────────────────────────────────────────
from .vadalingo.manage_vadalingo import translate_sql_to_vadalog
from .vadalingo.manage_vadalingo import translate_rdf_to_vadalog
from .vadalingo.manage_vadalingo import translate_owl_to_vadalog
