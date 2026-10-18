"""Parameter rules: small, composable checks the safety layer applies to an action's arguments.

A rule takes the action's params dict and returns a denial reason, or None to allow.
Rules fail closed: a missing key, wrong type, or unexpected shape is a denial, never a pass.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable

Rule = Callable[[dict[str, Any]], "str | None"]

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")


def required(*keys: str) -> Rule:
    def rule(params: dict[str, Any]) -> str | None:
        missing = [k for k in keys if k not in params]
        return f"missing required params: {missing}" if missing else None
    return rule


def only_keys(*keys: str) -> Rule:
    """Reject any parameter that is not explicitly expected."""
    allowed = set(keys)

    def rule(params: dict[str, Any]) -> str | None:
        extra = sorted(set(params) - allowed)
        return f"unexpected params: {extra}" if extra else None
    return rule


def one_of(key: str, values: Iterable[Any]) -> Rule:
    allowed = list(values)

    def rule(params: dict[str, Any]) -> str | None:
        if key not in params:
            return f"'{key}' is missing"
        return None if params[key] in allowed else f"'{key}' must be one of {allowed}"
    return rule


def matches(key: str, pattern: str) -> Rule:
    """The whole string value must match the regex (fullmatch, not search)."""
    compiled = re.compile(pattern)

    def rule(params: dict[str, Any]) -> str | None:
        value = params.get(key)
        if not isinstance(value, str):
            return f"'{key}' must be a string"
        return None if compiled.fullmatch(value) else f"'{key}' does not match {pattern!r}"
    return rule


def max_len(key: str, n: int) -> Rule:
    def rule(params: dict[str, Any]) -> str | None:
        value = params.get(key)
        if not isinstance(value, str):
            return f"'{key}' must be a string"
        return None if len(value) <= n else f"'{key}' longer than {n} characters"
    return rule


def number_between(key: str, lo: float | None = None, hi: float | None = None) -> Rule:
    def rule(params: dict[str, Any]) -> str | None:
        value = params.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"'{key}' must be a number"
        if value != value:  # NaN
            return f"'{key}' is NaN"
        if lo is not None and value < lo:
            return f"'{key}' below minimum {lo}"
        if hi is not None and value > hi:
            return f"'{key}' above maximum {hi}"
        return None
    return rule


def email_domain(key: str, *domains: str) -> Rule:
    """Value must be exactly one address whose domain is in the allowed list (exact match, case-insensitive)."""
    allowed = {d.lower() for d in domains}

    def rule(params: dict[str, Any]) -> str | None:
        value = params.get(key)
        if not isinstance(value, str) or not _EMAIL.fullmatch(value):
            return f"'{key}' must be a single email address"
        domain = value.rsplit("@", 1)[1].lower()
        return None if domain in allowed else f"'{key}' domain '{domain}' not in {sorted(allowed)}"
    return rule
