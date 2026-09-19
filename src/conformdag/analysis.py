"""Non-executing Python source discovery and structural analysis primitives."""

from __future__ import annotations

import ast
import hashlib
import os
import pickle
import re
import tempfile
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import cast

DEFAULT_EXCLUDES = ("**/.venv/**", "**/.git/**", "**/vendor/**", "**/generated/**")


class ParseIssueCode(StrEnum):
    """Stable categories for source-discovery and parsing failures."""

    SYMLINK_EXCLUDED = "SYMLINK_EXCLUDED"
    EXTERNAL_SYMLINK_EXCLUDED = "EXTERNAL_SYMLINK_EXCLUDED"
    BROKEN_SYMLINK_EXCLUDED = "BROKEN_SYMLINK_EXCLUDED"
    SYMLINK_RESOLUTION_ERROR = "SYMLINK_RESOLUTION_ERROR"
    READ_ERROR = "READ_ERROR"
    INVALID_SOURCE = "INVALID_SOURCE"


NON_FATAL_DISCOVERY_ISSUES = frozenset(
    {
        ParseIssueCode.SYMLINK_EXCLUDED,
        ParseIssueCode.EXTERNAL_SYMLINK_EXCLUDED,
        ParseIssueCode.BROKEN_SYMLINK_EXCLUDED,
        ParseIssueCode.SYMLINK_RESOLUTION_ERROR,
    }
)


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
    code: ParseIssueCode = ParseIssueCode.INVALID_SOURCE


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
    uncertain: bool = False


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
    start_date: tuple[int, int, int] | None = None
    start_date_tz: bool | None = None
    catchup: bool | None = None
    schedule: str | None = None
    max_active_runs: int | None = None
    factory_function: str | None = None


@dataclass
class TaskRecord:
    line: int
    qualified_name: str
    task_id: str | None
    dag_name: str | None
    values: dict[str, object]
    taskflow: bool = False
    dag_line: int | None = None
    unresolved_kwargs: tuple[str, ...] = ()


def _empty_secrets() -> list[SecretAssignment]:
    return []


def _empty_constants() -> list[ConstantAssignment]:
    return []


def _empty_dynamic_loops() -> list[int]:
    return []


@dataclass(frozen=True)
class ConstantAssignment:
    """A module-scope constant assignment: name, value, and line."""

    line: int
    name: str
    value: object


@dataclass(frozen=True)
class SecretAssignment:
    """A module-scope assignment whose name looks like a credential holder."""

    line: int
    name: str


def secret_like(name: str) -> bool:
    lowered = name.lower()
    return any(
        marker in lowered for marker in ("password", "passwd", "token", "secret", "api_key", "apikey", "credential")
    )


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
    constants: list[ConstantAssignment] = field(default_factory=_empty_constants)
    secret_assignments: list[SecretAssignment] = field(default_factory=_empty_secrets)
    dynamic_dag_lines: list[int] = field(default_factory=_empty_dynamic_loops)


def _normalize_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


@lru_cache(maxsize=256)
def _exclude_regex(pattern: str) -> re.Pattern[str]:
    """Compile a repository-relative glob with explicit ``**`` semantics."""
    normalized = _normalize_relative_path(pattern)
    expression: list[str] = []
    index = 0
    while index < len(normalized):
        if normalized.startswith("**/", index):
            expression.append("(?:.*/)?")
            index += 3
        elif normalized.startswith("/**", index):
            expression.append("(?:/.*)?")
            index += 3
        elif normalized.startswith("**", index):
            expression.append(".*")
            index += 2
        elif normalized[index] == "*":
            expression.append("[^/]*")
            index += 1
        elif normalized[index] == "?":
            expression.append("[^/]")
            index += 1
        else:
            expression.append(re.escape(normalized[index]))
            index += 1
    return re.compile("^" + "".join(expression) + "$")


