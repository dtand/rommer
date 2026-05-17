#!/bin/bash
# Start all rommer services for development
# Usage: ./scripts/dev.sh
# Stop:  Ctrl+C (kills all)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}Starting Rommer dev environment...${NC}"

# Activate venv
source .venv/bin/activate

# Trap Ctrl+C to kill all background processes
cleanup() {
    echo -e "\n${CYAN}Shutting down...${NC}"
    kill 0 2>/dev/null
    wait 2>/dev/null
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start backend
echo -e "${CYAN}[1/3] Backend${NC} → http://localhost:8000"
uvicorn rommer.backend.main:app --port 8000 --reload &

# Start worker daemon
echo -e "${CYAN}[2/3] Worker${NC} → polling for jobs"
rommer worker start --max-workers 4 &

# Start frontend
echo -e "${CYAN}[3/3] Frontend${NC} → http://localhost:5174"
cd web && npm run dev &

echo ""
echo -e "${GREEN}All services running. Press Ctrl+C to stop.${NC}"
echo ""

# Wait for any process to exit
wait
