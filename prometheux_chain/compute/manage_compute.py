"""
Compute Management Module

Check availability / reachability of compute resources (machines, Databricks).

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

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
