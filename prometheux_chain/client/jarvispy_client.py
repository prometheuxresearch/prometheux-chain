"""
JarvisPy Client Module

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

import json
import json as _json
import os
import re
from urllib.parse import quote, urlencode

import requests

from ..config import config
from ..data.database import Database

# Sentinel for "argument not supplied" where None is a meaningful value.
_UNSET = object()


def _resolve_user_agent():
    """Build the SDK's User-Agent once at import.

    Sent on every request so the backend can distinguish programmatic
    (CLI / SDK) callers from the browser frontend in usage analytics. Reads
    ``version.txt`` from the repo root when present (editable installs); falls
    back to ``unknown`` in wheels that don't ship it.
    """
    version = "unknown"
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        for cand in (
            os.path.join(here, "..", "..", "version.txt"),
            os.path.join(here, "..", "version.txt"),
        ):
            if os.path.exists(cand):
                with open(cand) as fh:
                    version = fh.read().strip() or version
                break
    except Exception:
        pass
    return f"prometheux-chain/{version}"


_USER_AGENT = _resolve_user_agent()


class JarvisPyClient:

    @staticmethod
    def _get_auth():
        pmtx_token = os.environ.get('PMTX_TOKEN', config.get('PMTX_TOKEN', ''))
        if not pmtx_token:
            raise Exception("PMTX_TOKEN is not set. Please set it in environment variables or config.")
        return pmtx_token

    @staticmethod
    def _get_supabase_token():
        """Optional Supabase token, needed by recipient-side share flows and a
        few other endpoints. Returns None when not configured."""
        return os.environ.get('SUPABASE_TOKEN', config.get('SUPABASE_TOKEN', '')) or None

    @staticmethod
    def _headers(pmtx_token, content_type='application/json'):
        headers = {'Authorization': f"Bearer {pmtx_token}", 'User-Agent': _USER_AGENT}
        if content_type:
            headers['Content-Type'] = content_type
        supabase_token = JarvisPyClient._get_supabase_token()
        if supabase_token:
            headers['X-Supabase-Token'] = supabase_token
        return headers

    # Default network timeouts (seconds). ``connect`` fails fast on an
    # unreachable/half-open backend; ``read`` is generous to accommodate
    # long-running engine/LLM operations. Both are overridable via config
    # (``JARVISPY_CONNECT_TIMEOUT`` / ``JARVISPY_READ_TIMEOUT``) or the
    # same-named environment variables.
    _DEFAULT_CONNECT_TIMEOUT = 10.0
    _DEFAULT_READ_TIMEOUT = 300.0

    @staticmethod
    def _timeout():
        """Return a ``(connect, read)`` timeout tuple for requests calls.

        Always returns finite values so no call can hang indefinitely.
        """
        def _as_float(value, fallback):
            try:
                parsed = float(value)
                return parsed if parsed > 0 else fallback
            except (TypeError, ValueError):
                return fallback

        connect = _as_float(config.get('JARVISPY_CONNECT_TIMEOUT'),
                            JarvisPyClient._DEFAULT_CONNECT_TIMEOUT)
        read = _as_float(config.get('JARVISPY_READ_TIMEOUT'),
                        JarvisPyClient._DEFAULT_READ_TIMEOUT)
        return (connect, read)

    @staticmethod
    def _send(method, url, **kwargs):
        """Issue a requests call with a guaranteed timeout and friendly errors."""
        kwargs.setdefault('timeout', JarvisPyClient._timeout())
        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.Timeout as exc:
            read_timeout = kwargs['timeout'][1] if isinstance(kwargs['timeout'], tuple) else kwargs['timeout']
            raise Exception(
                f"Request to {url} timed out after {read_timeout}s. "
                "The backend may be slow or unresponsive."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise Exception(
                f"Could not connect to JarvisPy backend at {config.get('JARVISPY_URL')}. "
                "Check that it is running and JARVISPY_URL is correct."
            ) from exc

    @staticmethod
    def _safe_filename(name):
        """Sanitize a server-supplied filename to a bare basename.

        Strips any directory components (including ``..``) so a malicious or
        buggy server response can never cause a write outside the intended
        directory. Only applied to server-derived names — an explicit
        ``dest_path`` from the caller is always honored verbatim.
        """
        candidate = os.path.basename((name or "").replace('\\', '/').split('/')[-1])
        if not candidate or candidate in ('.', '..'):
            return "download"
        return candidate

    @staticmethod
    def _request(method, path, json=None, params=None):
        """Send an authenticated request to the JarvisPy backend."""
        pmtx_token = JarvisPyClient._get_auth()
        url = f"{config['JARVISPY_URL']}{path}"
        headers = JarvisPyClient._headers(pmtx_token)
        response = JarvisPyClient._send(method, url, headers=headers, json=json, params=params)
        return JarvisPyClient._handle_response(response)

    @staticmethod
    def _request_multipart(method, path, files, data=None, params=None):
        """Send an authenticated multipart/form-data request (file uploads)."""
        pmtx_token = JarvisPyClient._get_auth()
        url = f"{config['JARVISPY_URL']}{path}"
        headers = JarvisPyClient._headers(pmtx_token, content_type=None)
        response = JarvisPyClient._send(method, url, headers=headers, files=files, data=data, params=params)
        return JarvisPyClient._handle_response(response)

    @staticmethod
    def _request_stream(method, path, json=None, params=None):
        """Generator yielding parsed NDJSON objects from a streaming endpoint."""
        pmtx_token = JarvisPyClient._get_auth()
        url = f"{config['JARVISPY_URL']}{path}"
        headers = JarvisPyClient._headers(pmtx_token)
        with JarvisPyClient._send(method, url, headers=headers, json=json, params=params, stream=True) as response:
            if response.status_code >= 400:
                JarvisPyClient._handle_response(response)
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        yield _json.loads(line)
                    except ValueError:
                        yield {"type": "raw", "data": line}
            except (requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ConnectionError) as exc:
                # A stalled or dropped stream must surface as a terminal event,
                # never an unbounded hang or an unhandled raw exception.
                yield {"type": "error", "data": {"status": "error", "message": str(exc)}}

    @staticmethod
    def _request_download(method, path, params=None, dest_path=None):
        """Stream a binary file response to disk and return the local path."""
        pmtx_token = JarvisPyClient._get_auth()
        url = f"{config['JARVISPY_URL']}{path}"
        headers = JarvisPyClient._headers(pmtx_token)
        with JarvisPyClient._send(method, url, headers=headers, params=params, stream=True) as response:
            if response.status_code >= 400:
                JarvisPyClient._handle_response(response)
            if dest_path is None:
                filename = None
                disposition = response.headers.get('Content-Disposition', '')
                match = re.search(r'filename="?([^";]+)"?', disposition)
                if match:
                    filename = match.group(1)
                if not filename:
                    filename = path.split('?')[0]
                # The filename is server-controlled here; sanitize to a bare
                # basename so it cannot escape the current directory.
                dest_path = JarvisPyClient._safe_filename(filename)
            with open(dest_path, 'wb') as out_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        out_file.write(chunk)
        return dest_path

    @staticmethod
    def _websocket(path, init_payload=None, params=None):
        """Generator yielding parsed messages from a WebSocket endpoint.

        Auth is passed as query params (``token`` and optional
        ``x_supabase_token``). The single ``init_payload`` is sent once after
        connecting. Iteration stops after a ``complete`` or ``error`` event.
        """
        try:
            from websocket import create_connection
            try:
                from websocket import WebSocketTimeoutException
            except ImportError:
                class WebSocketTimeoutException(Exception):
                    """Fallback when websocket-client doesn't export the type."""
        except ImportError as exc:
            raise Exception(
                "WebSocket support requires 'websocket-client'. "
                "Install it with: pip install websocket-client"
            ) from exc

        pmtx_token = JarvisPyClient._get_auth()
        base = config['JARVISPY_URL']
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        else:
            ws_base = base

        query = dict(params or {})
        query['token'] = pmtx_token
        supabase_token = JarvisPyClient._get_supabase_token()
        if supabase_token:
            query['x_supabase_token'] = supabase_token

        url = f"{ws_base}{path}?{urlencode(query)}"
        # Bound both the handshake and per-message waits so a hung or silent
        # server can never block the caller forever. The backend sends a
        # heartbeat ping every ~20s, so a recv timeout comfortably above that
        # only fires on a genuinely dead connection.
        connect_timeout = JarvisPyClient._timeout()[0]

        def _as_float(value, fallback):
            try:
                parsed = float(value)
                return parsed if parsed > 0 else fallback
            except (TypeError, ValueError):
                return fallback

        recv_timeout = _as_float(config.get('JARVISPY_WS_TIMEOUT'), 60.0)
        connection = create_connection(url, timeout=connect_timeout)
        connection.settimeout(recv_timeout)
        try:
            connection.send(_json.dumps(init_payload or {}))
            while True:
                try:
                    raw = connection.recv()
                except WebSocketTimeoutException as exc:
                    yield {
                        "event": "error",
                        "data": {
                            "status": "error",
                            "message": (
                                f"WebSocket timed out after {recv_timeout}s with no "
                                "message from the server (a heartbeat is expected "
                                "every ~20s); the connection appears dead."
                            ),
                        },
                    }
                    break
                except Exception:
                    break
                if not raw:
                    continue
                try:
                    message = _json.loads(raw)
                except ValueError:
                    continue
                if message.get("event") == "ping":
                    continue
                yield message
                if message.get("event") in ("complete", "error"):
                    break
        finally:
            try:
                connection.close()
            except Exception:
                pass

    @staticmethod
    def _handle_response(response):
        if response.status_code == 401:
            raise Exception("Unauthorized: Invalid or expired token. Please check your PMTX_TOKEN.")
        elif response.status_code == 403:
            raise Exception("Forbidden: You don't have permission to perform this action.")
        elif response.status_code == 404:
            raise Exception("Not Found: The requested resource was not found.")
        elif response.status_code >= 400:
            raise Exception(f"HTTP Error {response.status_code}: {response.text}")
        try:
            return response.json()
        except ValueError:
            raise Exception(f"Invalid JSON response from server: {response.text}")

    # ── Projects ──────────────────────────────────────────────────────────

    @staticmethod
    def save_ontology(ontology_id, ontology_name, description=None):
        payload = {'project': {'id': ontology_id, 'name': ontology_name}}
        if description is not None:
            payload['project']['description'] = description
        return JarvisPyClient._request("POST", "/api/v1/ontologies/save", json=payload)

    @staticmethod
    def list_ontologies():
        return JarvisPyClient._request("GET", "/api/v1/ontologies/list")

    @staticmethod
    def load_ontology(ontology_id):
        return JarvisPyClient._request("GET", "/api/v1/ontologies/load",
                                       params={'project_id': ontology_id})

    @staticmethod
    def cleanup_ontologies(ontology_id):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/cleanup",
                                       json={'project': {'id': ontology_id}})

    @staticmethod
    def copy_ontology(ontology_id, new_ontology_name=None, compute=None):
        payload = {'project_id': ontology_id, 'new_project_name': new_ontology_name}
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", "/api/v1/ontologies/copy", json=payload)

    @staticmethod
    def export_ontology(ontology_id):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/export-ontology",
                                       json={'project_id': ontology_id})

    @staticmethod
    def import_ontology(export_data, force_new_id=False, compute=None):
        payload = {'export_data': export_data, 'force_new_id': force_new_id}
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", "/api/v1/ontologies/import-ontology", json=payload)

    @staticmethod
    def export_workspace():
        return JarvisPyClient._request("POST", "/api/v1/ontologies/export-workspace", json={})

    @staticmethod
    def import_workspace(export_data):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/import-workspace",
                                       json={'export_data': export_data})

    @staticmethod
    def list_templates():
        return JarvisPyClient._request("GET", "/api/v1/ontologies/list-templates")

    @staticmethod
    def import_template(template_id, new_ontology_name=None, compute=None):
        payload = {'template_id': template_id}
        if new_ontology_name is not None:
            payload['new_project_name'] = new_ontology_name
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", "/api/v1/ontologies/import-template", json=payload)

    @staticmethod
    def create_ontology_from_context(context, concept_names=None, file_paths=None):
        data = {
            'context': context or "",
            'concept_names': json.dumps(concept_names or []),
        }
        opened_files = []
        files = []
        try:
            for file_path in (file_paths or []):
                file_obj = open(file_path, 'rb')
                opened_files.append(file_obj)
                files.append(('files', (os.path.basename(file_path), file_obj)))
            return JarvisPyClient._request_multipart(
                "POST", "/api/v1/ontologies/create-from-context",
                files=files or None, data=data)
        finally:
            for file_obj in opened_files:
                file_obj.close()

    @staticmethod
    def create_snapshot(ontology_id, description=None):
        payload = {'project_id': ontology_id}
        if description is not None:
            payload['description'] = description
        return JarvisPyClient._request("POST", "/api/v1/ontologies/snapshots/create", json=payload)

    @staticmethod
    def list_snapshots(ontology_id):
        return JarvisPyClient._request("GET", "/api/v1/ontologies/snapshots/list",
                                       params={'project_id': ontology_id})

    @staticmethod
    def restore_snapshot(snapshot_id, ontology_id, create_safety_snapshot=True):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/snapshots/restore",
                                       json={'snapshot_id': snapshot_id, 'project_id': ontology_id,
                                             'create_safety_snapshot': create_safety_snapshot})

    @staticmethod
    def delete_snapshot(snapshot_id, ontology_id):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/snapshots/delete",
                                       json={'snapshot_id': snapshot_id, 'project_id': ontology_id})

    # ── Data sources ──────────────────────────────────────────────────────

    @staticmethod
    def cleanup_sources(source_ids=None):
        return JarvisPyClient._request("POST", "/api/v1/data/cleanup",
                                       json={'source_ids': source_ids})

    @staticmethod
    def connect_sources(database_payload: Database, compute_row_count=False):
        return JarvisPyClient._request("POST", "/api/v1/data/connect",
                                       json={'database': database_payload.to_dict(),
                                             'computeRowCount': compute_row_count})

    @staticmethod
    def list_sources():
        return JarvisPyClient._request("GET", "/api/v1/data/list")

    @staticmethod
    def infer_schema(database: Database, add_bind: bool, add_model: bool):
        return JarvisPyClient._request("POST", "/api/v1/data/infer-schema",
                                       json={'database': database.to_dict(),
                                             'addBind': add_bind, 'addModel': add_model})

    @staticmethod
    def list_sheets(database: Database):
        return JarvisPyClient._request("POST", "/api/v1/data/list-sheets",
                                       json={'database': database.to_dict()})

    @staticmethod
    def list_demo_sources():
        return JarvisPyClient._request("GET", "/api/v1/data/demo-sources")

    @staticmethod
    def refresh_sources(group_filter=None):
        return JarvisPyClient._request("POST", "/api/v1/data/refresh",
                                       json={'group_filter': group_filter})

    @staticmethod
    def preview_datasource(bind_annotation, limit=10, page=1, page_size=0,
                           order_by=None, search_term=None, column_filters=None, compute=None):
        payload = {
            'bind_annotation': bind_annotation,
            'limit': limit,
            'page': page,
            'page_size': page_size,
        }
        if order_by is not None:
            payload['order_by'] = order_by
        if search_term is not None:
            payload['search_term'] = search_term
        if column_filters is not None:
            payload['column_filters'] = column_filters
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", "/api/v1/data/preview", json=payload)

    @staticmethod
    def all_pairs_join(database_payloads, to_evaluate=False, parallel=True):
        payload = {
            'database_payloads': [
                db.to_dict() if isinstance(db, Database) else db for db in database_payloads
            ],
            'to_evaluate': to_evaluate,
            'parallel': parallel,
        }
        return JarvisPyClient._request("POST", "/api/v1/data/all-pairs-join", json=payload)

    @staticmethod
    def upload_file(file_path, path=""):
        with open(file_path, 'rb') as file_obj:
            files = {'file': (os.path.basename(file_path), file_obj)}
            return JarvisPyClient._request_multipart(
                "POST", "/api/v1/data/files/upload", files=files, data={'path': path},
            )

    @staticmethod
    def list_files(path=""):
        return JarvisPyClient._request("GET", "/api/v1/data/files/list", params={'path': path})

    @staticmethod
    def make_directory(path):
        return JarvisPyClient._request("POST", "/api/v1/data/files/mkdir", json={'path': path})

    @staticmethod
    def delete_files(paths, recursive=False):
        return JarvisPyClient._request("POST", "/api/v1/data/files/delete",
                                       json={'paths': paths, 'recursive': recursive})

    @staticmethod
    def move_file(source, destination):
        return JarvisPyClient._request("POST", "/api/v1/data/files/move",
                                       json={'source': source, 'destination': destination})

    @staticmethod
    def download_file(path, dest_path=None):
        return JarvisPyClient._request_download("GET", "/api/v1/data/files/download",
                                                params={'path': path}, dest_path=dest_path)

    # ── Concepts ──────────────────────────────────────────────────────────

    @staticmethod
    def save_concept(ontology_id, definition, python_scripts=None,
                     description=None, concept_type="logic", concept_name=None,
                     binds=None, output_predicate="", existing_name=None,
                     position=None, group="group_id", compute=None, force_overwrite=False,
                     concept_config=None):
        payload = {'definition': definition, 'concept_type': concept_type}
        if python_scripts:
            payload['python_scripts'] = python_scripts
        if description:
            payload['description'] = description
        if concept_name:
            payload['concept_name'] = concept_name
        if binds:
            payload['binds'] = binds
        if output_predicate:
            payload['output_predicate'] = output_predicate
        if existing_name:
            payload['existing_name'] = existing_name
        if position is not None:
            payload['position'] = position
        if group and group != "group_id":
            payload['group'] = group
        if compute:
            payload['compute'] = compute
        if force_overwrite:
            payload['force_overwrite'] = force_overwrite
        if concept_config is not None:
            payload['concept_config'] = concept_config
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/save", json=payload)

    @staticmethod
    def rename_concept(ontology_id, old_name, new_name):
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/rename",
                                       json={'old_name': old_name, 'new_name': new_name})

    @staticmethod
    def run_concept(ontology_id, concept_name, params=None,
                    force_rerun=True, persist_outputs=False, compute=None):
        payload = {
            'params': params or {},
            'force_rerun': force_rerun,
            'persist_outputs': persist_outputs,
        }
        if compute:
            payload['compute'] = compute
        safe_name = quote(concept_name, safe='')
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/run/{safe_name}",
                                       json=payload)

    @staticmethod
    def run_concept_stream(ontology_id, concept_name, params=None,
                           force_rerun=True, persist_outputs=False, compute=None):
        payload = {
            'params': params or {},
            'force_rerun': force_rerun,
            'persist_outputs': persist_outputs,
        }
        if compute:
            payload['compute'] = compute
        safe_name = quote(concept_name, safe='')
        return JarvisPyClient._websocket(
            f"/api/v1/concepts/{ontology_id}/run-stream/{safe_name}", init_payload=payload)

    @staticmethod
    def list_concepts(ontology_id):
        return JarvisPyClient._request("GET", f"/api/v1/concepts/{ontology_id}/list")

    @staticmethod
    def cleanup_concepts(ontology_id, concept_names=None):
        payload = {}
        if concept_names:
            payload['concept_names'] = concept_names
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/cleanup", json=payload)

    @staticmethod
    def reorder_concepts(ontology_id, concept_names, group=None):
        payload = {'concept_names': concept_names}
        if group is not None:
            payload['group'] = group
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/reorder", json=payload)

    @staticmethod
    def get_execution_statuses():
        return JarvisPyClient._request("GET", "/api/v1/concepts/execution-statuses")

    @staticmethod
    def get_execution_status(ontology_id):
        return JarvisPyClient._request("GET", f"/api/v1/concepts/{ontology_id}/execution-status")

    @staticmethod
    def generate_concept_description(ontology_id, concept_name):
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/generate-description",
                                       json={'concept_name': concept_name})

    @staticmethod
    def get_concept_description(ontology_id, concept_name):
        return JarvisPyClient._request("GET", f"/api/v1/concepts/{ontology_id}/description",
                                       params={'concept_name': concept_name})

    @staticmethod
    def fetch_results(ontology_id, output_predicate, page=1, page_size=10,
                      order_by=None, params=None, compute=None,
                      search_term=None, column_filters=None, total_count=None):
        query = {
            'output_predicate': output_predicate,
        }
        body = {
            'page': page,
            'page_size': page_size,
        }
        if order_by:
            body['order_by'] = order_by
        if params:
            body['params'] = params
        if compute:
            body['compute'] = compute
        if search_term is not None:
            body['search_term'] = search_term
        if column_filters is not None:
            body['column_filters'] = column_filters
        if total_count is not None:
            body['total_count'] = total_count
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/fetch",
                                       json=body, params=query)

    @staticmethod
    def search_results(ontology_id, output_predicate, search_term=None, column_filters=None,
                       page=1, page_size=0, order_by=None, compute=None):
        """Search a populated predicate. Same route as ``fetch_results`` — search
        was folded into ``POST /concepts/{id}/fetch``."""
        return JarvisPyClient.fetch_results(
            ontology_id, output_predicate, page=page, page_size=page_size,
            order_by=order_by, compute=compute,
            search_term=search_term, column_filters=column_filters,
        )

    @staticmethod
    def query_concept(ontology_id, concept_name, sql, compute=None):
        payload = {'concept_name': concept_name, 'sql': sql}
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/query",
                                       json=payload)

    @staticmethod
    def search_similar_concepts(query, top_k=0, exclude_ontology_id=None):
        params = {'query': query, 'top_k': top_k}
        if exclude_ontology_id:
            params['exclude_project_id'] = exclude_ontology_id
        return JarvisPyClient._request("GET", "/api/v1/concepts/search-similar", params=params)

    @staticmethod
    def llm_analysis(ontology_id, question, predicate_names=None, predicate_data=None,
                     params=None, prompt_tuning=None, prompt_tuning_name=None,
                     default_response=None, compute=None):
        payload = {'question': question}
        if predicate_names is not None:
            payload['predicate_names'] = predicate_names
        if predicate_data is not None:
            payload['predicate_data'] = predicate_data
        if params is not None:
            payload['params'] = params
        if prompt_tuning is not None:
            payload['prompt_tuning'] = prompt_tuning
        if prompt_tuning_name is not None:
            payload['prompt_tuning_name'] = prompt_tuning_name
        if default_response is not None:
            payload['default_response'] = default_response
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/llm", json=payload)

    @staticmethod
    def download_concept(ontology_id, path=None, export_csv=False, concept_name=None,
                         dest_path=None):
        params = {}
        if export_csv:
            params['export_csv'] = 'true'
            params['concept_name'] = concept_name
            params['path'] = path or ""
        else:
            params['path'] = path
        return JarvisPyClient._request_download("GET", f"/api/v1/concepts/{ontology_id}/download",
                                                params=params, dest_path=dest_path)

    # ── Ontology Schema ───────────────────────────────────────────────────

    @staticmethod
    def save_ontology_schema(ontology_id, ontology_schema_data):
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/save-ontology-schema",
                                       json={'ontology_schema_data': ontology_schema_data})

    @staticmethod
    def load_ontology_schema(ontology_id):
        return JarvisPyClient._request("GET", f"/api/v1/concepts/{ontology_id}/load-ontology-schema")

    @staticmethod
    def update_concept_ontology_schema_type(ontology_id, concept_name, ontology_schema_type=None,
                                            edge_source=None, edge_target=None):
        safe_name = quote(concept_name, safe='')
        payload = {'ontology_schema_type': ontology_schema_type}
        if edge_source is not None:
            payload['edge_source'] = edge_source
        if edge_target is not None:
            payload['edge_target'] = edge_target
        return JarvisPyClient._request(
            "PATCH", f"/api/v1/concepts/{ontology_id}/concepts/{safe_name}/ontology-schema-type", json=payload)

    @staticmethod
    def add_to_lineage(ontology_id, element_type, element_data, all_nodes=None):
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/add-to-lineage",
                                       json={'element_type': element_type, 'element_data': element_data,
                                             'all_nodes': all_nodes or []})

    @staticmethod
    def import_owl(ontology_id, owl_content, base_namespace=None):
        payload = {'owl_content': owl_content}
        if base_namespace is not None:
            payload['base_namespace'] = base_namespace
        return JarvisPyClient._request("POST", f"/api/v1/concepts/{ontology_id}/import-owl", json=payload)

    # ── Knowledge Graphs ──────────────────────────────────────────────────

    @staticmethod
    def visualize_concept_lineage(ontology_id):
        return JarvisPyClient._request("POST", f"/api/v1/kgs/{ontology_id}/visualize-concept-lineage",
                                       json={})

    @staticmethod
    def build_graph(ontology_id, output_predicate, column_roles, page=1,
                    page_size=0, order_by=None, pagination_mode="records", max_depth=50,
                    source_node=None, target_node=None, recompute=False, compute=None):
        safe_predicate = quote(output_predicate, safe='')
        query = {
            'page': page,
            'page_size': page_size,
            'pagination_mode': pagination_mode,
            'max_depth': max_depth,
            'recompute': recompute,
        }
        if order_by:
            query['order_by'] = order_by
        if source_node is not None:
            query['source_node'] = source_node
        if target_node is not None:
            query['target_node'] = target_node
        body = {'column_roles': column_roles}
        if compute:
            body['compute'] = compute
        return JarvisPyClient._request("POST", f"/api/v1/kgs/{ontology_id}/build-graph/{safe_predicate}",
                                       json=body, params=query)

    @staticmethod
    def list_graph_functions():
        return JarvisPyClient._request("GET", "/api/v1/kgs/graph-functions")

    @staticmethod
    def run_graph_analytics(ontology_id, output_predicate, column_roles, function,
                            function_params=None, compute=None):
        safe_predicate = quote(output_predicate, safe='')
        body = {'column_roles': column_roles, 'function': function}
        if function_params is not None:
            body['function_params'] = function_params
        if compute:
            body['compute'] = compute
        return JarvisPyClient._request(
            "POST", f"/api/v1/kgs/{ontology_id}/graph-analytics/{safe_predicate}", json=body)

    # ── User config / account ─────────────────────────────────────────────

    @staticmethod
    def save_user_config(config_data):
        return JarvisPyClient._request("POST", "/api/v1/users/save-config",
                                       json={'config_data': config_data})

    @staticmethod
    def load_user_config():
        return JarvisPyClient._request("GET", "/api/v1/users/load-config")

    @staticmethod
    def get_role():
        return JarvisPyClient._request("GET", "/api/v1/users/get-role")

    @staticmethod
    def get_login_activity():
        return JarvisPyClient._request("GET", "/api/v1/users/login-activity")

    @staticmethod
    def list_llm_models(provider, credentials=None):
        payload = {'provider': provider}
        if credentials:
            payload.update(credentials)
        return JarvisPyClient._request("POST", "/api/v1/users/llm-models", json=payload)

    @staticmethod
    def get_usage_status():
        return JarvisPyClient._request("GET", "/api/v1/users/usage-status")

    # ── Auth / tokens ─────────────────────────────────────────────────────

    @staticmethod
    def issue_token(name=None, expires_in_minutes=None):
        payload = {}
        if name is not None:
            payload['name'] = name
        if expires_in_minutes is not None:
            payload['expires_in_minutes'] = expires_in_minutes
        return JarvisPyClient._request("POST", "/api/v1/auth/issue-token", json=payload)

    @staticmethod
    def list_tokens():
        return JarvisPyClient._request("GET", "/api/v1/auth/tokens")

    @staticmethod
    def revoke_token():
        return JarvisPyClient._request("POST", "/api/v1/auth/revoke")

    @staticmethod
    def revoke_specific_token(jti):
        safe_jti = quote(jti, safe='')
        return JarvisPyClient._request("POST", f"/api/v1/auth/revoke/{safe_jti}")

    @staticmethod
    def revoke_all_tokens():
        return JarvisPyClient._request("POST", "/api/v1/auth/revoke-all")

    # ── Knowledge / Context Layer ─────────────────────────────────────────

    @staticmethod
    def list_context_notes(scope, scope_id=None, kinds=None):
        params = {'scope': scope}
        if scope_id is not None:
            params['scope_id'] = scope_id
        if kinds:
            params['kinds'] = ','.join(kinds) if isinstance(kinds, (list, tuple)) else kinds
        return JarvisPyClient._request("GET", "/api/v1/knowledge/context", params=params)

    @staticmethod
    def create_context_note(scope, kind, text, scope_id=None, source="user",
                            pinned=False, supersedes=None, activation="retrieved",
                            title=None, folder_path=None):
        payload = {
            'scope': scope,
            'scope_id': scope_id,
            'kind': kind,
            'text': text,
            'source': source,
            'pinned': pinned,
            'activation': activation,
        }
        if supersedes is not None:
            payload['supersedes'] = supersedes
        if title is not None:
            payload['title'] = title
        if folder_path is not None:
            payload['folder_path'] = folder_path
        return JarvisPyClient._request("POST", "/api/v1/knowledge/context", json=payload)

    @staticmethod
    def create_context_notes_from_file(file_path, scope="global", scope_id=None):
        payload = {'scope': scope, 'file_path': file_path}
        if scope_id is not None:
            payload['scope_id'] = scope_id
        return JarvisPyClient._request("POST", "/api/v1/knowledge/context/from-file", json=payload)

    @staticmethod
    def get_context_note(note_id):
        return JarvisPyClient._request("GET", f"/api/v1/knowledge/context/{quote(note_id, safe='')}")

    @staticmethod
    def update_context_note(note_id, text=None, kind=None, pinned=None,
                            scope=_UNSET, scope_id=_UNSET, activation=None,
                            title=None, folder_path=_UNSET):
        payload = {'text': text, 'kind': kind, 'pinned': pinned}
        if scope is not _UNSET:
            payload['scope'] = scope
        if scope_id is not _UNSET:
            payload['scope_id'] = scope_id
        if activation is not None:
            payload['activation'] = activation
        if title is not None:
            payload['title'] = title
        if folder_path is not _UNSET:
            payload['folder_path'] = folder_path
        return JarvisPyClient._request("PATCH", f"/api/v1/knowledge/context/{quote(note_id, safe='')}",
                                       json=payload)

    @staticmethod
    def create_context_edge(src_type, src_id, dst_type, dst_id, relation="relates_to",
                            created_by="user"):
        return JarvisPyClient._request("POST", "/api/v1/knowledge/context/edges", json={
            'src_type': src_type, 'src_id': src_id, 'dst_type': dst_type, 'dst_id': dst_id,
            'relation': relation, 'created_by': created_by,
        })

    @staticmethod
    def delete_context_note(note_id):
        return JarvisPyClient._request("DELETE", f"/api/v1/knowledge/context/{quote(note_id, safe='')}")

    @staticmethod
    def auto_seed(scope="project", scope_id=None, datasource_ids=None):
        payload = {'scope': scope}
        if scope_id is not None:
            payload['scope_id'] = scope_id
        if datasource_ids is not None:
            payload['datasource_ids'] = datasource_ids
        return JarvisPyClient._request_stream("POST", "/api/v1/knowledge/auto-seed", json=payload)

    @staticmethod
    def interview_template(scope="global"):
        return JarvisPyClient._request("GET", "/api/v1/knowledge/interview/template",
                                       params={'scope': scope})

    @staticmethod
    def submit_interview(scope, answers, scope_id=None):
        payload = {'scope': scope, 'answers': answers}
        if scope_id is not None:
            payload['scope_id'] = scope_id
        return JarvisPyClient._request("POST", "/api/v1/knowledge/interview", json=payload)

    @staticmethod
    def onboarding_status():
        return JarvisPyClient._request("GET", "/api/v1/knowledge/onboarding-status")

    @staticmethod
    def search_context_notes(query, scope, scope_id=None, kinds=None, top_k=10):
        params = {'scope': scope, 'top_k': top_k}
        if scope_id is not None:
            params['scope_id'] = scope_id
        if kinds:
            params['kinds'] = ','.join(kinds) if isinstance(kinds, (list, tuple)) else kinds
        return JarvisPyClient._request("POST", "/api/v1/knowledge/context/search",
                                       json={'query': query}, params=params)

    @staticmethod
    def ontology_text(ontology_id, refresh=False):
        return JarvisPyClient._request("GET", f"/api/v1/knowledge/ontology/{ontology_id}/text",
                                       params={'refresh': refresh})

    # ── Agent ─────────────────────────────────────────────────────────────

    @staticmethod
    def agent_chat(ontology_id, message, session_id=None, model=None, attachment_paths=None):
        payload = {'message': message}
        if session_id is not None:
            payload['session_id'] = session_id
        if model is not None:
            payload['model'] = model
        if attachment_paths is not None:
            payload['attachment_paths'] = attachment_paths
        return JarvisPyClient._request_stream("POST", f"/api/v1/agent/{ontology_id}/chat", json=payload)

    @staticmethod
    def agent_reset(ontology_id, session_id=None):
        payload = {}
        if session_id is not None:
            payload['session_id'] = session_id
        return JarvisPyClient._request("POST", f"/api/v1/agent/{ontology_id}/reset", json=payload)

    # ── Project sharing ───────────────────────────────────────────────────

    @staticmethod
    def create_share(ontology_id, recipient, share_role, expires_in_minutes=None):
        payload = {'project_id': ontology_id, 'recipient': recipient, 'share_role': share_role}
        if expires_in_minutes is not None:
            payload['expires_in_minutes'] = expires_in_minutes
        return JarvisPyClient._request("POST", "/api/v1/ontologies/share", json=payload)

    @staticmethod
    def revoke_share(share_id=None, ontology_id=None, recipient_sub=None):
        payload = {}
        if share_id is not None:
            payload['share_id'] = share_id
        if ontology_id is not None:
            payload['project_id'] = ontology_id
        if recipient_sub is not None:
            payload['recipient_sub'] = recipient_sub
        return JarvisPyClient._request("POST", "/api/v1/ontologies/share/revoke", json=payload)

    @staticmethod
    def update_share_role(share_id, share_role):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/share/update-role",
                                       json={'share_id': share_id, 'share_role': share_role})

    @staticmethod
    def list_shares(ontology_id=None):
        params = {}
        if ontology_id is not None:
            params['project_id'] = ontology_id
        return JarvisPyClient._request("GET", "/api/v1/ontologies/share/list", params=params)

    @staticmethod
    def list_inbox():
        return JarvisPyClient._request("GET", "/api/v1/ontologies/share/inbox")

    @staticmethod
    def accept_share(share_id):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/share/accept",
                                       json={'share_id': share_id})

    @staticmethod
    def leave_share(share_id):
        return JarvisPyClient._request("POST", "/api/v1/ontologies/share/leave",
                                       json={'share_id': share_id})

    @staticmethod
    def sync_inbox():
        return JarvisPyClient._request("POST", "/api/v1/ontologies/share/sync")

    # ── Apps ──────────────────────────────────────────────────────────────

    @staticmethod
    def list_all_apps():
        return JarvisPyClient._request("GET", "/api/v1/apps/list")

    @staticmethod
    def list_apps(ontology_id):
        return JarvisPyClient._request("GET", f"/api/v1/apps/{ontology_id}/list")

    @staticmethod
    def get_app(ontology_id, app_id):
        return JarvisPyClient._request("GET", f"/api/v1/apps/{ontology_id}/{app_id}")

    @staticmethod
    def save_app(ontology_id, app):
        return JarvisPyClient._request("POST", f"/api/v1/apps/{ontology_id}/save",
                                       json={'app': app})

    @staticmethod
    def delete_app(ontology_id, app_id):
        return JarvisPyClient._request("DELETE", f"/api/v1/apps/{ontology_id}/{app_id}")

    @staticmethod
    def publish_app(ontology_id, app_id):
        return JarvisPyClient._request("POST", f"/api/v1/apps/{ontology_id}/{app_id}/publish")

    @staticmethod
    def unpublish_app(ontology_id, app_id):
        return JarvisPyClient._request("POST", f"/api/v1/apps/{ontology_id}/{app_id}/unpublish")

    # ── Schedules ─────────────────────────────────────────────────────────

    @staticmethod
    def create_policy(ontology_id, concept_name, trigger_type="cron", trigger_config=None,
                      enabled=True):
        return JarvisPyClient._request("POST", f"/api/v1/schedules/{ontology_id}/policies",
                                       json={'concept_name': concept_name, 'trigger_type': trigger_type,
                                             'trigger_config': trigger_config or {},
                                             'enabled': enabled})

    @staticmethod
    def list_policies(ontology_id, concept_name=None):
        params = {}
        if concept_name is not None:
            params['concept_name'] = concept_name
        return JarvisPyClient._request("GET", f"/api/v1/schedules/{ontology_id}/policies", params=params)

    @staticmethod
    def get_policy(ontology_id, policy_id):
        return JarvisPyClient._request("GET", f"/api/v1/schedules/{ontology_id}/policies/{policy_id}")

    @staticmethod
    def update_policy(ontology_id, policy_id, trigger_config=None, enabled=None):
        payload = {}
        if trigger_config is not None:
            payload['trigger_config'] = trigger_config
        if enabled is not None:
            payload['enabled'] = enabled
        return JarvisPyClient._request("PATCH", f"/api/v1/schedules/{ontology_id}/policies/{policy_id}",
                                       json=payload)

    @staticmethod
    def delete_policy(ontology_id, policy_id):
        return JarvisPyClient._request("DELETE", f"/api/v1/schedules/{ontology_id}/policies/{policy_id}")

    @staticmethod
    def trigger_policy(ontology_id, policy_id):
        return JarvisPyClient._request(
            "POST", f"/api/v1/schedules/{ontology_id}/policies/{policy_id}/trigger")

    @staticmethod
    def get_run_history(ontology_id, policy_id, limit=50, offset=0):
        return JarvisPyClient._request(
            "GET", f"/api/v1/schedules/{ontology_id}/policies/{policy_id}/runs",
            params={'limit': limit, 'offset': offset})

    # ── Alerts ────────────────────────────────────────────────────────────

    @staticmethod
    def get_alert_history(limit=100, offset=0):
        return JarvisPyClient._request("GET", "/api/v1/alerts/history",
                                       params={'limit': limit, 'offset': offset})

    @staticmethod
    def reprocess_alert(alert_id, compute=None):
        payload = {}
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", f"/api/v1/alerts/{quote(alert_id, safe='')}/reprocess",
                                       json=payload)

    # ── Chat history ──────────────────────────────────────────────────────

    @staticmethod
    def list_sessions(ontology_id=None, limit=50):
        params = {'limit': limit}
        if ontology_id is not None:
            params['project_id'] = ontology_id
        return JarvisPyClient._request("GET", "/api/v1/chat-history/sessions", params=params)

    @staticmethod
    def get_session(session_id):
        return JarvisPyClient._request("GET", f"/api/v1/chat-history/sessions/{quote(session_id, safe='')}")

    @staticmethod
    def rename_session(session_id, title):
        return JarvisPyClient._request("PATCH", f"/api/v1/chat-history/sessions/{quote(session_id, safe='')}",
                                       json={'title': title})

    @staticmethod
    def delete_session(session_id):
        return JarvisPyClient._request("DELETE", f"/api/v1/chat-history/sessions/{quote(session_id, safe='')}")

    # ── Compute ───────────────────────────────────────────────────────────

    @staticmethod
    def check_compute_availability(machine_configs=None, databricks_configs=None):
        compute = {}
        if machine_configs is not None:
            compute['machine_configs'] = machine_configs
        if databricks_configs is not None:
            compute['databricks_configs'] = databricks_configs
        return JarvisPyClient._request("POST", "/api/v1/compute/availability",
                                       json={'compute': compute})

    # ── Machines (compute lifecycle) ───────────────────────────────────────

    @staticmethod
    def list_machines_combined():
        """Catalog + the caller's enabled/disabled machines."""
        return JarvisPyClient._request("GET", "/api/v1/machines/machines-combined")

    @staticmethod
    def set_machine_active(user_machine_id, is_active, autotermination_minutes=None):
        """Start (is_active=True) or stop (is_active=False) one owned machine."""
        body = {'user_machine_id': user_machine_id, 'is_active': bool(is_active)}
        if autotermination_minutes is not None:
            body['autotermination_minutes'] = autotermination_minutes
        return JarvisPyClient._request("PATCH", "/api/v1/machines/user-machines/toggle-active",
                                       json=body)

    @staticmethod
    def get_machine_status(user_machine_id):
        """Real-time pod status of one owned machine."""
        return JarvisPyClient._request(
            "GET", f"/api/v1/machines/user-machines/{user_machine_id}/status")

    @staticmethod
    def use_machine(machine_id, machine_name=None):
        """Add a catalog machine to the caller's list (not billable until started)."""
        body = {'machine_id': machine_id}
        if machine_name is not None:
            body['machine_name'] = machine_name
        return JarvisPyClient._request("POST", "/api/v1/machines/user-machines/use", json=body)

    @staticmethod
    def delete_user_machine(user_machine_id):
        """Soft-disable an owned machine, preserving usage history."""
        return JarvisPyClient._request(
            "DELETE", f"/api/v1/machines/user-machines/{quote(str(user_machine_id), safe='')}")

    # ── Vadalog authoring ─────────────────────────────────────────────────

    @staticmethod
    def analyze_program(program, concept_type="logic", concept_name=""):
        return JarvisPyClient._request("POST", "/api/v1/vadalog/analyze",
                                       json={'program': program, 'conceptType': concept_type,
                                             'conceptName': concept_name})

    @staticmethod
    def build_bind(bind_annotation, predicate_name, is_output=False):
        return JarvisPyClient._request("POST", "/api/v1/vadalog/build-bind",
                                       json={'bindAnnotation': bind_annotation,
                                             'predicateName': predicate_name, 'isOutput': is_output})

    @staticmethod
    def parse_binds(program, output_predicate=""):
        return JarvisPyClient._request("POST", "/api/v1/vadalog/parse-binds",
                                       json={'program': program, 'outputPredicate': output_predicate})

    @staticmethod
    def evaluate_program(program, params=None, compute=None):
        payload = {'program': program, 'params': params or {}}
        if compute:
            payload['compute'] = compute
        return JarvisPyClient._request("POST", "/api/v1/vadalog/evaluate", json=payload)

    @staticmethod
    def validate_concept(definition, concept_type="logic", concept_name="",
                         ontology_id=None, concept_config=None):
        payload = {
            'definition': definition,
            'concept_type': concept_type,
            'concept_name': concept_name,
        }
        if ontology_id is not None:
            payload['project_id'] = ontology_id
        if concept_config is not None:
            payload['concept_config'] = concept_config
        return JarvisPyClient._request("POST", "/api/v1/vadalog/validate", json=payload)

    # ── Assistant helpers ─────────────────────────────────────────────────

    @staticmethod
    def list_skills():
        return JarvisPyClient._request("GET", "/api/v1/assistant/skills")

    @staticmethod
    def get_skill(skill_id):
        return JarvisPyClient._request(
            "GET", f"/api/v1/assistant/skills/{quote(skill_id, safe='')}")

    @staticmethod
    def get_company_info(query):
        return JarvisPyClient._request("GET", "/api/v1/assistant/company-info",
                                       params={'query': query})

    # ── Vadalingo translation ─────────────────────────────────────────────

    @staticmethod
    def translate_sql_to_vadalog(ontology_id, sql_data):
        return JarvisPyClient._request("POST", f"/api/v1/vadalingo/{ontology_id}/translate/sql-to-vadalog",
                                       json={'sql_data': sql_data})

    @staticmethod
    def translate_rdf_to_vadalog(ontology_id, rdf_data):
        return JarvisPyClient._request("POST", f"/api/v1/vadalingo/{ontology_id}/translate/rdf-to-vadalog",
                                       json={'rdf_data': rdf_data})

    @staticmethod
    def translate_owl_to_vadalog(ontology_id, owl_content, base_namespace, data_base_path=None,
                                 options=None, add_concepts=False):
        payload = {'owl_content': owl_content, 'base_namespace': base_namespace,
                   'add_concepts': add_concepts}
        if data_base_path is not None:
            payload['data_base_path'] = data_base_path
        if options is not None:
            payload['options'] = options
        return JarvisPyClient._request("POST", f"/api/v1/vadalingo/{ontology_id}/translate/owl-to-vadalog",
                                       json=payload)
