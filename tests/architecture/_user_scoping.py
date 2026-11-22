"""Static checker backing the T-D16 user-scoping rule (ADR-0022, ADR-0061 §5).

Walks Python source with :mod:`ast`, reconstructs every SQL string handed to
``<conn>.execute(...)`` / ``executemany(...)`` (string literals, implicit
concatenation, f-strings, ``+`` / ``+=`` building, and ``" AND ".join(list)``
over a locally-built clause list), parses it with :mod:`sqlglot`, and reports
any statement that touches a user-owned table without a ``user_id`` scope.

Rules:

- SELECT / UPDATE / DELETE touching a *directly user-owned* table must carry
  ``<alias>.user_id = ...`` in its own WHERE or JOIN ON clause (unqualified
  ``user_id`` is accepted for the statement's primary table).
- SELECT / UPDATE / DELETE touching an *FK-scoped* table (``account_snapshots``
  via ``accounts``, ``recurring_rule_overrides`` via ``recurring_rules``) must
  reference the parent table somewhere in the same statement (JOIN or EXISTS
  subquery) and that parent reference must itself be user-scoped.
- INSERT into a directly user-owned table must list ``user_id`` in its column
  list. INSERT into an FK-scoped table must be paired, in the same top-level
  function, with a user-scoped query against the parent (ownership pre-check).
- Credential tables (``sessions``, ``webauthn_credentials``) may alternatively
  be keyed by their opaque, unguessable identifier (possession of the token
  *is* the authentication step), see ``ALTERNATE_SCOPE_KEYS``.

The checker is intentionally conservative about control flow: every string
added under any branch is unioned into the final SQL, so a predicate added
only on one branch still counts. It is a backstop, not a proof.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

USER_OWNED_TABLES: frozenset[str] = frozenset(
    {
        "accounts",
        "categories",
        "transactions",
        "planned_transactions",
        "recurring_rules",
        "budget_defaults",
        "budget_recurring_overrides",
        "budget_one_off_overrides",
        "user_preferences",
        "sessions",
        "webauthn_credentials",
    }
)

FK_SCOPED_TABLES: dict[str, str] = {
    "account_snapshots": "accounts",
    "recurring_rule_overrides": "recurring_rules",
}

# Opaque-key lookups that are scoping by construction (T-D02 tables).
ALTERNATE_SCOPE_KEYS: dict[str, frozenset[str]] = {
    "sessions": frozenset({"id", "session_id", "token_hash"}),
    "webauthn_credentials": frozenset({"credential_id"}),
}

# Not user-owned — never checked (documented for readers; any table not in
# USER_OWNED_TABLES / FK_SCOPED_TABLES is ignored).
NOT_USER_OWNED_TABLES: frozenset[str] = frozenset(
    {"fx_rates", "audit_log", "schema_migrations", "users", "auth_rate_limit"}
)

_EXECUTE_METHODS = frozenset({"execute", "executemany"})
_DYN = "dyn"
_DYN_TABLE_MESSAGE = (
    "dynamic table name is not resolvable; use a repositories/_shared OwnedTable helper "
    "(its SQL builders are checked per table)"
)
_KEYWORDS_BEFORE_EXPR = frozenset(
    {
        "SELECT",
        "WHERE",
        "AND",
        "OR",
        "BY",
        "ON",
        "SET",
        "FROM",
        "JOIN",
        "IN",
        "VALUES",
        "UPDATE",
        "INTO",
    }
)


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    function: str
    message: str
    sql: str

    def render(self) -> str:
        return f"{self.path}:{self.line} in {self.function}(): {self.message}\n    SQL: {self.sql}"


@dataclass(frozen=True, slots=True)
class _SqlSite:
    line: int
    sql: str


# --------------------------------------------------------------------------
# Python side: reconstruct SQL strings
# --------------------------------------------------------------------------


def _module_constants(tree: ast.Module) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in tree.body:
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and value is not None:
            resolved = _Resolver(consts, {}, {}).resolve(value)
            if resolved is not None:
                consts[target.id] = resolved
    return consts


def _placeholder_for(prefix: str) -> str:
    """Pick a stand-in for an unresolvable f-string hole based on context.

    After a keyword / ``(`` / ``,`` / ``=`` an expression is expected so we
    emit an identifier; after an expression (e.g. ``ORDER BY col {dir}``)
    we emit nothing so the statement still parses.
    """
    stripped = prefix.rstrip()
    if not stripped or stripped[-1] in "(,=":
        return _DYN
    last_word = stripped.split()[-1].upper()
    return _DYN if last_word in _KEYWORDS_BEFORE_EXPR else ""


class _Resolver:
    def __init__(
        self,
        consts: dict[str, str],
        local_strs: dict[str, str],
        local_lists: dict[str, list[str]],
    ) -> None:
        self.consts = consts
        self.local_strs = local_strs
        self.local_lists = local_lists

    def resolve(self, node: ast.expr) -> str | None:  # noqa: PLR0911
        """Return the SQL text for ``node`` or ``None`` when not string-like."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return self._joined(node)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.resolve(node.left)
            right = self.resolve(node.right)
            if left is None and right is None:
                return None
            return (left if left is not None else _DYN) + (right if right is not None else _DYN)
        if isinstance(node, ast.Name):
            if node.id in self.local_strs:
                return self.local_strs[node.id]
            return self.consts.get(node.id)
        if isinstance(node, ast.Call):
            return self._join_call(node)
        return None

    def _joined(self, node: ast.JoinedStr) -> str:
        out = ""
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out += part.value
            elif isinstance(part, ast.FormattedValue):
                resolved = self.resolve(part.value)
                out += resolved if resolved is not None else _placeholder_for(out)
        return out

    def _join_call(self, node: ast.Call) -> str | None:
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "join"):
            return None
        sep = self.resolve(func.value)
        if sep is None or len(node.args) != 1:
            return None
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id in self.local_lists:
            items = self.local_lists[arg.id]
            return sep.join(items) if items else _DYN
        return _DYN


