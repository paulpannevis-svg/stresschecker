#!/bin/bash
# deploy.sh — Upload en start StressChecker Flask app op Hostnet VPS
# Gebruik: bash deploy.sh
# Vereist: scp en ssh toegang tot root@185.107.90.250

VPS="root@185.107.90.250"
REMOTE_DIR="/opt/stresschecker"
DOMAIN="app.stresschecker.com"

echo "=== StressChecker deployment ==="

# 1. Maak remote directory aan
echo "[1/5] Directory aanmaken op VPS..."
ssh $VPS "mkdir -p $REMOTE_DIR/templates/pro $REMOTE_DIR/static/css $REMOTE_DIR/static/js $REMOTE_DIR/static/img"

# 2. Upload bestanden
echo "[2/5] Bestanden uploaden..."
scp app.py requirements.txt $VPS:$REMOTE_DIR/
scp -r templates/ $VPS:$REMOTE_DIR/
scp -r static/    $VPS:$REMOTE_DIR/

# 3. Installeer dependencies
echo "[3/5] Python packages installeren..."
ssh $VPS "cd $REMOTE_DIR && pip3 install -r requirements.txt -q"

# 4. Systemd service aanmaken
echo "[4/5] Systemd service aanmaken..."
ssh $VPS "cat > /etc/systemd/system/stresschecker.service << 'EOF'
[Unit]
Description=StressChecker Flask App
After=network.target

[Service]
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/gunicorn --workers 2 --bind 127.0.0.1:8080 app:app
Restart=always
Environment=SC_SECRET_KEY=VERANDER-DIT-IN-PRODUCTIE
Environment=SC_DB_PATH=/opt/ic-license-server/data/saas_licenses.db

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable stresschecker
systemctl restart stresschecker"

# 5. Nginx configuratie bijwerken
echo "[5/5] Nginx configuratie..."
ssh $VPS "cat > /etc/nginx/sites-available/stresschecker << 'EOF'
server {
    listen 80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    location /static/ {
        alias $REMOTE_DIR/static/;
        expires 7d;
        add_header Cache-Control \"public, immutable\";
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
ln -sf /etc/nginx/sites-available/stresschecker /etc/nginx/sites-enabled/stresschecker
nginx -t && systemctl reload nginx"

echo ""
echo "=== Klaar! ==="
echo "App live op: https://$DOMAIN"
echo ""
echo "Status controleren: ssh $VPS 'systemctl status stresschecker'"
echo "Logs bekijken:       ssh $VPS 'journalctl -u stresschecker -f'"
