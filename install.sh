#!/usr/bin/env bash
# Установка общих правил.
#
#   ./install.sh claude              # ~/.claude (или $CLAUDE_CONFIG_DIR): ядро, скиллы, правила по путям
#   ./install.sh gigacode            # ~/.gigacode: ядро, скиллы
#   ./install.sh gigacode --copy     # копии вместо симлинков (если инструмент не идёт по ссылкам)
#   ./install.sh project <путь> [--tool claude|gigacode|agents]
#                                    # в репозиторий проекта: блок правил в AGENTS.md, скиллы, шаблоны
#   --dry-run                        # только показать, что будет сделано
#
# Повторный запуск безопасен: ссылки обновляются, блок в AGENTS.md заменяется.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS=(backend-guide backend-review)
BEGIN_MARK="<!-- engineering-standards:begin -->"
END_MARK="<!-- engineering-standards:end -->"
DRY=0
COPY=0
STAMP="$(date +%Y%m%d-%H%M%S)"

say() { printf '  %s\n' "$*"; }
run() { if (( DRY )); then say "[dry-run] $*"; else "$@"; fi }

# Положить src в dst: симлинк (по умолчанию) или копия. Чужой файл/каталог — в резервную копию.
place() {
  local src="$1" dst="$2" own="${3:-0}"
  if [[ -L "$dst" ]]; then
    run rm "$dst"
  elif (( own )) && [[ -e "$dst" ]]; then
    run rm -rf "$dst"   # наша же прежняя копия
  elif [[ -e "$dst" ]]; then
    say "резервная копия: $dst.bak-$STAMP"
    run mv "$dst" "$dst.bak-$STAMP"
  fi
  if (( COPY )); then run cp -R "$src" "$dst"; else run ln -s "$src" "$dst"; fi
  say "$dst → $src"
}

# Главный файл инструкций: шаблон с импортом ядра. Прежний — в резервную копию.
write_main() {
  local template="$1" dst="$2"
  local real="$dst"
  [[ -L "$dst" ]] && real="$(cd "$(dirname "$dst")" && cd "$(dirname "$(readlink "$dst")")" && pwd)/$(basename "$(readlink "$dst")")"
  if [[ -f "$real" ]] && grep -qF "@$REPO/core.md" "$real"; then
    say "$dst уже импортирует ядро — не трогаю"
    return
  fi
  if [[ -f "$real" ]]; then
    say "резервная копия: $real.bak-$STAMP  ← перенеси личное оттуда выше строки импорта"
    run cp "$real" "$real.bak-$STAMP"
  fi
  if (( DRY )); then
    say "[dry-run] записать $real из $(basename "$template")"
  else
    mkdir -p "$(dirname "$real")"
    sed "s|__CORE__|$REPO/core.md|" "$template" > "$real"
  fi
  say "$dst: импорт $REPO/core.md"
}

install_claude() {
  local cfg="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  echo "Claude Code → $cfg"
  run mkdir -p "$cfg/skills" "$cfg/rules"
  write_main "$REPO/adapters/claude/CLAUDE.md.template" "$cfg/CLAUDE.md"
  for s in "${SKILLS[@]}"; do place "$REPO/skills/$s" "$cfg/skills/$s"; done
  for r in "$REPO"/adapters/claude/rules/*.md; do place "$r" "$cfg/rules/$(basename "$r")"; done
}

install_gigacode() {
  local cfg="$HOME/.gigacode"
  echo "GigaCode CLI → $cfg"
  run mkdir -p "$cfg/skills"
  write_main "$REPO/adapters/gigacode/GIGACODE.md.template" "$cfg/GIGACODE.md"
  for s in "${SKILLS[@]}"; do place "$REPO/skills/$s" "$cfg/skills/$s"; done
}

install_project() {
  local dir="$1" tool="$2"
  [[ -d "$dir" ]] || { echo "нет каталога $dir" >&2; exit 1; }
  dir="$(cd "$dir" && pwd)"
  echo "Проект → $dir (скиллы для: $tool)"

  local agents="$dir/AGENTS.md"
  if [[ ! -f "$agents" ]]; then
    run cp "$REPO/templates/AGENTS.md" "$agents"
    say "AGENTS.md из шаблона — заполни описание и «Отклонения»"
  fi
  # Блок общих правил в конце AGENTS.md: копия ядра, обновляется повторным запуском.
  if (( DRY )); then
    say "[dry-run] обновить блок общих правил в AGENTS.md"
  else
    local tmp; tmp="$(mktemp)"
    # вырезать прежний блок и хвостовые пустые строки
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
      $0==b {skip=1; next} $0==e {skip=0; next} skip {next}
      /^[[:space:]]*$/ {blank++; next}
      {while (blank > 0) {print ""; blank--} print}
    ' "$agents" > "$tmp"
    {
      cat "$tmp"
      printf '\n%s\n' "$BEGIN_MARK"
      printf '<!-- Копия общих правил (engineering-standards). Не править здесь: обновлять ./install.sh project. -->\n\n'
      sed 's/^## /### /; s/^# /## /' "$REPO/core.md"
      printf '%s\n' "$END_MARK"
    } > "$agents"
    rm "$tmp"
    say "AGENTS.md: блок общих правил обновлён"
  fi

  local sdir
  case "$tool" in
    claude) sdir="$dir/.claude/skills" ;;
    gigacode) sdir="$dir/.gigacode/skills" ;;
    agents) sdir="$dir/.agents/skills" ;;
    *) echo "неизвестный --tool $tool" >&2; exit 1 ;;
  esac
  run mkdir -p "$sdir"
  COPY=1  # в репозиторий проекта — только копии: симлинк на чужой диск у коллег не откроется
  for s in "${SKILLS[@]}"; do place "$REPO/skills/$s" "$sdir/$s" 1; done

  [[ -e "$dir/.importlinter" ]] || { run cp "$REPO/templates/importlinter.ini" "$dir/.importlinter"; say ".importlinter из шаблона — заменить app/assets"; }
}

main() {
  local cmd="${1:-}"; shift || true
  local tool="agents" target=""
  while (( $# )); do
    case "$1" in
      --dry-run) DRY=1 ;;
      --copy) COPY=1 ;;
      --tool) tool="$2"; shift ;;
      *) target="$1" ;;
    esac
    shift
  done
  case "$cmd" in
    claude) install_claude ;;
    gigacode) install_gigacode ;;
    project) [[ -n "$target" ]] || { echo "укажи путь проекта" >&2; exit 1; }; install_project "$target" "$tool" ;;
    *) sed -n '2,11p' "$0"; exit 1 ;;
  esac
}

main "$@"
