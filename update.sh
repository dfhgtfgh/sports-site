#!/bin/bash
set -e
cd /opt/sports-site
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart sporthub
echo "✅ Обновлено: $(date)"
