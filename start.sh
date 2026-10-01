#!/bin/bash

echo ""
echo "===================================="
echo " FiveM Dev Lab - Server Starting"
echo "===================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed"
    echo "Please install Python 3.8+ from https://www.python.org"
    exit 1
fi

echo "[OK] Python found"
echo ""

echo "Checking dependencies..."
if ! pip3 list | grep -q Flask; then
    echo "[INFO] Installing dependencies..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install dependencies"
        exit 1
    fi
fi

echo "[OK] All dependencies installed"
echo ""
echo "===================================="
echo " Starting FiveM Dev Lab..."
echo " Open browser: http://localhost:5000"
echo " Login: admin / admin123"
echo "===================================="
echo ""

python3 app.py
