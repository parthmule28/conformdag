"""Deterministic per-check-kind codemods producing structured edit spans."""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from typing import Any, Final, cast

from conformdag.fixing.specs import EditSpan
from conformdag.models import RemediationAction, RemediationPayload

AUTOFIX_KINDS: Final[frozenset[str]] = frozenset(
    {"required-owner", "required-tags", "execution-timeout", "retry-bounds"}
)
PROPOSED_ONLY_KINDS: Final[frozenset[str]] = frozenset({"top-level-io"})
MANUAL_KINDS: Final[frozenset[str]] = frozenset(
    {
        "forbidden-operators",
        "idempotence",
        "orchestration-boundary",
        "sensitive-logging",
        "approved-abstractions",
    }
)

Codemod = Callable[[str, RemediationPayload], list[EditSpan] | None]


def _end_position(node: ast.stmt | ast.expr) -> tuple[int, int]:
    """Return the end (line, column) of a node parsed from a complete tree."""
    if node.end_lineno is None or node.end_col_offset is None:
        raise ValueError("node end position is unknown")
    return node.end_lineno, node.end_col_offset


def _string_list(raw: str) -> list[str] | None:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, list):
        return None
    entries = cast("list[Any]", loaded)
    additions = [entry for entry in entries if isinstance(entry, str)]
    if not additions or len(additions) != len(entries):
        return None
    return additions


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _is_dag_call(node: ast.Call) -> bool:
    qualified = _qualified_name(node.func)
    return bool(qualified and qualified.rsplit(".", 1)[-1] == "DAG")


def _is_task_call(node: ast.Call) -> bool:
    qualified = _qualified_name(node.func)
    return bool(qualified and qualified.rsplit(".", 1)[-1].endswith("Operator"))


def _keyword(call: ast.Call, name: str) -> ast.keyword | None:
    return next((keyword for keyword in call.keywords if keyword.arg == name), None)


def _insert_span(line: int, col: int, text: str) -> EditSpan:
    return EditSpan(line, col, line, col, text)


def _kwarg_addition_span(call: ast.Call, text: str) -> EditSpan:
    if call.keywords:
        line, col = _end_position(call.keywords[-1].value)
        return _insert_span(line, col, f", {text}")
    close_line, close_col = _end_position(call)
    prefix = ", " if call.args else ""
    return _insert_span(close_line, close_col - 1, f"{prefix}{text}")


def _set_kwarg_span(call: ast.Call, name: str, text: str) -> EditSpan | None:
    keyword = _keyword(call, name)
    if keyword is None:
        return None
    end_line, end_col = _end_position(keyword.value)
    return EditSpan(keyword.value.lineno, keyword.value.col_offset, end_line, end_col, text)


def _nearest(candidates: list[ast.Call], line: int) -> ast.Call:
    return min(candidates, key=lambda node: abs(node.lineno - line))


def _find_dag_call(tree: ast.Module, payload: RemediationPayload) -> ast.Call | None:
    enclosing = payload.target.enclosing if payload.target else None
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_dag_call(node)]
    if not candidates:
        return None
    if enclosing and not enclosing.startswith("dag@"):
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == enclosing
                and isinstance(node.value, ast.Call)
                and _is_dag_call(node.value)
            ):
                return node.value
    if payload.target is None:
        return candidates[0]
    return _nearest(candidates, payload.target.line)


def _find_task_call(tree: ast.Module, payload: RemediationPayload) -> ast.Call | None:
    enclosing = payload.target.enclosing if payload.target else None
    candidates = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_task_call(node)]
    if not candidates:
        return None
    if enclosing:
        for node in candidates:
            task_id = _keyword(node, "task_id")
            if task_id is not None and isinstance(task_id.value, ast.Constant) and task_id.value.value == enclosing:
                return node
        for node in candidates:
            if _qualified_name(node.func) == enclosing:
                return node
    if payload.target is None:
        return candidates[0]
    return _nearest(candidates, payload.target.line)


def _fix_dag_kwarg(source: str, payload: RemediationPayload, name: str, text: str) -> list[EditSpan] | None:
    call = _find_dag_call(ast.parse(source), payload)
    if call is None:
        return None
    if payload.action is RemediationAction.SET_KWARG:
        span = _set_kwarg_span(call, name, text)
        return [span] if span else None
    return [_kwarg_addition_span(call, f"{name}={text}")]


def _fix_task_kwarg(source: str, payload: RemediationPayload, name: str, text: str) -> list[EditSpan] | None:
    call = _find_task_call(ast.parse(source), payload)
    if call is None:
        return None
    if payload.action is RemediationAction.SET_KWARG:
        span = _set_kwarg_span(call, name, text)
        return [span] if span else None
    return [_kwarg_addition_span(call, f"{name}={text}")]


