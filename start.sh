#!/usr/bin/env bash
# start.sh — تشغيل البوت
set -e
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi
python installer.py
