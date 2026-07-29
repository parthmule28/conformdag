"""Non-executing Python source discovery and structural analysis primitives."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

DEFAULT_EXCLUDES = ("**/.venv/**", "**/.git/**", "**/vendor/**", "**/generated/**")


@dataclass(frozen=True)
class SourceFile:
    """A selected source file and its immutable input digest."""

    path: Path
    relative_path: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class ParseIssue:
    path: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class ImportRecord:
    module: str
    alias: str | None
    line: int


@dataclass(frozen=True)
class CallRecord:
    qualified_name: str
    line: int
    column: int
    module_scope: bool


def _empty_defaults() -> dict[str, object]:
    return {}


@dataclass
class DagRecord:
    line: int
    owner: str | None
    owner_source: str | None
    tags: tuple[str, ...]
    variable_name: str | None = None
    defaults: dict[str, object] = field(default_factory=_empty_defaults)


@dataclass
class TaskRecord:
    line: int
    qualified_name: str
    task_id: str | None
    dag_name: str | None
    values: dict[str, object]


def _empty_imports() -> list[ImportRecord]:
    return []


def _empty_calls() -> list[CallRecord]:
    return []


def _empty_dags() -> list[DagRecord]:
    return []


def _empty_tasks() -> list[TaskRecord]:
    return []


def _empty_assignments() -> dict[str, object]:
    return {}


@dataclass
class SourceModel:
    source: SourceFile
    imports: list[ImportRecord] = field(default_factory=_empty_imports)
    calls: list[CallRecord] = field(default_factory=_empty_calls)
    dags: list[DagRecord] = field(default_factory=_empty_dags)
    tasks: list[TaskRecord] = field(default_factory=_empty_tasks)
    assignments: dict[str, object] = field(default_factory=_empty_assignments)


def _matches(relative_path: str, patterns: tuple[str, ...]) -> bool:
    path = Path(relative_path)
    return any(path.match(pattern) for pattern in patterns)


def discover_python_files(
    repository_root: Path,
    include: list[str],
    exclude: list[str] | None = None,
    follow_internal_symlinks: bool = False,
) -> tuple[list[SourceFile], list[ParseIssue]]:
    """Discover normalized Python inputs without following symlinks by default."""
    root = repository_root.resolve()
    excluded = tuple(DEFAULT_EXCLUDES) + tuple(exclude or [])
    selected: dict[str, Path] = {}
    issues: list[ParseIssue] = []
    for pattern in include:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            if candidate.is_symlink() and not follow_internal_symlinks:
                issues.append(
                    ParseIssue(candidate.relative_to(root).as_posix(), "symlink excluded")
                )
                continue
            relative = candidate.relative_to(root).as_posix()
            if _matches(relative, excluded):
                continue
            selected[relative] = candidate

    files: list[SourceFile] = []
    for relative, candidate in sorted(selected.items()):
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(ParseIssue(relative, f"unreadable source: {exc}"))
            continue
        files.append(
            SourceFile(
                path=candidate,
                relative_path=relative,
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
    return files, issues


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

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            self.model.imports.append(ImportRecord(item.name, item.asname, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for item in node.names:
            self.model.imports.append(
                ImportRecord(f"{module}.{item.name}", item.asname, node.lineno)
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        value = _literal_value(node.value)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and value is not None:
            self.model.assignments[node.targets[0].id] = value
        if isinstance(node.value, ast.Call) and self._is_dag_call(node.value):
            variable_name = node.targets[0].id if isinstance(node.targets[0], ast.Name) else None
            for dag in reversed(self.model.dags):
                if dag.line == node.value.lineno:
                    dag.variable_name = variable_name
                    break

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:
        qualified_name = _qualified_name(node.func)
        if qualified_name:
            self.model.calls.append(
                CallRecord(qualified_name, node.lineno, node.col_offset, self._function_depth == 0)
            )
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
        for keyword in node.keywords:
            if (
                keyword.arg == "owner"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                owner = keyword.value.value
                owner_source = "DAG.owner"
            if keyword.arg == "default_args":
                defaults = self._resolve_mapping(keyword.value)
                default_owner = defaults.get("owner")
                if owner is None and isinstance(default_owner, str):
                    owner = default_owner
                    owner_source = "DAG.default_args.owner"
            if keyword.arg == "tags":
                resolved_tags = self._resolve_value(keyword.value)
                if isinstance(resolved_tags, list):
                    tags = tuple(
                        item for item in cast(list[object], resolved_tags) if isinstance(item, str)
                    )
        return DagRecord(node.lineno, owner, owner_source, tags, defaults=defaults)

    def _task_record(self, node: ast.Call, qualified_name: str) -> TaskRecord:
        values: dict[str, object] = {}
        for keyword in node.keywords:
            if keyword.arg:
                values[keyword.arg] = self._resolve_value(keyword.value)
        task_id = values.get("task_id")
        dag_name = values.get("dag")
        return TaskRecord(
            line=node.lineno,
            qualified_name=qualified_name,
            task_id=task_id if isinstance(task_id, str) else None,
            dag_name=dag_name if isinstance(dag_name, str) else None,
            values=values,
        )

    def _resolve_value(self, node: ast.AST) -> object:
        value = _literal_value(node)
        if value is not None:
            return value
        if isinstance(node, ast.Name):
            return self.model.assignments.get(node.id)
        return None

    def _resolve_mapping(self, node: ast.AST) -> dict[str, object]:
        value = _literal_value(node)
        if isinstance(value, dict):
            return cast(dict[str, object], value)
        if isinstance(node, ast.Name):
            assigned = self.model.assignments.get(node.id)
            if isinstance(assigned, dict):
                return cast(dict[str, object], assigned)
        return {}


def _literal_value(node: ast.AST) -> object:
    if isinstance(node, ast.Constant) and isinstance(
        node.value, (str, int, float, bool, type(None))
    ):
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
        units = {
            keyword.arg: _literal_value(keyword.value) for keyword in node.keywords if keyword.arg
        }
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


def analyze_source(source: SourceFile) -> tuple[SourceModel | None, ParseIssue | None]:
    """Parse one file only; importing or executing repository code never occurs."""
    try:
        tree = ast.parse(source.content, filename=source.relative_path)
    except SyntaxError as exc:
        return None, ParseIssue(source.relative_path, exc.msg, exc.lineno)
    visitor = _ModelVisitor(source)
    visitor.visit(tree)
    return visitor.model, None


def iter_module_scope_calls(model: SourceModel) -> Iterator[CallRecord]:
    return (call for call in model.calls if call.module_scope)