def _iter_functions(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _sorted_nodes(func: ast.AST) -> list[ast.AST]:
    nodes = [n for n in ast.walk(func) if hasattr(n, "lineno")]
    return sorted(nodes, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))


def _track_assign(node: ast.AST, resolver: _Resolver) -> None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            if isinstance(node.value, ast.List):
                resolver.local_lists[target.id] = [
                    s for s in (resolver.resolve(e) for e in node.value.elts) if s is not None
                ]
                return
            resolved = resolver.resolve(node.value)
            if resolved is not None:
                resolver.local_strs[target.id] = resolved
        elif isinstance(target, ast.Tuple):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    resolver.local_lists.setdefault(elt.id, [])
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
        if isinstance(node.value, ast.List):
            resolver.local_lists[node.target.id] = []
        else:
            resolved = resolver.resolve(node.value)
            if resolved is not None:
                resolver.local_strs[node.target.id] = resolved
    elif (
        isinstance(node, ast.AugAssign)
        and isinstance(node.op, ast.Add)
        and isinstance(node.target, ast.Name)
        and node.target.id in resolver.local_strs
    ):
        extra = resolver.resolve(node.value)
        resolver.local_strs[node.target.id] += extra if extra is not None else _DYN


def _track_list_mutation(node: ast.AST, resolver: _Resolver) -> None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return
    owner = node.func.value
    if not (isinstance(owner, ast.Name) and owner.id in resolver.local_lists):
        return
    if node.func.attr == "append" and len(node.args) == 1:
        value = resolver.resolve(node.args[0])
        if value is not None:
            resolver.local_lists[owner.id].append(value)
    elif node.func.attr == "insert" and len(node.args) == 2:
        value = resolver.resolve(node.args[1])
        if value is not None:
            resolver.local_lists[owner.id].insert(0, value)


