#!/usr/bin/env python3
"""Механические проверки архитектуры по каталогу правил.

Находит то, что ищется без модели: импорты через границы слоёв и доменов,
commit() в контроллерах, клиенты вне infrastructure, provides= в ioc и т.п.
То, что требует суждения, проверяет агент по чек-листу скилла.

    python3 arch_check.py [--root SRC] [--diff BASE] [--legacy MOD ...] [--json]

Подавить находку в строке: `# arch-ignore[TX-01]: причина` (причина обязательна).
Код выхода: 1 — есть ошибки (правила уровня «обязательно»), иначе 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

LAYERS = ("domain", "application", "adapters", "controllers")
DOMAIN_FILES = ("ioc.py", "public.py")
DUMP_DIRS = {"common", "utils", "helpers", "shared", "misc"}

# Уровень правила: error — «обязательно», warning — «по умолчанию».
SEVERITY = {
    "STR-02": "warning", "STR-03": "error", "STR-04": "error",
    "DEP-02": "error", "DEP-03": "error", "DEP-04": "error",
    "DOM-03": "error", "APP-02": "error", "APP-06": "error",
    "TX-01": "warning", "ADP-01": "error", "ADP-03": "error",
    "DI-02": "error", "DI-04": "error", "DB-01": "error", "DB-02": "error",
    "TST-01": "warning", "LEG-01": "error", "LEG-04": "error", "TYP-01": "error",
    # поведение сервиса: эвристики — warning, однозначные — error
    "API-04": "warning", "SEC-03": "warning", "SEC-04": "error", "SEC-05": "error",
    "SEC-10": "error", "PERF-01": "warning", "PERF-05": "warning", "PERF-06": "warning",
    "REL-06": "warning", "OBS-01": "warning", "OBS-03": "warning", "OBS-04": "error",
    "OPS-01": "error", "OPS-02": "warning", "OPS-04": "warning",
    "ARCH": "warning",
}

SQL_CALLS = {"execute", "executemany", "fetch", "fetchrow", "fetchval", "text", "exec_driver_sql"}
QUERY_CALLS = {"execute", "fetch", "fetchrow", "fetchval", "scalar", "scalars", "scalar_one", "scalar_one_or_none"}
SECRET_NAME = re.compile(r"(password|passwd|secret|token|api_?key|private_?key)", re.IGNORECASE)
SENSITIVE_LOG = re.compile(r"(password|passwd|secret|token|authorization|cookie|api_?key)", re.IGNORECASE)
MONEY_NAME = re.compile(r"(^|_)(price|amount|sum|cost|balance|total|fee|money|payout)(_|$)", re.IGNORECASE)
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical"}
ROUTE_METHODS = {"get"}
PAGING_ARGS = {"limit", "cursor", "page", "page_size", "per_page", "after", "offset"}

INFRA_LIBS = {
    "sqlalchemy", "asyncpg", "psycopg", "psycopg2", "aiosqlite", "alembic",
    "httpx", "aiohttp", "requests", "redis", "aio_pika", "faststream",
    "fastapi", "starlette", "aiogram", "dishka", "pydantic", "pydantic_settings",
    "boto3", "aiobotocore", "celery", "kafka", "aiokafka",
}
DB_LIBS = {"sqlalchemy", "asyncpg", "psycopg", "psycopg2", "aiosqlite"}
HTTP_LIBS = {"httpx", "aiohttp", "requests"}
CLIENT_CTORS = {"AsyncClient", "Client", "ClientSession", "create_pool", "create_async_engine"}
GENERIC_EXC = {"ValueError", "Exception", "KeyError", "LookupError", "TypeError"}
DDL = re.compile(r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|TYPE|SCHEMA)\b", re.IGNORECASE)
ALLOWED_IMPORT_RE = re.compile(r"^\s*([\w.*]+)\s*->\s*([\w.*]+)\s*$")
VALUE_BASES = {"Enum", "StrEnum", "IntEnum", "Flag", "IntFlag", "NamedTuple", "Exception"}
IGNORE_RE = re.compile(r"#\s*arch-ignore\[([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)\]\s*(:\s*\S.*)?")
TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore(\[[^\]]+\])?(.*)$")


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    message: str


@dataclass
class Domain:
    name: str
    path: Path
    module: str  # app.assets


class Checker:
    def __init__(self, root: Path, repo: Path, legacy: list[str]) -> None:
        self.root = root
        self.repo = repo
        self.legacy = legacy
        self.import_root = self._import_root(root)
        self.domains = self._find_domains()
        self.findings: list[Finding] = []
        self.allowed_imports = _read_ignore_imports(repo)
        self._value_cache: dict[tuple[str, str], bool] = {}

    # --- обнаружение -----------------------------------------------------

    @staticmethod
    def _import_root(root: Path) -> Path:
        # Первый родитель без __init__.py — то, что лежит в sys.path.
        p = root
        while (p / "__init__.py").exists() and p.parent != p:
            p = p.parent
        return p

    def module_of(self, path: Path) -> str:
        rel = path.relative_to(self.import_root).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    def _find_domains(self) -> list[Domain]:
        found: dict[Path, Domain] = {}
        for layer_dir in self.root.rglob("domain"):
            if not layer_dir.is_dir() or _skipped(layer_dir):
                continue
            d = layer_dir.parent
            if sum((d / layer).is_dir() for layer in LAYERS) >= 2:
                found[d] = Domain(d.name, d, self.module_of(d / "__init__.py"))
        return sorted(found.values(), key=lambda x: str(x.path))

    def domain_of(self, path: Path) -> tuple[Domain, str | None] | None:
        for d in self.domains:
            if d.path in path.parents:
                rel = path.relative_to(d.path).parts
                layer = rel[0] if rel and rel[0] in LAYERS else None
                return d, layer
        return None

    # --- вывод -----------------------------------------------------------

    def add(self, rule: str, path: Path, line: int, message: str, lines: list[str] | None = None) -> None:
        if lines is not None and 0 < line <= len(lines):
            m = IGNORE_RE.search(lines[line - 1])
            if m and rule in [r.strip() for r in m.group(1).split(",")]:
                if m.group(2):
                    return
                message += " (arch-ignore без причины)"
        self.findings.append(
            Finding(rule, SEVERITY.get(rule, "warning"), str(path.relative_to(self.repo)), line, message)
        )

    # --- проверки --------------------------------------------------------

    def check_layout(self) -> None:
        for d in self.domains:
            missing = [x for x in LAYERS if not (d.path / x).is_dir()]
            missing += [f for f in DOMAIN_FILES if not (d.path / f).exists()]
            if missing:
                self.add("STR-02", d.path, 0, f"домен {d.name}: нет {', '.join(missing)}")
        for p in self.root.rglob("*"):
            if p.is_dir() and p.name in DUMP_DIRS and not _skipped(p):
                self.add("STR-04", p, 0, f"каталог-свалка {p.name}/ — перенести в infrastructure/<назначение>/ или домен")

    def check_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            self.add("ARCH", path, exc.lineno or 0,
                     f"не разбирается ({exc.msg}) — запусти скрипт Python-ом проекта: uv run python …")
            return
        owner = self.domain_of(path)
        domain, layer = owner if owner else (None, None)
        parts = set(path.relative_to(self.root).parts)
        in_infra = "infrastructure" in parts
        in_migrations = "migrations" in parts or "alembic" in parts
        in_adapters = layer == "adapters"
        module = self.module_of(path)
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]

        self._check_empty(path, tree)
        self._check_type_ignore(path, lines)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for target, top in _imports(node, package):
                    self._check_import(path, node.lineno, lines, target, top, domain, layer,
                                       in_infra, in_migrations, in_adapters)
            elif isinstance(node, ast.Raise) and layer in ("application", "adapters"):
                name = _raised_name(node)
                if name in GENERIC_EXC:
                    self.add("DOM-03", path, node.lineno, f"raise {name} — нужно доменное исключение", lines)
            elif isinstance(node, ast.Call):
                self._check_call(path, node, lines, layer, in_infra, path.name == "ioc.py")
            elif isinstance(node, ast.Global):
                self.add("DI-04", path, node.lineno, "global — состояние через контейнер", lines)
            elif isinstance(node, ast.AsyncFunctionDef):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and _dotted(sub.func) == "time.sleep":
                        self.add("ADP-03", path, sub.lineno, "time.sleep в async — блокирует event loop", lines)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and not in_migrations:
                if DDL.search(node.value):
                    self.add("DB-02", path, node.lineno, "DDL в коде приложения — только миграции", lines)

        if layer == "application":
            self._check_interactor_returns(path, tree, lines, domain)
        if not in_migrations:
            self._check_service_behaviour(path, tree, lines)

    # --- поведение сервиса: API, SEC, PERF, REL, OBS, OPS -------------------

    def _check_service_behaviour(self, path: Path, tree: ast.Module, lines: list[str]) -> None:
        in_tests = "tests" in path.parts or path.name.startswith("test_")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                dotted = _dotted(node.func)
                # SEC-05: SQL, собранный из строк
                if name in SQL_CALLS and node.args and _is_built_string(node.args[0]):
                    self.add("SEC-05", path, node.lineno, f"{name}() со строкой, собранной из значений — только параметры", lines)
                # OPS-01: время без зоны
                if dotted in ("datetime.now", "datetime.datetime.now") and not node.args and not node.keywords:
                    self.add("OPS-01", path, node.lineno, "datetime.now() без зоны — datetime.now(UTC)", lines)
                elif dotted.endswith("datetime.utcnow") or dotted.endswith("datetime.utcfromtimestamp"):
                    self.add("OPS-01", path, node.lineno, f"{dotted}() — naive-время; нужен datetime.now(UTC)", lines)
                elif dotted in ("date.today", "datetime.date.today"):
                    self.add("OPS-01", path, node.lineno, "date.today() — дата в локальной зоне сервера; зона явно", lines)
                # SEC-10: CORS и debug
                if any(k.arg == "allow_origins" and _is_star_list(k.value) for k in node.keywords):
                    self.add("SEC-10", path, node.lineno, 'allow_origins=["*"] — явный список origin', lines)
                if any(k.arg == "debug" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    self.add("SEC-10", path, node.lineno, "debug=True — в проде выключен", lines)
                # PERF-05: gather по неограниченному списку
                if name == "gather" and any(isinstance(a, ast.Starred) and isinstance(a.value, (ast.ListComp, ast.GeneratorExp)) for a in node.args):
                    self.add("PERF-05", path, node.lineno, "gather(*[...]) по списку — ограничить семафором или пачками", lines)
                # OBS-01: print
                if isinstance(node.func, ast.Name) and node.func.id == "print" and not in_tests:
                    self.add("OBS-01", path, node.lineno, "print в коде сервиса — логгер", lines)
                # OBS-03: чувствительное в логах
                if isinstance(node.func, ast.Attribute) and node.func.attr in LOG_METHODS and _mentions(node, SENSITIVE_LOG):
                    self.add("OBS-03", path, node.lineno, "в лог уходит password/token/secret/authorization — убрать или маскировать", lines)
            elif isinstance(node, ast.ExceptHandler):
                broad = node.type is None or _dotted(node.type) in ("Exception", "BaseException")
                if broad and all(isinstance(b, ast.Pass) or (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant)) or isinstance(b, ast.Continue) for b in node.body):
                    self.add("OBS-04", path, node.lineno, "исключение проглочено (except … : pass) — лог или обработка", lines)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and not in_tests:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                for t in targets:
                    tname = t.id if isinstance(t, ast.Name) else t.attr if isinstance(t, ast.Attribute) else ""
                    if SECRET_NAME.search(tname) and isinstance(value, ast.Constant) and isinstance(value.value, str) \
                            and _looks_secret(tname, value.value):
                        self.add("SEC-04", path, node.lineno, f"секрет в коде ({tname}) — из окружения, SecretStr", lines)
                if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    self._check_money(path, node.target.id, node.annotation, node.lineno, lines)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in node.args.args + node.args.kwonlyargs:
                    if arg.annotation is not None:
                        self._check_money(path, arg.arg, arg.annotation, node.lineno, lines)
                if isinstance(node, ast.AsyncFunctionDef):
                    self._check_async_body(path, node, lines)
                self._check_route(path, node, lines)
            elif isinstance(node, ast.Compare) and any(isinstance(o, (ast.Eq, ast.NotEq)) for o in node.ops):
                names = [_dotted(x) for x in [node.left, *node.comparators]]
                if any(re.search(r"(signature|hmac|digest|token_hash|expected_sign)", n, re.IGNORECASE) for n in names):
                    self.add("SEC-03", path, node.lineno, "подпись/токен сравнивается через == — hmac.compare_digest", lines)
            elif isinstance(node, ast.Name) and node.id == "BackgroundTasks":
                self.add("PERF-06", path, node.lineno, "BackgroundTasks теряет задачу при перезапуске — только для неважного", lines)

    def _check_money(self, path: Path, name: str, annotation: ast.expr, lineno: int, lines: list[str]) -> None:
        if MONEY_NAME.search(name) and any(isinstance(n, ast.Name) and n.id == "float" for n in ast.walk(annotation)):
            self.add("OPS-02", path, lineno, f"{name}: float для денег — Decimal или целые минорные единицы", lines)

    def _check_async_body(self, path: Path, fn: ast.AsyncFunctionDef, lines: list[str]) -> None:
        for node in ast.walk(fn):
            if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
                periodic = any(isinstance(n, ast.Call) and _call_name(n) in ("sleep", "wait_for", "wait") for n in ast.walk(node))
                if periodic and not any(isinstance(b, ast.Try) for b in node.body):
                    self.add("REL-06", path, node.lineno, "while True без try в теле — сбой итерации остановит цикл", lines)
            if isinstance(node, (ast.For, ast.AsyncFor)) and not (isinstance(node.target, ast.Name) and node.target.id == "_"):
                for sub in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                    if isinstance(sub, ast.Await) and isinstance(sub.value, ast.Call):
                        func = sub.value.func
                        recv = _dotted(func.value).lower() if isinstance(func, ast.Attribute) else ""
                        if _call_name(sub.value) in QUERY_CALLS or re.search(r"(gateway|view|repo|session|conn)$", recv):
                            self.add("PERF-01", path, sub.lineno, "запрос к БД в цикле — один запрос на все строки (N+1)", lines)
                            break

    def _check_route(self, path: Path, fn: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> None:
        is_get = any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_METHODS
            and _dotted(d.func.value).split(".")[-1] in ("router", "app", "api", "admin_router") or
            (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ROUTE_METHODS
             and "router" in _dotted(d.func.value).lower())
            for d in fn.decorator_list
        )
        if not is_get or fn.returns is None:
            return
        ret = fn.returns
        returns_list = isinstance(ret, ast.Subscript) and _dotted(ret.value) in ("list", "List", "Sequence", "typing.List")
        if not returns_list:
            return
        args = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        if not args & PAGING_ARGS:
            self.add("API-04", path, fn.lineno, f"{fn.name}: список без limit/cursor — пагинация с первого дня", lines)

    def check_migrations(self, files: list[Path]) -> None:
        """OPS-04: только новые миграции (режим --diff) — старые уже применены."""
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            changes_schema = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = _call_name(node)
                    kw = {k.arg: k.value for k in node.keywords}
                    if name in ("create_index",) and "postgresql_concurrently" not in kw:
                        self.add("OPS-04", path, node.lineno, "create_index без postgresql_concurrently — блокирует запись в таблицу", lines)
                    if name == "add_column" and any(
                        isinstance(a, ast.Call) and _call_name(a) == "Column"
                        and any(k.arg == "nullable" and isinstance(k.value, ast.Constant) and k.value.value is False for k in a.keywords)
                        and not any(k.arg == "server_default" for k in a.keywords)
                        for a in node.args
                    ):
                        self.add("OPS-04", path, node.lineno, "add_column NOT NULL без server_default — сначала nullable, потом бэкфилл", lines)
                    if name == "alter_column" and isinstance(kw.get("nullable"), ast.Constant) and kw["nullable"].value is False:
                        self.add("OPS-04", path, node.lineno, "SET NOT NULL на живой таблице — через CHECK NOT VALID → VALIDATE", lines)
                    if name == "alter_column" and "new_column_name" in kw or name == "rename_table":
                        self.add("OPS-04", path, node.lineno, "переименование ломает работающую версию — новая колонка + двойная запись", lines)
                    if name in ("add_column", "alter_column", "drop_column", "create_index", "drop_index",
                                "create_foreign_key", "rename_table", "execute"):
                        changes_schema = True
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    sql = node.value
                    if re.search(r"\bCREATE\s+(UNIQUE\s+)?INDEX\b(?!\s+CONCURRENTLY)", sql, re.IGNORECASE):
                        self.add("OPS-04", path, node.lineno, "CREATE INDEX без CONCURRENTLY — блокирует запись", lines)
                    if re.search(r"\bRENAME\s+(COLUMN|TO)\b", sql, re.IGNORECASE):
                        self.add("OPS-04", path, node.lineno, "RENAME ломает работающую версию — expand/contract", lines)
                    if re.search(r"\bSET\s+NOT\s+NULL\b", sql, re.IGNORECASE):
                        self.add("OPS-04", path, node.lineno, "SET NOT NULL — через CHECK NOT VALID → VALIDATE", lines)
                    if re.search(r"\bADD\s+COLUMN\b[^;]*\bNOT\s+NULL\b(?![^;]*\bDEFAULT\b)", sql, re.IGNORECASE):
                        self.add("OPS-04", path, node.lineno, "ADD COLUMN NOT NULL без DEFAULT — сначала nullable", lines)
            if changes_schema and "lock_timeout" not in text:
                self.add("OPS-04", path, 0, "миграция меняет схему без SET lock_timeout")

    def _allowed(self, importer: str, target: str) -> bool:
        """Исключение уже записано в ignore_imports у import-linter."""
        return any(_glob(a, importer) and (_glob(b, target) or any(_glob(b, t) for t in _prefixes(target)))
                   for a, b in self.allowed_imports)

    def _check_import(self, path: Path, lineno: int, lines: list[str], target: str, top: str,
                      domain: Domain | None, layer: str | None,
                      in_infra: bool, in_migrations: bool, in_adapters: bool) -> None:
        importer = self.module_of(path)
        stdlib = top in sys.stdlib_module_names or top == "__future__"
        if top in {"requests"}:
            self.add("ADP-03", path, lineno, "requests — синхронный HTTP; нужен async-клиент", lines)

        target_owner = next((d for d in self.domains if target == d.module or target.startswith(d.module + ".")), None)

        if domain is not None and target_owner is not None and target_owner is not domain:
            rest = target[len(target_owner.module):].lstrip(".")
            if rest and rest.split(".")[0] != "public" and not self._allowed(importer, target):
                self.add("DEP-04", path, lineno,
                         f"импорт внутренностей домена {target_owner.name} ({target}) — только {target_owner.module}.public", lines)

        for legacy in self.legacy:
            if target == legacy or target.startswith(legacy + "."):
                if domain is not None and not path.name.startswith("legacy") and not self._allowed(importer, target):
                    self.add("LEG-04", path, lineno,
                             f"импорт старого модуля {target} вне adapters/legacy_*.py", lines)

        if layer == "domain":
            own = domain is not None and (target == domain.module + ".domain" or target.startswith(domain.module + ".domain."))
            if not stdlib and not own:
                self.add("DEP-02", path, lineno, f"domain импортирует {target} — только стандартная библиотека и свой domain", lines)
            return

        if layer == "application":
            if top in INFRA_LIBS:
                self.add("DEP-03", path, lineno, f"application импортирует {top} — через порт", lines)
            elif ".infrastructure" in "." + target or (domain and target.startswith(domain.module + ".adapters")) \
                    or (domain and target.startswith(domain.module + ".controllers")):
                self.add("DEP-03", path, lineno, f"application импортирует внешний слой {target}", lines)

        if top in DB_LIBS and not (in_adapters or in_infra or in_migrations or path.name == "ioc.py"):
            self.add("DB-01", path, lineno, f"{top} вне adapters/ и infrastructure/", lines)
        if top in HTTP_LIBS and not (in_adapters or in_infra or path.name == "ioc.py"):
            self.add("APP-06", path, lineno, f"{top} вне adapters/ и infrastructure/ — внешний сервис через порт", lines)

    def _check_call(self, path: Path, node: ast.Call, lines: list[str], layer: str | None,
                    in_infra: bool, is_ioc: bool) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "commit" and layer in ("controllers", "adapters"):
            self.add("TX-01", path, node.lineno, f"commit() в {layer}/ — коммитит сценарий", lines)
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name in CLIENT_CTORS and not in_infra and not is_ioc:
            self.add("ADP-01", path, node.lineno, f"{name}(...) вне infrastructure/ — клиент один на процесс", lines)
        if is_ioc and name in ("provide", "alias") and any(k.arg == "provides" for k in node.keywords):
            self.add("DI-02", path, node.lineno, "provides= — отдавать адаптер функцией с типом-протоколом", lines)

    def _check_interactor_returns(self, path: Path, tree: ast.Module, lines: list[str], domain: Domain | None) -> None:
        package = self.module_of(path).rpartition(".")[0]
        domain_names: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            for target, _ in _imports(node, package)[:1]:
                if ".domain" not in "." + target:
                    continue
                for a in node.names:
                    if a.name[:1].isupper() and not self._is_value_class(target, a.name):
                        domain_names.add(a.asname or a.name)
        if not domain_names:
            return
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            if not cls.name.endswith(("Interactor", "Service")):
                continue
            for fn in cls.body:
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and not fn.name.startswith("_") and fn.returns:
                    used = {n.id for n in ast.walk(fn.returns) if isinstance(n, ast.Name)}
                    leaked = used & domain_names
                    if leaked:
                        self.add("APP-02", path, fn.lineno,
                                 f"{cls.name}.{fn.name} возвращает доменную модель {', '.join(sorted(leaked))} — нужен Info", lines)

    def _is_value_class(self, module: str, name: str) -> bool:
        """Enum, NamedTuple, исключение или frozen dataclass — неизменяемое значение, его отдавать можно."""
        key = (module, name)
        if key in self._value_cache:
            return self._value_cache[key]
        result = False
        base = self.import_root.joinpath(*module.split("."))
        for file in (base.with_suffix(".py"), base / "__init__.py"):
            if not file.exists():
                continue
            try:
                tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                result = True  # не разобрать — не обвинять
                break
            for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name):
                bases = {_dotted(b).rpartition(".")[2] for b in cls.bases}
                frozen = any(
                    isinstance(d, ast.Call) and _dotted(d.func).endswith("dataclass")
                    and any(k.arg == "frozen" and isinstance(k.value, ast.Constant) and k.value.value for k in d.keywords)
                    for d in cls.decorator_list
                )
                result = frozen or bool(bases & VALUE_BASES) or any(b.endswith(("Enum", "Error")) for b in bases)
            for node in tree.body:  # Alias = A | B — проверить части
                if isinstance(node, (ast.Assign, ast.TypeAlias)) and any(
                    isinstance(t, ast.Name) and t.id == name for t in getattr(node, "targets", [getattr(node, "name", None)])
                ):
                    result = True
            break
        self._value_cache[key] = result
        return result

    def _check_empty(self, path: Path, tree: ast.Module) -> None:
        if path.name == "__init__.py":
            return
        body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        if all(isinstance(n, ast.Pass) for n in body):
            self.add("STR-03", path, 1, "пустой модуль-заготовка")

    def _check_type_ignore(self, path: Path, lines: list[str]) -> None:
        for i, line in enumerate(lines, 1):
            m = TYPE_IGNORE_RE.search(line)
            if not m:
                continue
            code, rest = m.group(1), m.group(2).strip()
            if not code or not rest.lstrip("#").strip():
                self.add("TYP-01", path, i, "type: ignore без [кода] и комментария «почему»", lines)

    def check_domain_tests(self, tests: Path) -> None:
        if not tests.is_dir():
            return
        corpus = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in tests.rglob("*.py"))
        for d in self.domains:
            for p in sorted((d.path / "domain").rglob("*.py")):
                if p.name in ("__init__.py", "exceptions.py", "events.py"):
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
                if not re.search(r"^\s*(async\s+)?def\s+\w|^\s+def\s+\w", text, re.MULTILINE):
                    continue
                mod = self.module_of(p)
                if mod not in corpus and f"{d.name}.domain.{p.stem}" not in corpus:
                    self.add("TST-01", p, 0, f"правила {mod} без модульных тестов")

    def check_legacy_growth(self, base: str) -> None:
        if not self.legacy:
            return
        out = _git(self.repo, "diff", "--numstat", f"{base}...HEAD") + _git(self.repo, "diff", "--numstat")
        for row in out.splitlines():
            added, removed, file = (row.split("\t") + ["", "", ""])[:3]
            if not added.isdigit() or not file.endswith(".py"):
                continue
            path = self.repo / file
            if not path.exists() or self.root not in path.parents:
                continue
            mod = self.module_of(path)
            if any(mod == m or mod.startswith(m + ".") for m in self.legacy) and int(added) > int(removed):
                self.add("LEG-01", path, 0, f"старый модуль растёт: +{added} −{removed} — новое писать в домене")


# --- помощники ---------------------------------------------------------------

def _skipped(p: Path) -> bool:
    return any(part.startswith(".") or part in {"__pycache__", "node_modules", "venv", ".venv", "build", "dist"}
               for part in p.parts)


def _read_ignore_imports(repo: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for name in (".importlinter", "setup.cfg", "pyproject.toml"):
        f = repo / name
        if f.exists():
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = ALLOWED_IMPORT_RE.match(line.strip().strip('",'))
                if m:
                    pairs.append((m.group(1), m.group(2)))
    return pairs


def _glob(pattern: str, module: str) -> bool:
    rx = re.escape(pattern).replace(r"\*\*", ".+").replace(r"\*", "[^.]+")
    return re.fullmatch(rx, module) is not None


def _prefixes(module: str) -> list[str]:
    parts = module.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def _imports(node: ast.Import | ast.ImportFrom, package: str) -> list[tuple[str, str]]:
    if isinstance(node, ast.Import):
        return [(a.name, a.name.split(".")[0]) for a in node.names]
    if node.level:
        parts = package.split(".") if package else []
        up = node.level - 1
        base = parts[: len(parts) - up] if up <= len(parts) else []
        target = ".".join(base + ([node.module] if node.module else []))
        results = [target] if node.module else [f"{target}.{a.name}" for a in node.names]
        return [(t, t.split(".")[0]) for t in results]
    mod = node.module or ""
    return [(mod, mod.split(".")[0])]


NOT_SECRET_SUFFIX = re.compile(r"_(PATH|URL|KEY_NAME|FIELD|HEADER|PARAM|COOKIE|PREFIX|ENV|VAR|ATTR|LABEL|TEXT|MSG)$", re.IGNORECASE)


def _looks_secret(name: str, value: str) -> bool:
    if NOT_SECRET_SUFFIX.search(name) or len(value) < 12 or any(c in value for c in " /:{}.$"):
        return False
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""


SQL_FRAGMENT = re.compile(r"(sql|condition|clause|columns|cols|where|table|order|join|fields|filter)", re.IGNORECASE)


def _is_fragment(expr: ast.expr) -> bool:
    """Подстановка, похожая на кусок SQL из кода (константа, условие), а не значение."""
    name = _dotted(expr).rpartition(".")[2]
    return bool(name) and (name.isupper() or SQL_FRAGMENT.search(name) is not None)


def _is_built_string(node: ast.expr) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) and not _is_fragment(v.value) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return _is_strlike(node.left) or _is_strlike(node.right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        return _is_strlike(node.func.value)
    return False


def _is_strlike(node: ast.expr) -> bool:
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)) or isinstance(node, ast.JoinedStr) \
        or (isinstance(node, ast.BinOp) and _is_built_string(node))


def _is_star_list(node: ast.expr) -> bool:
    return isinstance(node, (ast.List, ast.Tuple, ast.Set)) and any(
        isinstance(e, ast.Constant) and e.value == "*" for e in node.elts)


def _mentions(call: ast.Call, pattern: re.Pattern[str]) -> bool:
    for arg in [*call.args, *(k.value for k in call.keywords)]:
        for n in ast.walk(arg):
            if isinstance(n, ast.Name) and pattern.search(n.id):
                return True
            if isinstance(n, ast.Attribute) and pattern.search(n.attr):
                return True
    return any(k.arg and pattern.search(k.arg) for k in call.keywords)


def _raised_name(node: ast.Raise) -> str:
    exc = node.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    return exc.id if isinstance(exc, ast.Name) else ""


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        return ""


def _changed_files(repo: Path, base: str) -> set[Path]:
    names = _git(repo, "diff", "--name-only", f"{base}...HEAD") + _git(repo, "diff", "--name-only", "HEAD") \
        + _git(repo, "ls-files", "--others", "--exclude-standard")
    return {(repo / n).resolve() for n in names.splitlines() if n.endswith(".py")}


def _guess_root(repo: Path) -> Path:
    for candidate in (repo / "src", repo / "app"):
        if candidate.is_dir():
            return candidate
    return repo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="корень репозитория")
    ap.add_argument("--root", help="каталог с кодом (по умолчанию src/ или app/)")
    ap.add_argument("--tests", default="tests", help="каталог тестов относительно репозитория")
    ap.add_argument("--diff", metavar="BASE", help="проверять только изменения относительно ветки BASE")
    ap.add_argument("--legacy", nargs="*", default=[], help="старые модули (app.bot app.storage_pg)")
    ap.add_argument("--json", action="store_true", help="вывод JSON")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = Path(args.root).resolve() if args.root else _guess_root(repo)
    checker = Checker(root, repo, args.legacy)

    files = [p for p in root.rglob("*.py") if not _skipped(p.relative_to(repo))]
    if args.diff:
        changed = _changed_files(repo, args.diff)
        files = [p for p in files if p.resolve() in changed]
    else:
        checker.check_layout()
        checker.check_domain_tests(repo / args.tests)
    for p in files:
        mod = checker.module_of(p)
        if any(mod == m or mod.startswith(m + ".") for m in args.legacy):
            continue  # старый код не проверяется по новым правилам, только LEG-01
        checker.check_file(p)
    migrations = [p for d in ("migrations", "alembic") for p in (repo / d).rglob("*.py")
                  if (repo / d).is_dir() and not _skipped(p.relative_to(repo))]
    if args.diff:
        checker.check_legacy_growth(args.diff)
        changed = _changed_files(repo, args.diff)
        checker.check_migrations([p for p in migrations if p.resolve() in changed])

    findings = sorted(checker.findings, key=lambda f: (f.severity != "error", f.rule, f.path, f.line))
    if args.json:
        print(json.dumps({"domains": [d.module for d in checker.domains],
                          "findings": [asdict(f) for f in findings]}, ensure_ascii=False, indent=2))
    else:
        print(f"Домены ({len(checker.domains)}): {', '.join(d.module for d in checker.domains) or '—'}")
        print(f"Файлов проверено: {len(files)}")
        for f in findings:
            loc = f"{f.path}:{f.line}" if f.line else f.path
            print(f"{f.severity.upper():7} {f.rule:7} {loc}  {f.message}")
        errors = sum(f.severity == "error" for f in findings)
        print(f"Итого: {errors} ошибок, {len(findings) - errors} предупреждений")
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
