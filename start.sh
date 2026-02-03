#!/bin/bash
set -e

echo "=== LMS Attendance Bot Startup ==="
echo "Python version: $(python --version)"
echo "Current directory: $(pwd)"
echo "Environment variables:"
echo "PORT: $PORT"
echo "HOST: $HOST"

echo "=== Checking Python modules ==="
python -c "import sys; print('Python path:', sys.path)" || echo "Python path check failed"
python -c "import src.config.settings; print('Settings module loaded')" || echo "Settings module failed"
python -c "from src.web.app import app; print('Web app loaded')" || echo "Web app failed"

echo "=== Starting application ==="
exec python main.py