def _sql_sites(
    func: ast.FunctionDef | ast.AsyncFunctionDef, consts: dict[str, str]
) -> list[_SqlSite]:
    resolver = _Resolver(consts, {}, {})
    sites: list[_SqlSite] = []
    for node in _sorted_nodes(func):
        _track_assign(node, resolver)
        _track_list_mutation(node, resolver)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _EXECUTE_METHODS
            and node.args
        ):
            sql = resolver.resolve(node.args[0])
            if sql is not None:
                sites.append(_SqlSite(line=node.lineno, sql=" ".join(sql.split())))
    return sites


# --------------------------------------------------------------------------
# SQL side: check user-id scoping with sqlglot
# --------------------------------------------------------------------------

_QueryNode = exp.Select | exp.Update | exp.Delete | exp.Insert


def _owner(node: exp.Expression) -> exp.Expression | None:
    return node.find_ancestor(exp.Select, exp.Update, exp.Delete, exp.Insert)


def _primary_table(query: exp.Expression) -> exp.Table | None:
    if isinstance(query, exp.Select):
        from_ = query.args.get("from") or query.args.get("from_")
        target = from_.this if from_ is not None else None
    else:
        target = query.this
    return target if isinstance(target, exp.Table) else None


def _scope_columns(query: exp.Expression) -> list[exp.Column]:
    """Columns compared with ``=`` inside ``query``'s own WHERE / JOIN ON."""
    cols: list[exp.Column] = []
    for eq in query.find_all(exp.EQ):
        if _owner(eq) is not query:
            continue
        if eq.find_ancestor(exp.Where, exp.Join) is None:
            continue
        cols.extend(side for side in (eq.this, eq.expression) if isinstance(side, exp.Column))
    return cols


def _is_scoped(table: exp.Table, query: exp.Expression) -> bool:
    keys = {"user_id"} | ALTERNATE_SCOPE_KEYS.get(table.name, frozenset())
    alias = table.alias_or_name
    primary = _primary_table(query)
    for col in _scope_columns(query):
        if col.name not in keys:
            continue
        if col.table == alias or (not col.table and primary is table):
            return True
    return False


def _scoped_parent_present(statement: exp.Expression, parent: str) -> bool:
    for table in statement.find_all(exp.Table):
        query = _owner(table)
        if table.name == parent and query is not None and _is_scoped(table, query):
            return True
    return False


def _insert_columns(insert: exp.Insert) -> list[str] | None:
    target = insert.this
    if isinstance(target, exp.Schema):
        return [c.name for c in target.expressions]
    return None


def _insert_target(insert: exp.Insert) -> str:
    target = insert.this
    table = target.this if isinstance(target, exp.Schema) else target
    return table.name if isinstance(table, exp.Table) else ""


def _check_statement(statement: exp.Expression, fn_has_scoped_parent: set[str]) -> list[str]:
    problems: list[str] = []
    for insert in statement.find_all(exp.Insert):
        name = _insert_target(insert)
        if name in USER_OWNED_TABLES and "user_id" not in (_insert_columns(insert) or []):
            problems.append(f"INSERT into user-owned table {name!r} without user_id column")
        if name in FK_SCOPED_TABLES and FK_SCOPED_TABLES[name] not in fn_has_scoped_parent:
            problems.append(
                f"INSERT into FK-scoped table {name!r} without a user-scoped "
                f"ownership check on {FK_SCOPED_TABLES[name]!r} in the same function"
            )
    for table in statement.find_all(exp.Table):
        query = _owner(table)
        if query is None or isinstance(query, exp.Insert):
            continue
        if table.name in USER_OWNED_TABLES and not _is_scoped(table, query):
            problems.append(f"{query.key.upper()} on user-owned table {table.name!r} lacks user_id")
        parent = FK_SCOPED_TABLES.get(table.name)
        if parent is not None and not _scoped_parent_present(statement, parent):
            problems.append(
                f"{query.key.upper()} on FK-scoped table {table.name!r} lacks a "
                f"user-scoped reference to {parent!r}"
            )
    return problems


