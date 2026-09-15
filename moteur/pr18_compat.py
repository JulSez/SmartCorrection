"""Compatibility fixes for PR18 legacy format API."""
from __future__ import annotations

from .db import database
from . import pr18_patch as pr18

WorkflowApplication = pr18.WorkflowApplication


def _save_formats_compat(self, ident, correction='A6', corrige='A6', **kwargs):
    if kwargs.get('layout'):
        return pr18._save_layout(self, ident, kwargs['layout'])
    with database(self.db_path) as conn:
        layout = pr18._layout(conn, ident)
    layout['correction']['size'] = correction
    layout['corrige']['size'] = corrige
    pr18._save_layout(self, ident, layout)
    return {'correction': correction, 'corrige': corrige}


WorkflowApplication.save_formats = _save_formats_compat
