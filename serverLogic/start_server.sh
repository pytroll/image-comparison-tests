#!/bin/bash
# Funktion zum Beenden des Skripts bei Fehlern
set -e

# Pfade und Variablen definieren
PROJECT_DIR="/home/bildabgleich/pytroll-image-comparison-tests/serverLogic"
cd $PROJECT_DIR

# Überprüfen, ob Debug-Modus aktiviert ist
IS_DEBUG=$(python3 -c "from config import Config; print(Config.DEBUG)")
BASE_PATH=$(python3 -c "from config import Config; print(Config.CLONE_DIR_BASE)")

if [ "$IS_DEBUG" == "True" ]; then
    echo "Starting Flask server in development mode..."
    bash -c "source $BASE_PATH/venv/bin/activate && \
                     python3 $PROJECT_DIR/server.py"
else
    echo "Starting Flask server with Gunicorn in production mode..."
    bash -c "source $BASE_PATH/venv/bin/activate && \
                     gunicorn -w 4 -b 0.0.0.0:8080 \
                     'server:create_app()' \
                     --access-logfile /var/log/gunicorn/access.log \
                     --error-logfile /var/log/gunicorn/error.log"
fi

# Skript enden lassen
set +e
