#!/bin/bash
# 启动 glm2api (127.0.0.1:8100), 日志 /tmp/glm2api.log
# 用 start_new_session 让服务脱离当前 shell 的进程组，避免 shell 退出时被连带杀掉
cd "$(dirname "$0")"
if curl -s --max-time 2 http://127.0.0.1:8100/health >/dev/null 2>&1; then
  echo "already running"
  exit 0
fi
nohup python3 -c '
import subprocess, os
subprocess.Popen(["uv", "run", "main.py"], cwd=os.getcwd(), start_new_session=True)
' >> /tmp/glm2api.log 2>&1 &
sleep 3
curl -s --max-time 5 http://127.0.0.1:8100/health && echo " -> glm2api started"