def _parse(sql: str) -> list[exp.Expression]:
    return [s for s in sqlglot.parse(sql, read="sqlite") if isinstance(s, exp.Expression)]


def check_source(
    source: str,
    path: str,
    allowlist: Iterable[tuple[str, str]] = (),
) -> list[Violation]:
    """Return every user-scoping violation in ``source`` (a Python module)."""
    allowed = set(allowlist)
    tree = ast.parse(source)
    consts = _module_constants(tree)
    violations: list[Violation] = []
    for func in _iter_functions(tree):
        if (path, func.name) in allowed:
            continue
        parsed: list[tuple[_SqlSite, list[exp.Expression]]] = []
        for site in _sql_sites(func, consts):
            try:
                parsed.append((site, _parse(site.sql)))
            except sqlglot.errors.ParseError as err:
                violations.append(
                    Violation(path, site.line, func.name, f"unparseable SQL ({err})", site.sql)
                )
        scoped_parents = {
            parent
            for _, statements in parsed
            for statement in statements
            for parent in FK_SCOPED_TABLES.values()
            if _scoped_parent_present(statement, parent)
        }
        for site, statements in parsed:
            for statement in statements:
                violations.extend(
                    Violation(path, site.line, func.name, _DYN_TABLE_MESSAGE, site.sql)
                    for table in statement.find_all(exp.Table)
                    if table.name == _DYN
                )
                violations.extend(
                    Violation(path, site.line, func.name, problem, site.sql)
                    for problem in _check_statement(statement, scoped_parents)
                )
    return violations


def check_paths(
    paths: Iterable[Path], root: Path, allowlist: Iterable[tuple[str, str]] = ()
) -> list[Violation]:
    allowed = tuple(allowlist)
    out: list[Violation] = []
    for path in sorted(paths):
        rel = str(path.relative_to(root))
        out.extend(check_source(path.read_text(encoding="utf-8"), rel, allowed))
    return out


# --------------------------------------------------------------------------
# OwnedTable specs (T-Q284, ADR-0130 amendment 2026-11-22)
# --------------------------------------------------------------------------

_SHARED_MODULE = "budget_planner.repositories._shared"
_SPEC_FIELDS = ("table", "entity_type", "columns", "hydrate", "order_by")
_SAMPLE_KEYS = ("id",)
_SAMPLE_EXTRA_KEYS = ("account_id",)
_DEFAULT_ORDER_BY = "id ASC"


@dataclass(frozen=True, slots=True)
class OwnedSpec:
    """One statically collected ``OwnedTable(...)`` call."""

    path: str
    line: int
    table: str
    columns: str
    order_by: str


Renderer = Callable[[OwnedSpec], list[str]]


def default_renderers(shared: Any = None) -> dict[str, Renderer]:
    """One renderer per ``*_sql`` builder of ``repositories/_shared`` (the runtime builders)."""
    mod = shared if shared is not None else importlib.import_module(_SHARED_MODULE)
    both = (False, True)
    return {
        "find_sql": lambda s: [
            mod.find_sql(s.table, s.columns, _SAMPLE_KEYS, include_deleted=d) for d in both
        ],
        "list_sql": lambda s: [
            mod.list_sql(s.table, s.columns, keys, s.order_by, include_deleted=d)
            for d in both
            for keys in ((), _SAMPLE_EXTRA_KEYS)
        ],
        "recently_deleted_sql": lambda s: [mod.recently_deleted_sql(s.table, s.columns)],
        "insert_sql": lambda s: [mod.insert_sql(s.table, ("name",))],
        "update_sql": lambda s: [mod.update_sql(s.table, ("name",))],
        "soft_delete_sql": lambda s: [mod.soft_delete_sql(s.table)],
        "undelete_sql": lambda s: [mod.undelete_sql(s.table)],
    }


