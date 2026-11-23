#!/usr/bin/env bash
# Установка общих правил.
#
#   ./install.sh claude              # ~/.claude (или $CLAUDE_CONFIG_DIR): ядро, скиллы, правила по путям
#   ./install.sh gigacode            # ~/.gigacode: ядро, скиллы
#   ./install.sh project <путь> [--tool claude|gigacode|agents]
#                                    # в репозиторий проекта: блок правил в AGENTS.md, скиллы, шаблоны
#   --profile backend,frontend       # какие области ставить (по умолчанию обе)
#   --copy                           # копии вместо симлинков (если инструмент не идёт по ссылкам)
#   --dry-run                        # только показать, что будет сделано
#
# Повторный запуск безопасен: ссылки обновляются, блоки между метками заменяются.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEGIN_MARK="<!-- engineering-standards:begin -->"
END_MARK="<!-- engineering-standards:end -->"
DRY=0
COPY=0
PROFILES=(backend frontend)
STAMP="$(date +%Y%m%d-%H%M%S)"

say() { printf '  %s\n' "$*"; }
run() { if (( DRY )); then say "[dry-run] $*"; else "$@"; fi }

skills() { local p; for p in "${PROFILES[@]}"; do printf '%s\n' "$p-guide" "$p-review"; done; }

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

