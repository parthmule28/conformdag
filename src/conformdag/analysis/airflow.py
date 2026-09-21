"""Airflow-specific non-executing AST analysis."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import cast

from conformdag.analysis.cache import ParseCache
from conformdag.analysis.models import (
    CallRecord,
    ConstantAssignment,
    DagRecord,
    ImportRecord,
    ParseIssue,
    ParseIssueCode,
    SecretAssignment,
    SourceFile,
    SourceModel,
    TaskRecord,
    secret_like,
)


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


class _ModelVisitor(ast.NodeVisitor):
    def __init__(self, source: SourceFile) -> None:
        self.model = SourceModel(source)
        self._function_depth = 0
        self._with_dag_stack: list[tuple[str | None, int | None]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self.model.imports.append(ImportRecord(item.name, item.asname, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for item in node.names:
            self.model.imports.append(ImportRecord(f"{module}.{item.name}", item.asname, node.lineno))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        value = self._resolve_value(node.value)
        unresolved: tuple[str, ...] = ()
        if isinstance(node.value, (ast.Dict, ast.Name)):
            mapped_value, unresolved = self._resolve_mapping(node.value)
            if unresolved or isinstance(value, dict):
                value = mapped_value
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and value is not _UNRESOLVED_VALUE:
            name = node.targets[0].id
            self.model.assignments[name] = value
            if unresolved:
                self.model.unresolved_assignments[name] = unresolved
            else:
                self.model.unresolved_assignments.pop(name, None)
            if self._function_depth == 0 and not unresolved:
                self.model.constants.append(ConstantAssignment(node.lineno, node.targets[0].id, value))
                if isinstance(value, str) and secret_like(node.targets[0].id):
                    self.model.secret_assignments.append(SecretAssignment(node.lineno, node.targets[0].id))
        if isinstance(node.value, ast.Call) and self._is_dag_call(node.value):
            variable_name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
            for dag in reversed(self.model.dags):
                if dag.line == node.value.lineno:
                    dag.variable_name = variable_name
                    break

    def visit_With(self, node: ast.With) -> None:
        entered: list[str | None] = []
        for item in node.items:
            context = item.context_expr
            is_dag = isinstance(context, ast.Call) and self._is_dag_call(context)
            dag_count = len(self.model.dags)
            self.visit(context)
            if is_dag:
                name: str | None = None
                if item.optional_vars is not None and isinstance(item.optional_vars, ast.Name):
                    name = item.optional_vars.id
                dag_line: int | None = None
                if len(self.model.dags) > dag_count:
                    dag_record = self.model.dags[dag_count]
                    dag_record.variable_name = name
                    dag_line = dag_record.line
                self._with_dag_stack.append((name, dag_line))
                entered.append(name)
            if item.optional_vars is not None:
                self.visit(item.optional_vars)
        for statement in node.body:
            self.visit(statement)
        for _ in entered:
            self._with_dag_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_decorated_function(node)
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_decorated_function(node)
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_For(self, node: ast.For) -> None:
        if self._function_depth == 0:
            for nested in ast.walk(node):
                if isinstance(nested, ast.Call) and self._is_dag_call(nested):
                    self.model.dynamic_dag_lines.append(node.lineno)
                    break
        self.generic_visit(node)

    def _enter_decorated_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._check_taskflow_decorator(node)
        self._function_depth += 1

    def _check_taskflow_decorator(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            qualified_name = _qualified_name(target)
            if qualified_name is None:
                continue
            leaf = qualified_name.rsplit(".", 1)[-1]
            if leaf != "task":
                continue
            values: dict[str, object] = {}
            unresolved: list[str] = []
            if isinstance(decorator, ast.Call):
                for keyword in decorator.keywords:
                    if not keyword.arg:
                        continue
                    value = self._resolve_value(keyword.value)
                    if value is _UNRESOLVED_VALUE:
                        unresolved.append(keyword.arg)
                    else:
                        values[keyword.arg] = value
            task_id = values.get("task_id")
            dag_name: str | None = None
            dag_line: int | None = None
            if self._with_dag_stack:
                dag_name, dag_line = self._with_dag_stack[-1]
            self.model.tasks.append(
                TaskRecord(
                    line=node.lineno,
                    qualified_name=node.name + " (taskflow)",
                    task_id=task_id if isinstance(task_id, str) else node.name,
                    dag_name=dag_name,
                    values=values,
                    taskflow=True,
                    dag_line=dag_line,
                    unresolved_kwargs=tuple(unresolved),
                )
            )

    def visit_Call(self, node: ast.Call) -> None:
        qualified_name = _qualified_name(node.func)
        self.model.calls.append(
            CallRecord(
                qualified_name or "<dynamic>",
                node.lineno,
                node.col_offset,
                self._function_depth == 0,
                uncertain=qualified_name is None,
            )
        )
        if qualified_name:
            if self._is_dag_call(node):
                self.model.dags.append(self._dag_record(node))
            elif qualified_name.rsplit(".", 1)[-1].endswith("Operator"):
                self.model.tasks.append(self._task_record(node, qualified_name))
        self.generic_visit(node)

    @staticmethod
    def _is_dag_call(node: ast.Call) -> bool:
        qualified_name = _qualified_name(node.func)
        return bool(qualified_name and qualified_name.rsplit(".", 1)[-1] == "DAG")

    def _dag_record(self, node: ast.Call) -> DagRecord:
        owner: str | None = None
        owner_source: str | None = None
        tags: tuple[str, ...] = ()
        defaults: dict[str, object] = {}
        unresolved_defaults: list[str] = []
        start_date: tuple[int, int, int] | None = None
        start_date_tz: bool | None = None
        catchup: bool | None = None
        schedule: str | None = None
        max_active_runs: int | None = None
        for keyword in node.keywords:
            if (
                keyword.arg == "owner"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                owner = keyword.value.value
                owner_source = "DAG.owner"
            if keyword.arg == "default_args":
                defaults, unresolved = self._resolve_mapping(keyword.value)
                unresolved_defaults.extend(unresolved)
                default_owner = defaults.get("owner")
                if owner is None and isinstance(default_owner, str):
                    owner = default_owner
                    owner_source = "DAG.default_args.owner"
            if keyword.arg == "tags":
                resolved_tags = self._resolve_value(keyword.value)
                if isinstance(resolved_tags, list):
                    tags = tuple(item for item in cast(list[object], resolved_tags) if isinstance(item, str))
            if keyword.arg == "start_date":
                start_date, start_date_tz = datetime_parts(keyword.value)
            if keyword.arg == "catchup" and isinstance(keyword.value, ast.Constant):
                catchup = bool(keyword.value.value)
            if keyword.arg == "schedule" and isinstance(keyword.value, ast.Constant):
                schedule = str(keyword.value.value)
            if (
                keyword.arg == "max_active_runs"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, int)
            ):
                max_active_runs = keyword.value.value
        return DagRecord(
            node.lineno,
            owner,
            owner_source,
            tags,
            defaults=defaults,
            unresolved_defaults=tuple(unresolved_defaults),
            start_date=start_date,
            start_date_tz=start_date_tz,
            catchup=catchup,
            schedule=schedule,
            max_active_runs=max_active_runs,
        )

    def _task_record(self, node: ast.Call, qualified_name: str) -> TaskRecord:
        values: dict[str, object] = {}
        unresolved: list[str] = []
        dag_name: str | None = None
        dag_line: int | None = None
        for keyword in node.keywords:
            if not keyword.arg:
                continue
            if keyword.arg == "dag" and isinstance(keyword.value, ast.Name):
                bound_line = self._resolve_dag_binding(keyword.value)
                if bound_line is not None:
                    dag_name = keyword.value.id
                    dag_line = bound_line
                    continue
            value = self._resolve_value(keyword.value)
            if value is _UNRESOLVED_VALUE:
                unresolved.append(keyword.arg)
            else:
                values[keyword.arg] = value
        if dag_name is None:
            raw_dag = values.get("dag")
            if isinstance(raw_dag, str):
                dag_name = raw_dag
        if dag_line is None and self._with_dag_stack:
            dag_line = self._with_dag_stack[-1][1]
        task_id = values.get("task_id")
        return TaskRecord(
            line=node.lineno,
            qualified_name=qualified_name,
            task_id=task_id if isinstance(task_id, str) else None,
            dag_name=dag_name,
            values=values,
            dag_line=dag_line,
            unresolved_kwargs=tuple(unresolved),
        )

    def _resolve_dag_binding(self, node: ast.AST) -> int | None:
        """Return the concrete DagRecord line when the node names a known DAG variable."""
        if not isinstance(node, ast.Name):
            return None
        for dag in self.model.dags:
            if dag.variable_name == node.id:
                return dag.line
        return None

    def _resolve_value(self, node: ast.AST) -> object:
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            resolved_items: list[object] = []
            for item in node.elts:
                value = self._resolve_value(item)
                if value is _UNRESOLVED_VALUE:
                    return _UNRESOLVED_VALUE
                resolved_items.append(value)
            return resolved_items
        if isinstance(node, ast.Dict):
            values: dict[str, object] = {}
            for key, value_node in zip(node.keys, node.values, strict=True):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    return _UNRESOLVED_VALUE
                value = self._resolve_value(value_node)
                if value is _UNRESOLVED_VALUE:
                    return _UNRESOLVED_VALUE
                values[key.value] = value
            return values
        if isinstance(node, ast.Call) and _qualified_name(node.func) == "timedelta":
            units: dict[str, object] = {}
            for keyword in node.keywords:
                if not keyword.arg:
                    return _UNRESOLVED_VALUE
                value = self._resolve_value(keyword.value)
                if value is _UNRESOLVED_VALUE:
                    return _UNRESOLVED_VALUE
                units[keyword.arg] = value
            total = 0.0
            for unit, multiplier in (
                ("weeks", 604800),
                ("days", 86400),
                ("hours", 3600),
                ("minutes", 60),
                ("seconds", 1),
            ):
                value = units.get(unit, 0)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return _UNRESOLVED_VALUE
                total += float(value) * multiplier
            return total
        if isinstance(node, ast.Name):
            return self.model.assignments.get(node.id, _UNRESOLVED_VALUE)
        return _UNRESOLVED_VALUE

    def _resolve_mapping(self, node: ast.AST) -> tuple[dict[str, object], tuple[str, ...]]:
        value = self._resolve_value(node)
        if isinstance(value, dict):
            unresolved_keys = self.model.unresolved_assignments.get(node.id, ()) if isinstance(node, ast.Name) else ()
            return cast(dict[str, object], value), tuple(unresolved_keys)
        if isinstance(node, ast.Dict):
            resolved: dict[str, object] = {}
            unresolved: list[str] = []
            for key, value_node in zip(node.keys, node.values, strict=True):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    continue
                value = self._resolve_value(value_node)
                if value is _UNRESOLVED_VALUE:
                    unresolved.append(key.value)
                else:
                    resolved[key.value] = value
            return resolved, tuple(unresolved)
        return {}, ()


def _literal_value(node: ast.AST) -> object:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [_literal_value(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        result: dict[str, object] = {}
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                result[key.value] = _literal_value(value)
        return result
    if isinstance(node, ast.Call) and _qualified_name(node.func) == "timedelta":
        units = {keyword.arg: _literal_value(keyword.value) for keyword in node.keywords if keyword.arg}
        total = 0.0
        for unit, multiplier in (
            ("weeks", 604800),
            ("days", 86400),
            ("hours", 3600),
            ("minutes", 60),
            ("seconds", 1),
        ):
            value = units.get(unit, 0)
            if not isinstance(value, (int, float)):
                return None
            total += float(value) * multiplier
        return total
    return None


_UNRESOLVED_VALUE = object()


def datetime_parts(node: ast.AST) -> tuple[tuple[int, int, int] | None, bool | None]:
    """Extract (year, month, day) and timezone-awareness from a date expression.

    Understands ``datetime(y, m, d)`` / ``pendulum.datetime(...)`` calls (with
    an optional tz keyword marking awareness) and ISO ``"YYYY-MM-DD"`` strings.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        parts = node.value.split("-")
        if len(parts) == 3 and all(part.strip().isdigit() for part in parts):
            return (int(parts[0]), int(parts[1]), int(parts[2])), False
        return None, None
    if not isinstance(node, ast.Call):
        return None, None
    components: list[int] = []
    for arg in node.args[:3]:
        value = _literal_value(arg)
        if not isinstance(value, int) or isinstance(value, bool):
            return None, None
        components.append(value)
    if len(components) < 3 or any(part < 0 for part in components):
        return None, None
    has_tz = any(keyword.arg in {"tz", "tzinfo"} for keyword in node.keywords)
    return (components[0], components[1], components[2]), has_tz


def analyze_source(source: SourceFile, cache: ParseCache | None = None) -> tuple[SourceModel | None, ParseIssue | None]:
    """Parse one file only; importing or executing repository code never occurs."""
    if cache is not None:
        cached = cache.get(source.content_hash)
        if cached is not None:
            cached.source = source
            return cached, None
    try:
        tree = ast.parse(source.content, filename=source.relative_path)
    except SyntaxError as exc:
        return None, ParseIssue(source.relative_path, exc.msg, exc.lineno, ParseIssueCode.INVALID_SOURCE)
    visitor = _ModelVisitor(source)
    visitor.visit(tree)
    model = visitor.model
    if cache is not None:
        cache.put(source.content_hash, model)
    return model, None


def iter_module_scope_calls(model: SourceModel) -> Iterator[CallRecord]:
    return (call for call in model.calls if call.module_scope)