def fix_owner(source: str, payload: RemediationPayload) -> list[EditSpan] | None:
    if payload.value is None:
        return None
    return _fix_dag_kwarg(source, payload, "owner", f'"{payload.value}"')


def fix_tags(source: str, payload: RemediationPayload) -> list[EditSpan] | None:
    if payload.value is None:
        return None
    additions = _string_list(payload.value)
    if additions is None:
        return None
    call = _find_dag_call(ast.parse(source), payload)
    if call is None:
        return None
    rendered = ", ".join(repr(item) for item in additions)
    keyword = _keyword(call, "tags")
    if keyword is None:
        return [_kwarg_addition_span(call, f"tags=[{rendered}]")]
    if not isinstance(keyword.value, ast.List):
        return None
    if keyword.value.elts:
        line, col = _end_position(keyword.value.elts[-1])
        return [_insert_span(line, col, f", {rendered}")]
    return [_insert_span(keyword.value.lineno, keyword.value.col_offset + 1, rendered)]


def fix_execution_timeout(source: str, payload: RemediationPayload) -> list[EditSpan] | None:
    if payload.value is None:
        return None
    text = f"timedelta(seconds={payload.value})"
    return _fix_task_kwarg(source, payload, "execution_timeout", text)


def fix_retry_bounds(source: str, payload: RemediationPayload) -> list[EditSpan] | None:
    if payload.value is None or payload.kwarg is None:
        return None
    if payload.kwarg == "retries":
        return _fix_task_kwarg(source, payload, "retries", payload.value)
    if payload.kwarg == "retry_delay":
        text = f"timedelta(seconds={payload.value})"
        return _fix_task_kwarg(source, payload, "retry_delay", text)
    return None


def _needs_timedelta_import(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "datetime"
            and any(alias.name == "timedelta" and alias.asname is None for alias in node.names)
        ):
            return False
    return True


def timedelta_import_span(source: str) -> EditSpan:
    """Build a zero-width span inserting the timedelta import at a stable position.

    The import is placed after the last top-level import, after the module
    docstring, or after a shebang line when neither exists.

    Args:
        source: The complete current content of the target file.

    Returns:
        A zero-width EditSpan inserting ``from datetime import timedelta``.
    """
    tree = ast.parse(source)
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    if imports:
        line, _ = _end_position(imports[-1])
        return _insert_span(line + 1, 0, "from datetime import timedelta\n")
    docstring = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
        ),
        None,
    )
    if docstring is not None:
        line, _ = _end_position(docstring)
        return _insert_span(line + 1, 0, "from datetime import timedelta\n")
    skip = 2 if source.startswith("#!") else 1
    return _insert_span(skip, 0, "from datetime import timedelta\n")


def fix_move_statement(source: str, payload: RemediationPayload) -> list[EditSpan] | None:
    """Build the proposed-only structural move spans for one module-scope statement."""
    if payload.target is None:
        return None
    tree = ast.parse(source)
    statement = next(
        (node for node in tree.body if node.lineno <= payload.target.line <= (node.end_lineno or node.lineno)),
        None,
    )
    if statement is None or not isinstance(statement, (ast.Assign, ast.Expr)):
        return None
    end_line, _ = _end_position(statement)
    following = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno > end_line
        ),
        None,
    )
    if following is None or not following.body:
        return None
    anchor = following.body[0]
    lines = source.splitlines(keepends=True)
    moved = lines[statement.lineno - 1 : end_line]
    dedented = [line[statement.col_offset :] if line.strip() else line for line in moved]
    indented = "".join(" " * anchor.col_offset + line if line.strip() else line for line in dedented)
    if not indented.endswith("\n"):
        indented += "\n"
    return [
        EditSpan(statement.lineno, 0, end_line + 1, 0, ""),
        _insert_span(anchor.lineno, 0, indented),
    ]


FIXERS: Final[dict[str, Codemod]] = {
    "required-owner": fix_owner,
    "required-tags": fix_tags,
    "execution-timeout": fix_execution_timeout,
    "retry-bounds": fix_retry_bounds,
    "top-level-io": fix_move_statement,
}

TIMEDELTA_KINDS: Final[frozenset[str]] = frozenset({"execution-timeout", "retry-bounds"})


def generate_spans(source: str, payload: RemediationPayload) -> tuple[list[EditSpan], bool] | None:
    """Run the registered codemod for a payload, reporting timedelta import needs.

    Args:
        source: The complete current content of the target file.
        payload: The finding's remediation payload describing the edit.

    Returns:
        A tuple of the edit spans and whether a timedelta import must be
        inserted, or None when the codemod cannot handle the construct.
    """
    codemod = FIXERS.get(payload.fix_kind)
    if codemod is None:
        return None
    spans = codemod(source, payload)
    if spans is None:
        return None
    needs_import = payload.fix_kind in TIMEDELTA_KINDS and _needs_timedelta_import(ast.parse(source))
    return spans, needs_import
