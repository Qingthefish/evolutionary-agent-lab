#!/bin/zsh
# Prototype (2026-11-27): Open WebUI in front of the classroom platform through scripts/webui_adapter.py.
# Both servers listen on 127.0.0.1 only. Close this window (or Ctrl+C) to stop both.
set -eu
project_dir="${0:A:h}"
cd "$project_dir"
py="$project_dir/venv/presentation/bin/python"
webui="$project_dir/venv/openwebui/bin/open-webui"
for f in "$py" "$webui"; do
  [[ -x "$f" ]] || { print "缺少环境：$f。请先按原型说明安装。"; read '?按回车退出'; exit 1; }
done
[[ -S "$HOME/.colima/agent-lab/docker.sock" ]] || { print '请先在 Terminal 执行：colima start --profile agent-lab'; read '?按回车退出'; exit 1; }
"$py" scripts/webui_adapter.py --port 8765 &
adapter=$!
trap 'kill $adapter 2>/dev/null' EXIT INT TERM
sleep 2
data="$project_dir/runs/openwebui-data"; mkdir -p "$data"
[[ -f "$data/.secret" ]] || { openssl rand -hex 32 > "$data/.secret"; chmod 600 "$data/.secret"; }
export DATA_DIR="$data" WEBUI_SECRET_KEY="$(cat "$data/.secret")" WEBUI_AUTH=False HOST=127.0.0.1 PORT=8080 \
  OPENAI_API_BASE_URL="http://127.0.0.1:8765/v1" OPENAI_API_KEY="$(cat runs/presentation-local/webui-token.txt)" \
  ENABLE_OLLAMA_API=False ENABLE_OPENAI_API=True OFFLINE_MODE=True HF_HUB_OFFLINE=1 \
  ENABLE_TITLE_GENERATION=False ENABLE_TAGS_GENERATION=False ENABLE_FOLLOW_UP_GENERATION=False \
  ENABLE_AUTOCOMPLETE_GENERATION=False ENABLE_WEB_SEARCH=False ENABLE_IMAGE_GENERATION=False \
  ENABLE_EVALUATION_ARENA_MODELS=False DEFAULT_MODELS=agent-lab-classroom \
  SCARF_NO_ANALYTICS=true DO_NOT_TRACK=true ANONYMIZED_TELEMETRY=false
( sleep 25; open "http://127.0.0.1:8080" ) &
caffeinate -i "$webui" serve --host 127.0.0.1 --port 8080
