#!/usr/bin/env python3
"""Механические проверки фронтенда по каталогу правил (frontend-guide/catalog.md).

Находит то, что ищется без модели: импорты через границы слоёв и фич,
fetch мимо клиента, токены в localStorage, dangerouslySetInnerHTML, any,
подавления без причины, пустые catch и т.п. Это эвристики по тексту, не
разбор TypeScript: каждую находку агент проверяет глазами. Остальное —
ESLint, tsc и чек-лист скилла.

    python3 fe_check.py [--repo .] [--root src] [--diff BASE] [--legacy DIR ...] [--json]

Подавить находку: `// arch-ignore[FSEC-01]: причина` на строке или строкой выше
(в JSX — `{/* arch-ignore[FA11Y-01]: причина */}`). Причина обязательна.
Код выхода: 1 — есть ошибки (правила уровня «обязательно»), иначе 0.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

LAYERS = ("app", "routes", "features", "shared")       # сверху вниз (FDEP-01)
KNOWN_TOP = {*LAYERS, "test", "tests", "assets", "styles", "legacy", "mocks"}
TOP_FILES = re.compile(r"^(main\.tsx?|routeTree\.gen\.ts|vite-env\.d\.ts|.*\.css|env\.d\.ts)$")
DUMP_DIRS = {"utils", "helpers", "common", "misc"}
TOP_ONLY_DUMPS = {"components", "hooks", "services", "types"}   # свалка, если лежит прямо в src/
SKIP_DIRS = {"node_modules", "dist", "build", "coverage", ".git", "generated", ".turbo", ".next", "storybook-static"}
CODE_EXT = {".ts", ".tsx"}

# error — «обязательно», warning — «по умолчанию» или эвристика с заметной долей ложных срабатываний.
SEVERITY = {
    "FSTR-01": "warning", "FSTR-02": "error", "FSTR-03": "error", "FSTR-05": "warning",
    "FDEP-01": "error", "FDEP-02": "error", "FDEP-03": "error", "FDEP-04": "warning", "FDEP-05": "warning",
    "FCMP-02": "warning", "FCMP-04": "warning", "FCMP-05": "warning",
    "FAPI-01": "warning", "FAPI-02": "error", "FAPI-03": "warning",
    "FRTE-04": "warning",
    "FSEC-01": "error", "FSEC-02": "error", "FSEC-04": "error", "FSEC-06": "warning",
    "FSEC-08": "error", "FSEC-09": "error", "FSEC-10": "error",
    "FPERF-05": "warning", "FPERF-06": "warning",
    "FA11Y-01": "error", "FA11Y-03": "error",
    "FOBS-03": "error", "FOBS-04": "error",
    "FTST-01": "warning", "FTST-03": "warning",
    "FTS-01": "error", "FTS-02": "error", "FTS-03": "error", "FTS-04": "warning", "FTS-05": "warning",
    "FLEG-01": "error", "FLEG-02": "warning",
}

IMPORT_RE = re.compile(r"""(?:^|[\s;])(?:import|export)\s[^'"`;]*?from\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)|^\s*import\s+['"]([^'"]+)['"]""", re.M)
IGNORE_RE = re.compile(r"arch-ignore\[([A-Z0-9]+-\d+(?:\s*,\s*[A-Z0-9]+-\d+)*)\]\s*(:\s*\S.*)?")
COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*)")

