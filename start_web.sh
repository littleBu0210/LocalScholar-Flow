#!/usr/bin/env bash
set -Eeuo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "正在停止 LocalScholar Flow 服务..."
  if [[ -f workspace/web_workflow.pid ]]; then
    workflow_pid="$(<workspace/web_workflow.pid)"
    if [[ "$workflow_pid" =~ ^[0-9]+$ ]]; then
      pkill -TERM -P "$workflow_pid" >/dev/null 2>&1 || true
      kill -TERM "$workflow_pid" >/dev/null 2>&1 || true
    fi
  fi
  docker compose stop mineru hunyuan mongodb >/dev/null 2>&1 || true
  echo "服务已停止。"
}
trap cleanup INT TERM EXIT

if [[ ! -x .venv/bin/python ]]; then
  echo "未找到 .venv，请先安装项目依赖。" >&2
  exit 1
fi

.venv/bin/python -c 'import streamlit' 2>/dev/null || .venv/bin/pip install -r requirements.txt

# streamlit-pdf hides its zoom controls until a precise hover. Keep them
# visible so the reader always has obvious zoom-in/zoom-out buttons.
python_version="$(${project_dir}/.venv/bin/python -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
pdf_component_dir=".venv/lib/python${python_version}/site-packages/streamlit_pdf/frontend/build/assets"
if [[ -d "$pdf_component_dir" ]]; then
  sed -i 's/opacity:0;padding:0;overflow:hidden;pointer-events:none/opacity:1;padding:0;overflow:hidden;pointer-events:auto/g' "$pdf_component_dir"/*.css
fi

docker compose up -d mongodb

echo "网页地址：http://localhost:8501"
echo "按 Ctrl+C 停止网页和 Docker 服务。"
.venv/bin/python -m streamlit run web_app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
