#!/bin/bash

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print banner
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  Calendar Screenshot App Service Setup   ${NC}"
echo -e "${GREEN}==========================================${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root or with sudo${NC}"
  exit 1
fi

# Get the username of the user who ran sudo
if [ -n "$SUDO_USER" ]; then
  USERNAME="$SUDO_USER"
else
  echo -e "${YELLOW}Enter the username for which the service should run:${NC}"
  read USERNAME
fi

# Get absolute path of app directory
APP_DIR=$(cd "$(dirname "$0")" && pwd)
echo -e "${GREEN}App directory: $APP_DIR${NC}"

# Check if Python virtual environment exists, create if not
VENV_PATH="$APP_DIR/venv"
if [ ! -d "$VENV_PATH" ]; then
  echo -e "${YELLOW}Creating Python virtual environment...${NC}"
  python3 -m venv "$VENV_PATH"
fi

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
"$VENV_PATH/bin/pip" install -r "$APP_DIR/requirements.txt"

# Create service file
SERVICE_FILE="/etc/systemd/system/calendar-screenshot.service"

echo -e "${YELLOW}Creating systemd service file...${NC}"
cat > "$SERVICE_FILE" << EOL
[Unit]
Description=Calendar Screenshot Analyzer
After=network.target
After=thunderbird.service

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$VENV_PATH/bin/python $APP_DIR/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# Set permissions
chmod 644 "$SERVICE_FILE"

# Reload systemd
echo -e "${YELLOW}Reloading systemd...${NC}"
systemctl daemon-reload

# Enable and start service
echo -e "${YELLOW}Enabling and starting service...${NC}"
systemctl enable calendar-screenshot.service
systemctl start calendar-screenshot.service

# Display status
echo -e "${YELLOW}Service status:${NC}"
systemctl status calendar-screenshot.service

echo -e "${GREEN}Installation complete!${NC}"
echo -e "${GREEN}The service will now start automatically at boot.${NC}"
echo -e "${YELLOW}You can manage the service with:${NC}"
echo -e "  - sudo systemctl start calendar-screenshot.service"
echo -e "  - sudo systemctl stop calendar-screenshot.service"
echo -e "  - sudo systemctl restart calendar-screenshot.service"
echo -e "  - sudo systemctl status calendar-screenshot.service"
echo -e "${GREEN}The application should be accessible at http://localhost:5000${NC}" 