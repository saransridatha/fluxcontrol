#!/bin/bash
set -x # Enable debugging

# --- PHASE 1: SETUP & UPDATE ---
cd ~/fluxcontrol

# Verify it's a git repo before pulling
if [ ! -d .git ]; then
  echo "Error: Not a git repository. Please clone the repo first."
  exit 1
fi
git pull origin main || true

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# Install dependencies using the venv's pip
venv/bin/pip install -r src/backend/requirements.txt || exit 1

# --- PHASE 2: RESTART ---
# Kill old process (Port 8080)
fuser -k -n tcp 8080 || true

# Move into the backend folder
cd src/backend

# Run the app with the venv python, log inside the project dir
nohup ../../venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 > ../../backend.log 2>&1 &

# Verify
sleep 3
pgrep -a uvicorn