def matches_exclude(relative_path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Match normalized repository-relative paths with recursive glob semantics."""
    candidate = _normalize_relative_path(relative_path)
    return any(_exclude_regex(_normalize_relative_path(pattern)).fullmatch(candidate) for pattern in patterns)


def _contains_symlink(candidate: Path, root: Path) -> bool:
    try:
        relative_parts = candidate.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _append_discovery_issue(
    issues: list[ParseIssue],
    seen: set[tuple[str, ParseIssueCode]],
    path: str,
    message: str,
    code: ParseIssueCode,
) -> None:
    key = (path, code)
    if key in seen:
        return
    seen.add(key)
    issues.append(ParseIssue(path, message, code=code))


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
    issue_keys: set[tuple[str, ParseIssueCode]] = set()
    for pattern in include:
        for candidate in root.glob(pattern):
            try:
                relative = candidate.relative_to(root).as_posix()
            except ValueError:
                continue
            if matches_exclude(relative, excluded):
                continue
            contains_symlink = _contains_symlink(candidate, root)
            try:
                resolved = candidate.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                _append_discovery_issue(
                    issues,
                    issue_keys,
                    relative,
                    f"symlink target could not be resolved: {exc}",
                    ParseIssueCode.SYMLINK_RESOLUTION_ERROR,
                )
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                if contains_symlink:
                    _append_discovery_issue(
                        issues,
                        issue_keys,
                        relative,
                        "symlink target is outside the repository root",
                        ParseIssueCode.EXTERNAL_SYMLINK_EXCLUDED,
                    )
                continue
            if contains_symlink:
                if not follow_internal_symlinks:
                    _append_discovery_issue(
                        issues,
                        issue_keys,
                        relative,
                        "symlink excluded by scan configuration",
                        ParseIssueCode.SYMLINK_EXCLUDED,
                    )
                    continue
                if not resolved.exists():
                    _append_discovery_issue(
                        issues,
                        issue_keys,
                        relative,
                        "symlink target does not exist",
                        ParseIssueCode.BROKEN_SYMLINK_EXCLUDED,
                    )
                    continue
            if not candidate.is_file():
                continue
            selected[relative] = candidate

    files: list[SourceFile] = []
    for relative, candidate in sorted(selected.items()):
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            issues.append(ParseIssue(relative, f"unreadable source: {exc}", code=ParseIssueCode.READ_ERROR))
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
        value = _literal_value(node.value)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and value is not None:
            self.model.assignments[node.targets[0].id] = value
            if self._function_depth == 0:
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
                    value = _literal_value(keyword.value)
                    if value is None:
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
                defaults = self._resolve_mapping(keyword.value)
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
            if value is None:
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


class ParseCache:
    """Disk-backed parse cache keyed by file content hash.

    Entries store pickled SourceModel objects in a trusted local directory and
    are validated by their content-hash key, so a cache hit is exactly the model
    a fresh parse of the same bytes would produce. Repeated scans of unchanged
    trees skip reparsing entirely.
    """

    def __init__(self, directory: Path, max_entries: int = 50_000) -> None:
        self.directory = directory
        self.max_entries = max_entries
        self._puts_since_prune = 0

    def get(self, content_hash: str) -> SourceModel | None:
        entry = self.directory / f"{content_hash}.pkl"
        try:
            model = pickle.loads(entry.read_bytes())  # noqa: S301 - trusted local cache
        except (OSError, pickle.UnpicklingError, EOFError):
            return None
        return model if isinstance(model, SourceModel) else None

    def put(self, content_hash: str, model: SourceModel) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        entry = self.directory / f"{content_hash}.pkl"
        payload = pickle.dumps(model)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.directory,
                prefix=f".{entry.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(entry)
        except OSError:
            return
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
        self._puts_since_prune += 1
        if self._puts_since_prune >= 500:
            self._puts_since_prune = 0
            self._prune()

    def _prune(self) -> None:
        try:
            entries = sorted(self.directory.glob("*.pkl"), key=lambda entry: entry.stat().st_mtime, reverse=True)
        except OSError:
            return
        for stale in entries[self.max_entries :]:
            try:
                stale.unlink(missing_ok=True)
            except OSError:
                continue


def iter_module_scope_calls(model: SourceModel) -> Iterator[CallRecord]:
    return (call for call in model.calls if call.module_scope)
