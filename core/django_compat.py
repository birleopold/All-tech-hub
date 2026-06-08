"""
Work around Django 4.2 template context copying on Python 3.14+.

BaseContext.__copy__ used ``copy(super())``, which no longer produces a real
instance there, breaking admin and any code that copies RequestContext/Context.

Matches the fix in Django's main branch (see django.template.context.BaseContext).
"""

from __future__ import annotations

from copy import copy as copy_obj


def apply() -> None:
    from django.template.context import BaseContext

    def __copy__(self):  # noqa: D401 — Django mirrors stdlib copy protocol
        duplicate = BaseContext()
        duplicate.__class__ = self.__class__
        duplicate.__dict__ = copy_obj(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate

    BaseContext.__copy__ = __copy__
