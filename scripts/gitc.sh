#!/bin/sh
# Commit everything with one message: scripts/gitc.sh "message"
set -e
cd "$(dirname "$0")/.."
git add -A
git commit -q -m "$1" -m "Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>"
git log --oneline | head -3
