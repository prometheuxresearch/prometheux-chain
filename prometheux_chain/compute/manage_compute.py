"""
Compute Management Module

Check availability / reachability of compute resources (machines, Databricks).

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

import time
from contextlib import contextmanager

from ..client.jarvispy_client import JarvisPyClient


def check_compute_availability(machine_configs=None, databricks_configs=None):
    """Check whether the given compute resources are available and reachable.

    Provide at least one of ``machine_configs`` or ``databricks_configs``.
    Returns the parsed response data. Note the backend returns a non-success
    status when a resource is unavailable, so this returns the full response
    dict rather than raising in that case.
    """
    if not machine_configs and not databricks_configs:
        raise ValueError("Provide at least one of 'machine_configs' or 'databricks_configs'")
    return JarvisPyClient.check_compute_availability(
        machine_configs=machine_configs, databricks_configs=databricks_configs,
    )


def list_machines_combined():
    """Return the machine catalog plus the caller's enabled/disabled machines."""
    return JarvisPyClient.list_machines_combined()


def set_machine_active(user_machine_id, is_active, autotermination_minutes=None):
    """Start (is_active=True) or stop (is_active=False) one owned machine."""
    return JarvisPyClient.set_machine_active(
        user_machine_id, is_active, autotermination_minutes=autotermination_minutes,
    )


def get_machine_status(user_machine_id):
    """Return real-time pod status of one owned machine."""
    return JarvisPyClient.get_machine_status(user_machine_id)


def use_machine(machine_id, machine_name=None):
    """Add a catalog machine to the caller's list (not billable until started)."""
    return JarvisPyClient.use_machine(machine_id, machine_name=machine_name)


def delete_user_machine(user_machine_id):
    """Soft-disable an owned machine, preserving usage history."""
    return JarvisPyClient.delete_user_machine(user_machine_id)


def set_engine_workers(replicas, idle_minutes=None, user_machine_id=None):
    """Run ``replicas`` engine-only workers beside your running machine (0 removes them).

    Program evaluations (``evaluate_program``, ``check_program``) are then spread
    across the machine and its ready workers, so independent programs sent at the
    same time run in parallel. Each worker is another node of the machine's size,
    billed at the machine's hourly rate from this call until it is removed; the
    platform caps how many you may run. Workers nobody sends a program to for
    ``idle_minutes`` (default 10, never longer than the machine's auto-termination)
    are removed automatically.

    Returns the workers' state: ``desired``, ``ready``, ``pods``, ``engines`` (how
    many calls each engine is running and has run) and ``billing``
    (``cost_per_worker_hour_usd``, ``billed_workers``, ``billed_since``,
    ``cost_since_usd``).
    """
    return JarvisPyClient.set_engine_workers(
        replicas, idle_minutes=idle_minutes, user_machine_id=user_machine_id).get("data") or {}


def get_engine_workers(user_machine_id=None):
    """The state of the engine workers beside your running machine."""
    return JarvisPyClient.get_engine_workers(user_machine_id=user_machine_id).get("data") or {}


def wait_for_engine_workers(replicas, timeout=600, poll_seconds=5, on_progress=None,
                            user_machine_id=None):
    """Block until ``replicas`` workers are ready; returns their state.

    A new worker usually needs a new node, so allow several minutes. Raises
    ``TimeoutError`` when they are not all ready in time. ``on_progress`` is
    called with the state after every poll.
    """
    deadline = time.monotonic() + timeout
    while True:
        state = get_engine_workers(user_machine_id=user_machine_id)
        if on_progress:
            on_progress(state)
        if int(state.get("ready") or 0) >= replicas:
            return state
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"{state.get('ready', 0)} of {replicas} engine worker(s) ready after {timeout:.0f}s")
        time.sleep(poll_seconds)


@contextmanager
def engine_workers(replicas, idle_minutes=None, timeout=600, keep=False, on_progress=None,
                   user_machine_id=None):
    """Run ``replicas`` engine workers for the duration of a ``with`` block.

    Waits until they are ready before entering, and removes them on exit, even
    when the block raises, unless ``keep`` is set (the idle timeout still applies)::

        with px.engine_workers(3):
            reports = list(pool.map(lambda p: px.check_program(p, expect=...), programs))
    """
    set_engine_workers(replicas, idle_minutes=idle_minutes, user_machine_id=user_machine_id)
    try:
        state = wait_for_engine_workers(replicas, timeout=timeout, on_progress=on_progress,
                                        user_machine_id=user_machine_id) if replicas else {}
        yield state
    finally:
        if not keep and replicas:
            set_engine_workers(0, user_machine_id=user_machine_id)
