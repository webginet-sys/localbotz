#!/bin/sh
# LocalBotz — macOS one-click launcher.
# Double-click this file in Finder to start LocalBotz.
# If macOS blocks it, right-click it, choose Open, then click Open.
# It runs start.sh in this folder, which installs the dependencies
# (first time) and starts the app on http://127.0.0.1:8000.
cd "$(dirname "$0")"
exec ./start.sh "$@"
