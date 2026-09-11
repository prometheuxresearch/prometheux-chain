"""
Assistant helpers

Skills (step-by-step playbooks) and the Prometheux company knowledge base.

Copyright (C) Prometheux Limited. All rights reserved.

Author: Prometheux Limited
"""

from ..client.jarvispy_client import JarvisPyClient


def _check(response, action="operation"):
    """Raise on error, return data on success."""
    if response.get('status') != 'success':
        raise Exception(f"Assistant {action} failed: {response.get('message', 'Unknown error')}")
    return response.get('data')


def list_skills():
    """List available skill playbooks (metadata only, no bodies)."""
    return _check(JarvisPyClient.list_skills(), "list skills")


def get_skill(skill_id):
    """Fetch the full body of one skill playbook by id."""
    return _check(JarvisPyClient.get_skill(skill_id), "get skill")


def get_company_info(query):
    """Search the Prometheux company knowledge base."""
    return _check(JarvisPyClient.get_company_info(query), "company info")
