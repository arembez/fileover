#!/bin/sh
# entrypoint.sh
# Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
# MIT License (see LICENSE or https://opensource.org/licenses/MIT)

set -e

echo "Looking for additional requirements.txt files in /fileover/app..."

find /fileover/app -name "requirements.txt" -type f | while read req; do
    echo "Installing dependencies from $req"
    pip install --no-cache-dir -r "$req"
done

echo "Starting FileOver server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8435