# Убрать наши симлинки на области, которые не выбраны (переустановка с другим --profile).
prune() {
  local dir="$1" link target keep name
  [[ -d "$dir" ]] || return 0
  for link in "$dir"/*; do
    [[ -L "$link" ]] || continue
    target="$(readlink "$link")"
    [[ "$target" == "$REPO"/* ]] || continue
    [[ -e "$target" ]] || { run rm "$link"; say "удалена битая ссылка $link"; continue; }
    name="$(basename "$link")"; keep=0
    for p in "${PROFILES[@]}"; do [[ "$name" == "$p"-* ]] && keep=1; done
    (( keep )) || { run rm "$link"; say "удалено (область не выбрана): $link"; }
  done
}

# Блок импортов: ядро + ядра выбранных областей.
import_block() {
  printf '%s\n' "$BEGIN_MARK" "@$REPO/core.md"
  for p in "${PROFILES[@]}"; do printf '@%s\n' "$REPO/$p.md"; done
  printf '%s\n' "$END_MARK"
}

# Главный файл инструкций. Свой (с нашим блоком или прежним импортом) — заменить блок,
# остальное не трогать. Чужой — в резервную копию, записать шаблон.
write_main() {
  local template="$1" dst="$2" real="$2"
  [[ -L "$dst" ]] && real="$(cd "$(dirname "$dst")" && cd "$(dirname "$(readlink "$dst")")" && pwd)/$(basename "$(readlink "$dst")")"
  if (( DRY )); then say "[dry-run] $dst: блок импортов (${PROFILES[*]})"; return; fi
  mkdir -p "$(dirname "$real")"
  local tmp; tmp="$(mktemp)"
  if [[ -f "$real" ]] && grep -qF -e "$BEGIN_MARK" -e "@$REPO/" "$real"; then
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" -v r="@$REPO/" '
      $0==b {skip=1; next} $0==e {skip=0; next} skip {next}
      index($0, r)==1 {next}
      /^[[:space:]]*$/ {blank++; next}
      {while (blank > 0) {print ""; blank--} print}
    ' "$real" > "$tmp"
  else
    if [[ -f "$real" ]]; then
      say "резервная копия: $real.bak-$STAMP  ← перенеси личное оттуда выше блока"
      cp "$real" "$real.bak-$STAMP"
    fi
    cat "$template" > "$tmp"
  fi
  { cat "$tmp"; printf '\n'; import_block; } > "$real"
  rm "$tmp"
  say "$dst: импорт core.md + ${PROFILES[*]}"
}

install_claude() {
  local cfg="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  echo "Claude Code → $cfg (${PROFILES[*]})"
  run mkdir -p "$cfg/skills" "$cfg/rules"
  write_main "$REPO/adapters/claude/CLAUDE.md.template" "$cfg/CLAUDE.md"
  prune "$cfg/skills"; prune "$cfg/rules"
  local s r p
  for s in $(skills); do place "$REPO/skills/$s" "$cfg/skills/$s"; done
  for p in "${PROFILES[@]}"; do
    for r in "$REPO"/adapters/claude/rules/"$p"-*.md; do place "$r" "$cfg/rules/$(basename "$r")"; done
  done
}

install_gigacode() {
  local cfg="$HOME/.gigacode"
  echo "GigaCode CLI → $cfg (${PROFILES[*]})"
  run mkdir -p "$cfg/skills"
  write_main "$REPO/adapters/gigacode/GIGACODE.md.template" "$cfg/GIGACODE.md"
  prune "$cfg/skills"
  local s
  for s in $(skills); do place "$REPO/skills/$s" "$cfg/skills/$s"; done
}

install_project() {
  local dir="$1" tool="$2"
  [[ -d "$dir" ]] || { echo "нет каталога $dir" >&2; exit 1; }
  dir="$(cd "$dir" && pwd)"
  echo "Проект → $dir (${PROFILES[*]}; скиллы для: $tool)"

  local agents="$dir/AGENTS.md"
  if [[ ! -f "$agents" ]]; then
    run cp "$REPO/templates/AGENTS.md" "$agents"
    say "AGENTS.md из шаблона — заполни описание и «Отклонения»"
  fi
  # Блок общих правил в конце AGENTS.md: копия ядер, обновляется повторным запуском.
  if (( DRY )); then
    say "[dry-run] обновить блок общих правил в AGENTS.md"
  else
    local tmp p; tmp="$(mktemp)"
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
      $0==b {skip=1; next} $0==e {skip=0; next} skip {next}
      /^[[:space:]]*$/ {blank++; next}
      {while (blank > 0) {print ""; blank--} print}
    ' "$agents" > "$tmp"
    {
      cat "$tmp"
      printf '\n%s\n' "$BEGIN_MARK"
      printf '<!-- Копия общих правил (engineering-standards). Не править здесь: обновлять ./install.sh project. -->\n\n'
      for f in core "${PROFILES[@]}"; do
        sed 's/^### /#### /; s/^## /### /; s/^# /## /' "$REPO/$f.md"
        printf '\n'
      done
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
  local s
  for s in $(skills); do place "$REPO/skills/$s" "$sdir/$s" 1; done

  for p in "${PROFILES[@]}"; do
    case "$p" in
      backend)
        [[ -e "$dir/.importlinter" ]] || { run cp "$REPO/templates/importlinter.ini" "$dir/.importlinter"; say ".importlinter из шаблона — заменить app/assets"; } ;;
      frontend)
        say "фронтенд: конфиги — $REPO/templates/frontend/ (eslint, tsconfig, openapi-ts, knip), см. frontend-guide/new-project.md" ;;
    esac
  done
}

main() {
  local cmd="${1:-}"; shift || true
  local tool="agents" target=""
  while (( $# )); do
    case "$1" in
      --dry-run) DRY=1 ;;
      --copy) COPY=1 ;;
      --tool) tool="$2"; shift ;;
      --profile)
        IFS=',' read -r -a PROFILES <<< "$2"; shift
        for p in "${PROFILES[@]}"; do
          [[ -f "$REPO/$p.md" ]] || { echo "неизвестная область $p (есть: backend, frontend)" >&2; exit 1; }
        done ;;
      *) target="$1" ;;
    esac
    shift
  done
  case "$cmd" in
    claude) install_claude ;;
    gigacode) install_gigacode ;;
    project) [[ -n "$target" ]] || { echo "укажи путь проекта" >&2; exit 1; }; install_project "$target" "$tool" ;;
    *) sed -n '2,12p' "$0"; exit 1 ;;
  esac
}

main "$@"
