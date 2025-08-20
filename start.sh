#!/bin/sh

set -e

echo "Starting Flask server..."
python server.py &

echo "Starting Discord bot..."
python discord_bot.py