FETCH_RE = re.compile(r"(?<![\w.])fetch\s*\(|\baxios\b")
KEY_INDEX_RE = re.compile(r"\bkey\s*=\s*\{\s*(?:index|idx|i|`[^`]*\$\{\s*(?:index|idx|i)\s*\}[^`]*`)\s*\}")
RESPONSE_TYPE_RE = re.compile(r"^\s*(?:export\s+)?(?:interface|type)\s+\w+(?:Response|Dto|DTO)\b")
RELOAD_RE = re.compile(r"\blocation\.reload\s*\(")
DANGER_RE = re.compile(r"dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML\s*\(|document\.write\s*\(")
STORAGE_TOKEN_RE = re.compile(r"(?:localStorage|sessionStorage)\s*\.\s*setItem\s*\([^)]*(token|jwt|auth|session|access|refresh|bearer)", re.I)
VITE_SECRET_RE = re.compile(r"\bVITE_\w*(SECRET|PRIVATE|PASSWORD|PASSWD|TOKEN|API_?KEY)\w*", re.I)
HARDCODED_SECRET_RE = re.compile(r"(sk_live_[0-9a-zA-Z]{10,}|ghp_[0-9a-zA-Z]{20,}|xox[abprs]-[0-9a-zA-Z-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
JS_URL_RE = re.compile(r"""href\s*=\s*\{?\s*['"`]\s*javascript:""", re.I)
DATA_HREF_RE = re.compile(r"\bhref\s*=\s*\{(?![^}]*safe)[^}]*\.(url|link|website|homepage|href)\b[^}]*\}", re.I)
MSG_LISTENER_RE = re.compile(r"addEventListener\s*\(\s*['\"]message['\"]|onmessage\s*=")
POST_STAR_RE = re.compile(r"postMessage\s*\([^;]*,\s*['\"]\*['\"]")
EVAL_RE = re.compile(r"(?<![\w.])eval\s*\(|\bnew\s+Function\s*\(|\bset(?:Timeout|Interval)\s*\(\s*['\"`]")
HEAVY_IMPORT = re.compile(r"""from\s+['"](moment|lodash)['"]""")
CLICK_DIV_RE = re.compile(r"<(div|span|li|td|p|img)\b(?=[^>]*\bonClick\s*=)(?![^>]*\brole\s*=)[^>]*>", re.S)
IMG_TAG_RE = re.compile(r"<img\b[^>]*?/?>", re.S)
# `.catch(() => null)` — запасное значение, не проглатывание; ловим только пустое тело.
EMPTY_CATCH_RE = re.compile(r"catch\s*(?:\([^)]*\))?\s*\{\s*\}|\.catch\s*\(\s*(?:\(\s*\w*\s*\)|\w+)\s*=>\s*\{\s*\}\s*\)")
STATIC_LIST_RE = re.compile(r"Array\.from\(\s*\{\s*length|\[\.\.\.Array\(|Array\(\d+\)")
CONSOLE_RE = re.compile(r"\bconsole\s*\.\s*(log|debug|info|trace|dir|table)\s*\(|^\s*debugger\s*;?\s*$")
ANY_RE = re.compile(r"(?::\s*any\b(?!\w)|\bas\s+any\b|<any>|\bany\[\]|Array<any>|Record<[^>]*,\s*any>)")
TS_IGNORE_RE = re.compile(r"@ts-ignore|@ts-nocheck")
TS_EXPECT_RE = re.compile(r"@ts-expect-error\s*(?:\*/)?\s*$")
ESLINT_DISABLE_RE = re.compile(r"eslint-disable(?:-next-line|-line)?\b(?P<rest>.*)")
JSON_AS_RE = re.compile(r"JSON\.parse\s*\([^;]*\)\s*as\s+(?!const\b|unknown\b)\w")
ENUM_RE = re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?(?:const\s+)?enum\s+\w+")
USE_EFFECT_RE = re.compile(r"\buseEffect\s*\(")
EFFECT_LOAD_RE = re.compile(r"(?<![\w.])fetch\s*\(|\baxios\b|\.then\s*\(|\bawait\s")
TEST_MOCK_CLIENT_RE = re.compile(r"""vi\.mock\s*\(\s*['"][^'"]*(shared/api|/client|generated)""")
FETCH_STUB_RE = re.compile(r"(?:global|globalThis|window)\.fetch\s*=|spyOn\s*\(\s*(?:global|globalThis|window)\s*,\s*['\"]fetch['\"]")


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    message: str


class Checker:
    def __init__(self, repo: Path, root: Path, legacy: list[Path]) -> None:
        self.repo = repo
        self.root = root
        self.legacy = legacy
        self.findings: list[Finding] = []
        self.feature_edges: dict[str, dict[str, tuple[Path, int]]] = {}

    # --- общее -----------------------------------------------------------

    def add(self, rule: str, path: Path, line: int, message: str, lines: list[str] | None = None) -> None:
        if lines is not None and line and _suppressed(rule, lines, line):
            return
        self.findings.append(Finding(rule, SEVERITY.get(rule, "warning"), _rel(path, self.repo), line, message))

    def is_legacy(self, path: Path) -> bool:
        return any(path == d or d in path.parents for d in self.legacy)

    def layer_of(self, path: Path) -> tuple[str | None, str | None]:
        """('features', 'assets') / ('shared', None) / (None, None) для чужого."""
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            return None, None
        if not parts or parts[0] not in LAYERS:
            return None, None
        if parts[0] == "features":
            return "features", parts[1] if len(parts) > 2 else None
        return parts[0], None

    def resolve(self, spec: str, src: Path) -> Path | None:
        if spec.startswith(("@/", "~/")):
            return self.root / spec[2:]
        if spec.startswith("."):
            return (src.parent / spec).resolve()
        return None

    # --- раскладка проекта (режим repo) ------------------------------------

    def check_layout(self) -> None:
        if not self.root.is_dir():
            self.add("FSTR-01", self.root, 0, f"нет каталога {_rel(self.root, self.repo)} — укажи --root")
            return
        for child in sorted(self.root.iterdir()):
            if child.name.startswith(".") or self.is_legacy(child):
                continue
            if child.is_dir():
                if child.name in DUMP_DIRS | TOP_ONLY_DUMPS:
                    self.add("FSTR-03", child, 0, f"src/{child.name}/ — свалка по типу; код — в фичу или shared/<назначение>/")
                elif child.name not in KNOWN_TOP:
                    self.add("FSTR-01", child, 0, f"src/{child.name}/ — верхний уровень: app, routes, features, shared")
            elif not TOP_FILES.match(child.name):
                self.add("FSTR-01", child, 0, f"файл {child.name} прямо в src/ — разложить по слоям")
        for d in self.root.rglob("*"):
            if d.is_dir() and d.name in DUMP_DIRS and not _skipped(d) and not self.is_legacy(d):
                self.add("FSTR-03", d, 0, f"каталог {d.name}/ — назвать по назначению (shared/lib/<что>/)")
        features = self.root / "features"
        if features.is_dir():
            for f in sorted(p for p in features.iterdir() if p.is_dir()):
                if not any((f / n).exists() for n in ("index.ts", "index.tsx")):
                    self.add("FDEP-03", f, 0, f"у фичи {f.name} нет index.ts — публичной поверхности")
                self._check_model_tests(f)

    def _check_model_tests(self, feature: Path) -> None:
        model = feature / "model"
        if not model.is_dir():
            return
        for p in model.rglob("*.ts"):
            if _is_test(p) or p.name.endswith(".d.ts") or p.name in {"index.ts", "types.ts"}:
                continue
            if re.search(r"(schema|store|types?)\.ts$", p.name):
                continue
            if not any((p.parent / f"{p.stem}.{s}").exists() for s in ("test.ts", "spec.ts", "test.tsx")):
                self.add("FTST-01", p, 0, "правило в model/ без теста рядом")

    def check_configs(self) -> None:
        pkg = self.repo / "package.json"
        if pkg.exists() and not any((self.repo / n).exists() for n in ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb")):
            self.add("FSEC-08", pkg, 0, "нет lock-файла в репозитории")
        eslint = [p for p in self.repo.glob("eslint.config.*")]
        if not eslint:
            self.add("FDEP-05", self.repo, 0, "нет eslint.config.* — границы не проверяются (шаблон templates/frontend)")
        elif not any("boundaries" in p.read_text(encoding="utf-8", errors="ignore") for p in eslint):
            self.add("FDEP-05", eslint[0], 0, "ESLint без eslint-plugin-boundaries — границы слоёв не проверяются")
        tsconfigs = [p for p in (self.repo / "tsconfig.app.json", self.repo / "tsconfig.json") if p.exists()]
        if tsconfigs:
            text = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in tsconfigs)
            for opt in ("strict", "noUncheckedIndexedAccess"):
                if not re.search(rf'"{opt}"\s*:\s*true', text):
                    self.add("FTS-01", tsconfigs[0], 0, f"в tsconfig не включён {opt}")
        for vite in self.repo.glob("vite.config.*"):
            text = vite.read_text(encoding="utf-8", errors="ignore")
            if "router-plugin" in text and "autoCodeSplitting" not in text:
                self.add("FRTE-04", vite, 0, "плагин TanStack Router без autoCodeSplitting: true")
        for env in self.repo.glob(".env*"):
            if env.name.endswith((".example", ".sample", ".template")):
                continue
            lines = env.read_text(encoding="utf-8", errors="ignore").splitlines()
            for i, line in enumerate(lines, 1):
                if VITE_SECRET_RE.search(line.split("=", 1)[0]):
                    self.add("FSEC-04", env, i, "секрет в переменной VITE_* — попадёт в бандл", lines)

    # --- файл ------------------------------------------------------------

    def check_file(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        test = _is_test(path)
        layer, feature = self.layer_of(path)
        rel_src = path.relative_to(self.root).as_posix() if self.root in path.parents else ""

        if not text.strip():
            self.add("FSTR-02", path, 0, "пустой файл")
            return
        if path.name in {"index.ts", "index.tsx"} and "export" not in text:
            self.add("FSTR-02", path, 0, "index.ts без экспортов")

        if not test:
            self._check_imports(path, text, lines, layer, feature)

        if path.suffix == ".tsx" and not test and not rel_src.startswith("shared/ui/"):   # shared/ui — код shadcn
            limit = 120 if layer == "routes" else 250
            rule = "FSTR-05" if layer == "routes" else "FCMP-05"
            if len(lines) > limit:
                self.add(rule, path, 0, f"{len(lines)} строк — разделить (ориентир {limit})")

        in_api_layer = rel_src.startswith("shared/api/")
        for i, raw in enumerate(lines, 1):
            if COMMENT_LINE.match(raw):
                self._check_comment(path, raw, i, lines)
                continue
            line = _strip_trailing_comment(raw)
            self._check_comment(path, raw, i, lines)

            if test:
                if TEST_MOCK_CLIENT_RE.search(line):
                    self.add("FTST-03", path, i, "подмена клиента API в тесте — ответы через MSW", lines)
                if FETCH_STUB_RE.search(line):
                    self.add("FTST-03", path, i, "подмена fetch руками — ответы через MSW", lines)
                continue

            if FETCH_RE.search(line) and not in_api_layer and "sendBeacon" not in line:
                self.add("FAPI-02", path, i, "fetch/axios мимо клиента shared/api", lines)
            if KEY_INDEX_RE.search(line) and not STATIC_LIST_RE.search(line) and not STATIC_LIST_RE.search(lines[i - 2] if i > 1 else ""):
                self.add("FCMP-04", path, i, "key по индексу — нужен стабильный id", lines)
            if layer == "features" and RESPONSE_TYPE_RE.search(line):
                self.add("FAPI-01", path, i, "ручной тип ответа API — брать из shared/api/generated", lines)
            if RELOAD_RE.search(line):
                self.add("FAPI-03", path, i, "перезагрузка страницы вместо инвалидации запросов", lines)
            if DANGER_RE.search(line) and "sanitize" not in line:
                self.add("FSEC-01", path, i, "HTML в DOM без DOMPurify.sanitize", lines)
            if STORAGE_TOKEN_RE.search(line):
                self.add("FSEC-02", path, i, "токен/сессия в localStorage/sessionStorage", lines)
            if VITE_SECRET_RE.search(line):
                self.add("FSEC-04", path, i, "секрет в VITE_* — попадёт в бандл", lines)
            if HARDCODED_SECRET_RE.search(line):
                self.add("FSEC-04", path, i, "ключ или токен в коде", lines)
            if JS_URL_RE.search(line):
                self.add("FSEC-06", path, i, "javascript: в ссылке", lines)
            elif DATA_HREF_RE.search(line):
                self.add("FSEC-06", path, i, "ссылка из данных без проверки схемы (safeHref)", lines)
            if POST_STAR_RE.search(line):
                self.add("FSEC-09", path, i, "postMessage с targetOrigin '*'", lines)
            if EVAL_RE.search(line):
                self.add("FSEC-10", path, i, "выполнение строки как кода", lines)
            if HEAVY_IMPORT.search(line):
                self.add("FPERF-06", path, i, "тяжёлая библиотека целиком (moment/lodash)", lines)
            if CONSOLE_RE.search(line):
                self.add("FOBS-04", path, i, "отладочный вывод", lines)
            if ANY_RE.search(line):
                self.add("FTS-02", path, i, "any — unknown и сужение", lines)
            if JSON_AS_RE.search(line):
                self.add("FTS-04", path, i, "JSON.parse(...) as T — проверить схемой", lines)
            if ENUM_RE.search(line):
                self.add("FTS-05", path, i, "enum — объединение литералов или as const", lines)

        if not test:
            self._check_multiline(path, text, lines)

    def _check_comment(self, path: Path, raw: str, i: int, lines: list[str]) -> None:
        if TS_IGNORE_RE.search(raw):
            self.add("FTS-03", path, i, "@ts-ignore/@ts-nocheck — @ts-expect-error с причиной", lines)
        if TS_EXPECT_RE.search(raw):
            self.add("FTS-03", path, i, "@ts-expect-error без причины", lines)
        m = ESLINT_DISABLE_RE.search(raw)
        if m and "--" not in m.group("rest"):
            self.add("FTS-03", path, i, "eslint-disable без причины (`-- почему`)", lines)
        elif m and re.search(r"/\*\s*eslint-disable(?!-)", raw):
            self.add("FTS-03", path, i, "eslint-disable на весь файл", lines)

    def _check_multiline(self, path: Path, text: str, lines: list[str]) -> None:
        for m in CLICK_DIV_RE.finditer(text):
            self.add("FA11Y-01", path, _line_of(text, m.start()), f"onClick на <{m.group(1)}> — нужен <button> или <a>", lines)
        for m in IMG_TAG_RE.finditer(text):
            tag = m.group(0)
            line = _line_of(text, m.start())
            if not re.search(r"\balt\s*=", tag) and "{...props}" not in tag:
                self.add("FA11Y-03", path, line, "<img> без alt", lines)
            if not (re.search(r"\bwidth\s*=", tag) and re.search(r"\bheight\s*=", tag)) and "{..." not in tag:
                self.add("FPERF-05", path, line, "<img> без width/height — сдвиг макета (CLS)", lines)
        for m in EMPTY_CATCH_RE.finditer(text):
            self.add("FOBS-03", path, _line_of(text, m.start()), "пустой catch — ошибка проглочена", lines)
        if MSG_LISTENER_RE.search(text) and ".origin" not in text:
            m = MSG_LISTENER_RE.search(text)
            assert m
            self.add("FSEC-09", path, _line_of(text, m.start()), "обработчик message без проверки event.origin", lines)
        if path.suffix == ".tsx":
            for m in USE_EFFECT_RE.finditer(text):
                body = _balanced(text, m.end() - 1)
                if EFFECT_LOAD_RE.search(body):
                    self.add("FCMP-02", path, _line_of(text, m.start()), "загрузка данных в useEffect — useQuery/loader", lines)

    def _check_imports(self, path: Path, text: str, lines: list[str], layer: str | None, feature: str | None) -> None:
        if layer is None:
            return
        for m in IMPORT_RE.finditer(text):
            spec = m.group(1) or m.group(2) or m.group(3)
            line = _line_of(text, m.start(1) if m.group(1) else m.start())
            target = self.resolve(spec, path)
            if target is None:
                continue
            if self.is_legacy(target) and not self.is_legacy(path):
                self.add("FLEG-01", path, line, f"новый код импортирует старый: {spec}", lines)
                continue
            t_layer, t_feature = self.layer_of(target)
            if t_layer is None:
                continue
            if LAYERS.index(t_layer) < LAYERS.index(layer):
                rule = "FDEP-02" if layer == "shared" and t_layer == "features" else "FDEP-01"
                self.add(rule, path, line, f"{layer} импортирует верхний слой {t_layer}: {spec}", lines)
                continue
            if t_layer == "features" and t_feature is None:
                t_feature = target.relative_to(self.root / "features").parts[0] if target != self.root / "features" else None
            if t_layer == "features" and t_feature and t_feature != feature:
                inner = target.relative_to(self.root / "features" / t_feature).parts
                if inner and inner[0] not in {"index", "index.ts", "index.tsx"}:
                    self.add("FDEP-03", path, line, f"глубокий импорт чужой фичи — через features/{t_feature}: {spec}", lines)
                if layer == "features" and feature:
                    self.feature_edges.setdefault(feature, {})[t_feature] = (path, line)
                    self.add("FDEP-04", path, line, f"фича {feature} → фича {t_feature}: компоновать в маршруте?", lines)

    def check_feature_cycles(self) -> None:
        seen: set[tuple[str, ...]] = set()

        def walk(node: str, stack: list[str]) -> None:
            for nxt in self.feature_edges.get(node, {}):
                if nxt in stack:
                    cycle = stack[stack.index(nxt):] + [nxt]
                    key = tuple(sorted(cycle[:-1]))
                    if key not in seen:
                        seen.add(key)
                        path, line = self.feature_edges[node][nxt]
                        self.findings.append(Finding("FDEP-04", "error", _rel(path, self.repo), line,
                                                     "цикл между фичами: " + " → ".join(cycle)))
                elif len(stack) < 20:
                    walk(nxt, [*stack, nxt])

        for start in self.feature_edges:
            walk(start, [start])

    def check_new_js(self, changed: set[Path]) -> None:
        added = _git(self.repo, "diff", "--name-only", "--diff-filter=A", "HEAD").splitlines()
        for name in added:
            p = (self.repo / name).resolve()
            if p.suffix in {".js", ".jsx"} and self.root in p.parents and p in changed:
                self.add("FLEG-02", p, 0, "новый .js/.jsx — новые файлы только .ts/.tsx")


# --- помощники -----------------------------------------------------------


def _rel(p: Path, base: Path) -> str:
    try:
        return str(p.relative_to(base))
    except ValueError:
        return str(p)


def _skipped(p: Path) -> bool:
    return any(part in SKIP_DIRS for part in p.parts) or p.name == "routeTree.gen.ts" or p.name.endswith(".d.ts")


def _is_test(p: Path) -> bool:
    return bool(re.search(r"\.(test|spec)\.tsx?$", p.name)) or "e2e" in p.parts or "test" in p.parts or "__tests__" in p.parts


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _strip_trailing_comment(line: str) -> str:
    # грубо: `//` вне строки с URL; достаточно для эвристик
    idx = line.find(" //")
    return line[:idx] if idx >= 0 and "://" not in line[idx:idx + 4] else line


def _balanced(text: str, start: int, limit: int = 4000) -> str:
    """Текст от открывающей скобки до парной (не дальше limit символов)."""
    depth = 0
    for i in range(start, min(len(text), start + limit)):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:start + limit]


def _suppressed(rule: str, lines: list[str], line: int) -> bool:
    for idx in (line - 1, line - 2):
        if 0 <= idx < len(lines):
            m = IGNORE_RE.search(lines[idx])
            if m and m.group(2) and rule in {r.strip() for r in m.group(1).split(",")}:
                return True
    return False


def _git(repo: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _changed_files(repo: Path, base: str) -> set[Path]:
    merge_base = _git(repo, "merge-base", "HEAD", base).strip() or base
    names = _git(repo, "diff", "--name-only", merge_base).splitlines()
    names += _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return {(repo / n).resolve() for n in names if n}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="корень фронтенд-проекта (где package.json)")
    ap.add_argument("--root", default="src", help="каталог с кодом относительно --repo")
    ap.add_argument("--diff", metavar="BASE", help="проверять только изменения относительно ветки BASE")
    ap.add_argument("--legacy", nargs="*", default=[], help="старые каталоги относительно --repo (src/legacy)")
    ap.add_argument("--json", action="store_true", help="вывод JSON")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = (repo / args.root).resolve()
    checker = Checker(repo, root, [(repo / d).resolve() for d in args.legacy])

    files = [p.resolve() for p in root.rglob("*") if p.suffix in CODE_EXT and p.is_file() and not _skipped(p.relative_to(repo))]
    files += [p.resolve() for p in (repo / "e2e").rglob("*.ts") if (repo / "e2e").is_dir()]
    if args.diff:
        changed = _changed_files(repo, args.diff)
        files = [p for p in files if p in changed]
        checker.check_new_js(changed)
    else:
        checker.check_layout()
        checker.check_configs()
    files = [p for p in files if not checker.is_legacy(p)]
    for p in files:
        checker.check_file(p)
    checker.check_feature_cycles()

    findings = sorted(checker.findings, key=lambda f: (f.severity != "error", f.rule, f.path, f.line))
    features = sorted(p.name for p in (root / "features").iterdir() if p.is_dir()) if (root / "features").is_dir() else []
    if args.json:
        print(json.dumps({"features": features, "findings": [asdict(f) for f in findings]}, ensure_ascii=False, indent=2))
    else:
        print(f"Фичи ({len(features)}): {', '.join(features) or '—'}")
        print(f"Файлов проверено: {len(files)}")
        for f in findings:
            loc = f"{f.path}:{f.line}" if f.line else f.path
            print(f"{f.severity.upper():7} {f.rule:8} {loc}  {f.message}")
        errors = sum(f.severity == "error" for f in findings)
        print(f"Итого: {errors} ошибок, {len(findings) - errors} предупреждений")
    return 1 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
