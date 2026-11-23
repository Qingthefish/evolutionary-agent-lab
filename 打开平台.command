#!/bin/zsh
set -eu
project_dir="${0:A:h}"
cd "$project_dir"
presentation_python="$project_dir/venv/presentation/bin/python"
if [[ ! -x "$presentation_python" ]]; then
  print '界面环境尚未准备，请先阅读 docs/presentation-sop.md。'
  read '?按回车退出'
  exit 1
fi
caffeinate -i "$presentation_python" "$project_dir/scripts/classroom.py" menu
