#!/bin/bash
# SHIELD - EC2 One-Click Setup Script
# Run this on a fresh Ubuntu 22.04 t2.micro instance
# Usage: bash setup.sh

set -e
echo "=========================================="
echo "  SHIELD EC2 Deployment"
echo "=========================================="

# 1. System packages
echo "[1/6] Installing system packages..."
sudo apt update -y
sudo apt install python3-pip python3-venv nginx git -y

# 2. Clone repo
echo "[2/6] Cloning SHIELD repository..."
cd /home/ubuntu
if [ -d "AWS_AI-FOR-BHARAT" ]; then
    cd AWS_AI-FOR-BHARAT && git pull origin main
else
    git clone https://github.com/BEAST04289/AWS_AI-FOR-BHARAT.git
    cd AWS_AI-FOR-BHARAT
fi

# 3. Python environment
echo "[3/6] Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Create .env file (EDIT THESE VALUES!)
echo "[4/6] Creating .env file..."
cat > .env << 'ENVFILE'
# IMPORTANT: Replace these with your actual AWS credentials
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY_HERE
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY_HERE
AWS_REGION=ap-south-1
BEDROCK_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
DYNAMODB_TABLE=shield-fingerprint
S3_BUCKET=shield-temp-upload
FLASK_ENV=production
DEMO_MODE=false
MAX_REQUESTS_PER_IP_PER_DAY=100
MAX_FILE_SIZE_MB=5
PORT=8000
ENVFILE

# 5. Setup systemd service (auto-restart on crash/reboot)
echo "[5/6] Creating systemd service..."
sudo tee /etc/systemd/system/shield.service > /dev/null << 'SERVICE'
[Unit]
Description=SHIELD AI Scam Detector
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/AWS_AI-FOR-BHARAT
Environment=PATH=/home/ubuntu/AWS_AI-FOR-BHARAT/.venv/bin:/usr/bin
ExecStart=/home/ubuntu/AWS_AI-FOR-BHARAT/.venv/bin/gunicorn app:app --bind 127.0.0.1:8000 --workers 2 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable shield
sudo systemctl start shield

# 6. Setup nginx reverse proxy
echo "[6/6] Configuring nginx..."
sudo tee /etc/nginx/sites-available/shield > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
    }
}
NGINX

sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/shield /etc/nginx/sites-enabled/shield
sudo nginx -t && sudo systemctl restart nginx

echo ""
echo "=========================================="
echo "  SHIELD is LIVE!"
echo "  URL: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo "=========================================="
echo ""
echo "Commands:"
echo "  sudo systemctl status shield    # Check status"
echo "  sudo journalctl -u shield -f    # View logs"
echo "  sudo systemctl restart shield   # Restart app"
