#!/bin/zsh
# Prototype (2026-11-27): Open WebUI in front of the classroom platform through scripts/webui_adapter.py.
# Only features the platform can actually serve are shown: chat, live progress, HTML preview, copy,
# chat history and search. Everything else is switched off with Open WebUI's own settings, and the
# local account is a normal user so its permission switches apply (they do not restrict admins).
# Both servers listen on 127.0.0.1 only. Close this window (or Ctrl+C) to stop both.
set -eu
project_dir="${0:A:h}"
cd "$project_dir"
py="$project_dir/venv/presentation/bin/python"
webui="$project_dir/venv/openwebui/bin/open-webui"
for f in "$py" "$webui"; do
  [[ -x "$f" ]] || { print "缺少环境：$f。请先按 docs/presentation-sop.md「网页界面（原型，可选）」安装。"; read '?按回车退出'; exit 1; }
done
[[ -S "$HOME/.colima/agent-lab/docker.sock" ]] || { print '请先在 Terminal 执行：colima start --profile agent-lab'; read '?按回车退出'; exit 1; }
for port in 8080 8765; do
  if lsof -nP -iTCP:$port -sTCP:LISTEN >/dev/null 2>&1; then
    print "端口 $port 已被占用：网页界面可能已经在运行（浏览器打开 http://127.0.0.1:8080），或请先关闭旧窗口。"
    read '?按回车退出'; exit 1
  fi
done

"$py" scripts/webui_adapter.py --port 8765 &
adapter=$!
trap 'kill $adapter 2>/dev/null' EXIT INT TERM
sleep 2
data="$project_dir/runs/openwebui-data"; mkdir -p "$data"
[[ -f "$data/.secret" ]] || { openssl rand -hex 32 > "$data/.secret"; chmod 600 "$data/.secret"; }

# Connection and privacy.
static="$project_dir/runs/openwebui-static"; mkdir -p "$static"
export STATIC_DIR="$static"
export DATA_DIR="$data" WEBUI_SECRET_KEY="$(cat "$data/.secret")" WEBUI_AUTH=False HOST=127.0.0.1 PORT=8080 \
  ENABLE_PERSISTENT_CONFIG=False \
  OPENAI_API_BASE_URL="http://127.0.0.1:8765/v1" OPENAI_API_KEY="$(cat runs/presentation-local/webui-token.txt)" \
  ENABLE_OPENAI_API=True ENABLE_OLLAMA_API=False ENABLE_DIRECT_CONNECTIONS=False \
  ENABLE_FORWARD_USER_INFO_HEADERS=True BYPASS_MODEL_ACCESS_CONTROL=True DEFAULT_MODELS=agent-lab-classroom \
  OFFLINE_MODE=True HF_HUB_OFFLINE=1 SCARF_NO_ANALYTICS=true DO_NOT_TRACK=true ANONYMIZED_TELEMETRY=false \
  DEFAULT_PROMPT_SUGGESTIONS='[]'

# Features the platform cannot serve, or that would send extra requests to it.
for flag in TITLE_GENERATION TAGS_GENERATION FOLLOW_UP_GENERATION AUTOCOMPLETE_GENERATION \
    RETRIEVAL_QUERY_GENERATION SEARCH_QUERY_GENERATION IMAGE_PROMPT_GENERATION CONTEXT_COMPACTION \
    WEB_SEARCH IMAGE_GENERATION IMAGE_EDIT VIDEO_GENERATION CODE_INTERPRETER CODE_EXECUTION \
    CHANNELS ENCRYPTED_CHANNELS NOTES CALENDAR AUTOMATIONS MEMORIES FOLDERS APPS SUBAGENTS \
    COMMUNITY_SHARING MESSAGE_RATING EVALUATION_ARENA_MODELS USER_WEBHOOKS API_KEYS COMMENTS \
    USER_STATUS GOOGLE_DRIVE_INTEGRATION ONEDRIVE_INTEGRATION TOOL_SEARCH VOICE_MODE_PROMPT; do
  export "ENABLE_$flag=False"
done

# Per-user permissions (apply because the local account is made a normal user below).
for perm in CHAT_CONTROLS CHAT_VALVES CHAT_SYSTEM_PROMPT CHAT_PARAMS CHAT_FILE_UPLOAD CHAT_WEB_UPLOAD \
    CHAT_DELETE_MESSAGE CHAT_CONTINUE_RESPONSE CHAT_REGENERATE_RESPONSE CHAT_RATE_RESPONSE CHAT_EDIT \
    CHAT_SHARE CHAT_EXPORT CHAT_IMPORT CHAT_STT CHAT_TTS CHAT_CALL CHAT_MULTIPLE_MODELS CHAT_TEMPORARY \
    CHAT_SIDE_CHAT CHAT_ALLOW_OPEN_SHARING CHAT_ALLOW_PUBLIC_SHARING \
    FEATURES_API_KEYS FEATURES_AUTOMATIONS FEATURES_CALENDAR FEATURES_CHANNELS FEATURES_ENCRYPTED_CHANNELS \
    FEATURES_CODE_INTERPRETER FEATURES_FOLDERS FEATURES_IMAGE_GENERATION FEATURES_MEMORIES FEATURES_NOTES \
    FEATURES_SUBAGENTS FEATURES_USER_WEBHOOKS FEATURES_VIDEO_GENERATION FEATURES_WEB_SEARCH \
    WORKSPACE_MODELS_ACCESS WORKSPACE_KNOWLEDGE_ACCESS WORKSPACE_PROMPTS_ACCESS WORKSPACE_TOOLS_ACCESS \
    WORKSPACE_SKILLS_ACCESS; do
  export "USER_PERMISSIONS_$perm=False"
done
export USER_PERMISSIONS_CHAT_DELETE=True

( for i in {1..120}; do
    curl -s --max-time 2 http://127.0.0.1:8080/health | grep -q true && break; sleep 2
  done
  # Create (or sign in) the no-login local account, then make it a normal user so the switches above apply.
  curl -s -o /dev/null --max-time 10 -H 'Content-Type: application/json' \
    -d '{"email":"","password":""}' http://127.0.0.1:8080/api/v1/auths/signin || true
  "$py" -c "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute(\"UPDATE user SET role='user' WHERE email='admin@localhost'\"); db.commit()" "$data/webui.db"
  # Open WebUI refreshes its static copy at start-up; add our stylesheet afterwards.
  cp "$project_dir/ui/openwebui-custom.css" "$static/custom.css"
  cp "$project_dir/ui/openwebui-loader.js" "$static/loader.js"
  open "http://127.0.0.1:8080" ) &

caffeinate -i "$webui" serve --host 127.0.0.1 --port 8080