def builder_names(shared_source: str) -> set[str]:
    """Public ``*_sql`` builder functions defined at the top level of ``_shared``."""
    return {
        f.name
        for f in _iter_functions(ast.parse(shared_source))
        if f.name.endswith("_sql") and not f.name.startswith("_")
    }


def check_builders_covered(shared_source: str, renderers: dict[str, Renderer]) -> list[str]:
    """Builders without a renderer (or renderers without a builder) are a silent skip: report."""
    defined = builder_names(shared_source)
    missing = [
        f"SQL builder {n!r} has no guard renderer" for n in sorted(defined - renderers.keys())
    ]
    stale = [f"guard renderer {n!r} has no SQL builder" for n in sorted(renderers.keys() - defined)]
    return missing + stale


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Subscript):
        func = func.value
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def _spec_arg(
    resolver: _Resolver, args: dict[str, ast.expr], name: str, default: str
) -> str | None:
    return resolver.resolve(args[name]) if name in args else default


def collect_owned_specs(source: str, path: str) -> tuple[list[OwnedSpec], list[Violation]]:
    """Statically collect every ``OwnedTable(...)`` call; unresolvable ones are violations."""
    tree = ast.parse(source)
    resolver = _Resolver(_module_constants(tree), {}, {})
    specs: list[OwnedSpec] = []
    problems: list[Violation] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _call_name(node.func) == "OwnedTable"):
            continue
        args: dict[str, ast.expr] = dict(zip(_SPEC_FIELDS, node.args, strict=False))
        args.update({kw.arg: kw.value for kw in node.keywords if kw.arg})
        table = _spec_arg(resolver, args, "table", "")
        columns = _spec_arg(resolver, args, "columns", "")
        order = _spec_arg(resolver, args, "order_by", _DEFAULT_ORDER_BY)
        if not table or not columns or order is None or _DYN in (table, columns, order):
            problems.append(
                Violation(path, node.lineno, "OwnedTable", "spec is not statically resolvable", "")
            )
            continue
        specs.append(OwnedSpec(path, node.lineno, table, columns, order))
    return specs, problems


def _check_rendered(sql: str, table: str) -> list[str]:
    try:
        statements = _parse(sql)
    except sqlglot.errors.ParseError as err:
        return [f"unparseable rendered SQL ({err})"]
    if not any(t.name == table for s in statements for t in s.find_all(exp.Table)):
        return [f"rendered SQL does not touch table {table!r}"]
    return [p for s in statements for p in _check_statement(s, set())]


def check_owned_specs(
    specs: Iterable[OwnedSpec], renderers: dict[str, Renderer]
) -> list[Violation]:
    """Render every builder for every spec's table and apply the user_id-predicate check."""
    out: list[Violation] = []
    for spec in specs:
        if spec.table not in USER_OWNED_TABLES:
            out.append(
                Violation(spec.path, spec.line, "OwnedTable", f"unknown table {spec.table!r}", "")
            )
            continue
        for name, render in renderers.items():
            for sql in render(spec):
                flat = " ".join(sql.split())
                out.extend(
                    Violation(spec.path, spec.line, name, f"table {spec.table!r}: {problem}", flat)
                    for problem in _check_rendered(flat, spec.table)
                )
    return out


def check_owned_tables(
    paths: Iterable[Path], root: Path, renderers: dict[str, Renderer] | None = None
) -> list[Violation]:
    """Collect specs across ``paths`` and check every generated statement per table."""
    specs: list[OwnedSpec] = []
    out: list[Violation] = []
    for path in sorted(paths):
        found, problems = collect_owned_specs(
            path.read_text(encoding="utf-8"), str(path.relative_to(root))
        )
        specs.extend(found)
        out.extend(problems)
    out.extend(check_owned_specs(specs, renderers or default_renderers()))
    return out
