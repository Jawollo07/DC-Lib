#!/bin/bash

echo "Starting MedienBot..."
echo "Checking Python version..."
git pull
# Check if Python 3.11+ is available
if command -v python3.11 &>/dev/null; then
    PYTHON_CMD=python3.11
elif command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
else
    echo "Error: Python 3.11 or higher is required but not found."
    exit 1
fi

# Verify Python version
$PYTHON_CMD -c "import sys; exit(0) if sys.version_info >= (3, 11) else exit(1)"
if [ $? -ne 0 ]; then
    echo "Error: Python 3.11 or higher is required."
    exit 1
fi

echo "Python version OK"
echo "Installing dependencies..."

# Install/upgrade dependencies
$PYTHON_CMD -m pip install --upgrade pip
$PYTHON_CMD -m pip install -r requirements.txt

echo "Starting bot..."
$PYTHON_CMD main.py