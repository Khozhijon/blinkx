#!/bin/sh
# Publish frontend/ as a static site on the gh-pages branch (GitHub Pages).
# The saved examples then load instantly even while the Render backend is asleep.
set -e
cd "$(dirname "$0")/.."
git push origin "$(git subtree split --prefix frontend main)":refs/heads/gh-pages --force
echo "Pushed. If the site does not appear, enable it once: GitHub repo > Settings > Pages > Branch: gh-pages."
