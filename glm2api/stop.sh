#!/bin/bash
pkill -f "glm2api.*main.py" 2>/dev/null && echo "stopped" || echo "not running"
