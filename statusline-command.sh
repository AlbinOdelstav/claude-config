#!/usr/bin/env bash

input=$(cat)

# Parse JSON fields using node with process.stdin
parse_json() {
  echo "$input" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      try{
        const o=JSON.parse(d);
        const k='$1'.split('.');
        let v=o;
        for(const p of k) v=v?.[p];
        process.stdout.write(v!=null?String(v):'');
      }catch(e){}
    });
  " 2>/dev/null
}

cwd=$(parse_json "cwd")
remaining_pct=$(parse_json "context_window.remaining_percentage")
total_input=$(parse_json "context_window.total_input_tokens")
ctx_size=$(parse_json "context_window.context_window_size")
model=$(parse_json "model.display_name")

# Git branch
branch=""
if [ -n "$cwd" ]; then
  branch=$(git --no-optional-locks -C "$cwd" branch --show-current 2>/dev/null)
fi
if [ -z "$branch" ]; then
  branch=$(git --no-optional-locks branch --show-current 2>/dev/null)
fi

# ANSI colors
RST=$'\033[0m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
CYAN=$'\033[96m'
GREEN=$'\033[92m'
YELLOW=$'\033[93m'
MAGENTA=$'\033[95m'
BLUE=$'\033[94m'
RED=$'\033[91m'
WHITE=$'\033[97m'

# Row 1: Branch + Model
line1=""
if [ -n "$branch" ]; then
  line1="${BOLD}${MAGENTA}Branch:${RST} ${CYAN}${branch}${RST}"
fi
if [ -n "$model" ]; then
  [ -n "$line1" ] && line1="${line1}    "
  line1="${line1}${BOLD}${BLUE}Model:${RST} ${WHITE}${model}${RST}"
fi

# Row 2: Token usage
line2=""
if [ -n "$remaining_pct" ]; then
  pct_int=$(printf "%.0f" "$remaining_pct")

  if awk "BEGIN{exit !($remaining_pct > 50)}"; then
    token_color="${GREEN}"
  elif awk "BEGIN{exit !($remaining_pct > 20)}"; then
    token_color="${YELLOW}"
  else
    token_color="${RED}"
  fi

  ctx_int=$(echo "$ctx_size" | cut -d. -f1)
  used_int=$(echo "$total_input" | cut -d. -f1)

  if [ "${ctx_int:-0}" -gt 0 ] 2>/dev/null; then
    remaining_tokens=$((ctx_int - used_int))
    remaining_k=$(awk "BEGIN{printf \"%.0f\", $remaining_tokens / 1000}")
    ctx_k=$(awk "BEGIN{printf \"%.0f\", $ctx_int / 1000}")
    line2="${BOLD}${YELLOW}Tokens:${RST} ${token_color}${pct_int}% remaining${RST}  ${DIM}(${remaining_k}k / ${ctx_k}k)${RST}"
  else
    line2="${BOLD}${YELLOW}Tokens:${RST} ${token_color}${pct_int}% remaining${RST}"
  fi
fi

[ -n "$line1" ] && printf "%s\n" "$line1"
[ -n "$line2" ] && printf "%s\n" "$line2"

exit 0
