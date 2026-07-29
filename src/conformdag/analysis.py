"""Non-executing Python source discovery and structural analysis primitives."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass(frozen=True)
class DagRecord:
    line: int
    owner: str | None
    tags: tuple[str, ...]


def _empty_imports() -> list[ImportRecord]:
    return []


def _empty_calls() -> list[CallRecord]:
    return []


def _empty_dags() -> list[DagRecord]:
    return []


@dataclass
class SourceModel:
    source: SourceFile
    imports: list[ImportRecord] = field(default_factory=_empty_imports)
    calls: list[CallRecord] = field(default_factory=_empty_calls)
    dags: list[DagRecord] = field(default_factory=_empty_dags)


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
            if qualified_name.rsplit(".", 1)[-1] == "DAG":
                self.model.dags.append(self._dag_record(node))
        self.generic_visit(node)

    @staticmethod
    def _dag_record(node: ast.Call) -> DagRecord:
        owner: str | None = None
        tags: tuple[str, ...] = ()
        for keyword in node.keywords:
            if (
                keyword.arg == "owner"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                owner = keyword.value.value
            if keyword.arg == "tags" and isinstance(keyword.value, (ast.List, ast.Tuple)):
                tags = tuple(
                    item.value
                    for item in keyword.value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
        return DagRecord(node.lineno, owner, tags)


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
