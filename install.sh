#!/usr/bin/env bash
#
# PyBlog installation script.
# Checks requirements, sets the password and builds the site for the first time.
#
# Usage:  ./install.sh
#

set -e

echo ""
echo "=============================================="
echo "   PyBlog - installation"
echo "=============================================="
echo ""

# 1. Check that Python 3 is available.
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: Python 3 is not installed."
  echo "Install Python 3 and try again:"
  echo "  - Ubuntu/Debian:  sudo apt install python3"
  echo "  - macOS:          brew install python3"
  exit 1
fi

VERSION=$(python3 -c 'import sys; print(str(sys.version_info[0]) + "." + str(sys.version_info[1]))')
echo "Found Python $VERSION"

# PyBlog has no external dependencies: it only uses the Python standard library.
echo "Nothing to install: PyBlog only uses the standard library."
echo ""

# 2. Set the administration area password (if it doesn't exist yet).
if [ ! -f "admin_password.txt" ]; then
  echo "Set the password for the administration area now."
  python3 pyblog.py password
  echo ""
fi

# 3. Build the site for the first time.
echo "Building the site for the first time..."
python3 pyblog.py build
echo ""

echo "=============================================="
echo "   Installation complete!"
echo "=============================================="
echo ""
echo "To start the editor locally:"
echo "    python3 pyblog.py serve"
echo ""
echo "Then open your browser at:"
echo "    http://localhost:8000/admin"
echo ""
echo "To put it online on an Ubuntu server, follow TUTORIAL.md"
echo ""
