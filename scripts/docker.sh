#!/usr/bin/env bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_ROOT/docker"

# Docker Compose command with project name
COMPOSE_CMD="docker compose -p deer-flow-dev -f docker-compose-dev.yaml"

detect_sandbox_mode() {
    local config_file="$PROJECT_ROOT/config.yaml"
    local sandbox_use=""
    local provisioner_url=""

    if [ ! -f "$config_file" ]; then
        echo "local"
        return
    fi

    sandbox_use=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*use:[[:space:]]*/ {
            line=$0
            sub(/^[[:space:]]*use:[[:space:]]*/, "", line)
            print line
            exit
        }
    ' "$config_file")

    provisioner_url=$(awk '
        /^[[:space:]]*sandbox:[[:space:]]*$/ { in_sandbox=1; next }
        in_sandbox && /^[^[:space:]#]/ { in_sandbox=0 }
        in_sandbox && /^[[:space:]]*provisioner_url:[[:space:]]*/ {
            line=$0
            sub(/^[[:space:]]*provisioner_url:[[:space:]]*/, "", line)
            print line
            exit
        }
    ' "$config_file")

    if [[ "$sandbox_use" == *"deerflow.sandbox.local:LocalSandboxProvider"* ]]; then
        echo "local"
    elif [[ "$sandbox_use" == *"deerflow.community.aio_sandbox:AioSandboxProvider"* ]]; then
        if [ -n "$provisioner_url" ]; then
            echo "provisioner"
        else
            echo "aio"
        fi
    else
        echo "local"
    fi
}

# Cleanup function for Ctrl+C
cleanup() {
    echo ""
    echo -e "${YELLOW}Operation interrupted by user${NC}"
    exit 130
}

# Set up trap for Ctrl+C
trap cleanup INT TERM

docker_available() {
    # Check that the docker CLI exists
    if ! command -v docker >/dev/null 2>&1; then
        return 1
    fi

    # Check that the Docker daemon is reachable
    if ! docker info >/dev/null 2>&1; then
        return 1
    fi

    return 0
}

# Initialize: pre-pull the sandbox image so first Pod startup is fast
init() {
    echo "=========================================="
    echo "  DeerFlow Init — Pull Sandbox Image"
    echo "=========================================="
    echo ""

    SANDBOX_IMAGE="enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"

    # Detect sandbox mode from config.yaml
    local sandbox_mode
    sandbox_mode="$(detect_sandbox_mode)"

    # Skip image pull for local sandbox mode (no container image needed)
    if [ "$sandbox_mode" = "local" ]; then
        echo -e "${GREEN}Detected local sandbox mode — no Docker image required.${NC}"
        echo ""

        if docker_available; then
            echo -e "${GREEN}✓ Docker environment is ready.${NC}"
            echo ""
            echo -e "${YELLOW}Next step: make docker-start${NC}"
        else
            echo -e "${YELLOW}Docker does not appear to be installed, or the Docker daemon is not reachable.${NC}"
            echo "Local sandbox mode itself does not require Docker, but Docker-based workflows (e.g., docker-start) will fail until Docker is available."
            echo ""
            echo -e "${YELLOW}Install and start Docker, then run: make docker-init && make docker-start${NC}"
        fi

        return 0
    fi

    if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${SANDBOX_IMAGE}$"; then
        echo -e "${BLUE}Pulling sandbox image: $SANDBOX_IMAGE ...${NC}"
        echo ""

        if ! docker pull "$SANDBOX_IMAGE" 2>&1; then
            echo ""
            echo -e "${YELLOW}⚠ Failed to pull sandbox image.${NC}"
            echo ""
            echo "This is expected if:"
            echo "  1. You are using local sandbox mode (default — no image needed)"
            echo "  2. You are behind a corporate proxy or firewall"
            echo "  3. The registry requires authentication"
            echo ""
            echo -e "${GREEN}The Docker development environment can still be started.${NC}"
            echo "If you need AIO sandbox (container-based execution):"
            echo "  - Ensure you have network access to the registry"
            echo "  - Or configure a custom sandbox image in config.yaml"
            echo ""
            echo -e "${YELLOW}Next step: make docker-start${NC}"
            return 0
        fi
    else
        echo -e "${GREEN}Sandbox image already exists locally: $SANDBOX_IMAGE${NC}"
    fi

    echo ""
    echo -e "${GREEN}✓ Sandbox image is ready.${NC}"
    echo ""
    echo -e "${YELLOW}Next step: make docker-start${NC}"
}

# Auto-detect host IP and update ADS MCP configuration
# This ensures ADS MCP can connect to services on the host machine from inside Docker
# ADS MCP reads its server URL from .ads-mcp/config.json, not from environment variables
detect_and_update_ads_host_ip() {
    # ADS MCP config file location (on host) - 相对于 PROJECT_ROOT
    local ads_mcp_dir="${PROJECT_ROOT}/ads-agent-mcp/.ads-mcp"
    local ads_mcp_config="${ads_mcp_dir}/config.json"

    # 如果目录不存在，创建目录
    if [ ! -d "$ads_mcp_dir" ]; then
        echo -e "${BLUE}Creating ADS MCP config directory: $ads_mcp_dir${NC}"
        mkdir -p "$ads_mcp_dir"
    fi

    # 如果配置文件不存在，创建初始配置
    if [ ! -f "$ads_mcp_config" ]; then
        echo -e "${BLUE}Creating initial ADS MCP config: $ads_mcp_config${NC}"
        cat > "$ads_mcp_config" << 'EOF'
{
  "ads": {
    "server": {
      "url": "http://127.0.0.1:80"
    },
    "credentials": {
      "new": {
        "username": "",
        "password": ""
      },
      "default": {
        "username": "admin",
        "password": "Admin#123"
      }
    },
    "token": {
      "value": "",
      "expires": 0,
      "loginTime": 0,
      "usedBy": "default"
    }
  }
}
EOF
    fi

    echo -e "${BLUE}Using ADS MCP config: $ads_mcp_config${NC}"

    local ip=""

    # Try to detect host IP (works on Linux, macOS, and Windows Docker)
    # Method 1: Use ip route show default - get the SOURCE IP of the default route (Linux/macOS)
    # NOTE: This gets the LAN IP (src), NOT the gateway IP (via)
    if [ -z "$ip" ] && command -v ip >/dev/null 2>&1; then
        ip=$(ip route show default 2>/dev/null | awk '/default/ {for(i=1;i<=NF;i++) if($i=="src") print $(i+1); exit}' | head -1)
    fi

    # Method 2: Try to get IP from docker0 interface (Linux)
    if [ -z "$ip" ] && command -v ip >/dev/null 2>&1; then
        ip=$(ip -4 addr show docker0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
    fi

    # Method 3: Use hostname -I (common on Linux)
    if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi

    # Method 4: Use ipconfig on Windows (Git Bash or MSYS) - get host IP on LAN interface
    # NOTE: We use "Wireless" or "Ethernet" adapter pattern, NOT Default Gateway
    if [ -z "$ip" ] && command -v ipconfig >/dev/null 2>&1; then
        # Try to get the host's actual LAN IP (192.168.x.x pattern), not gateway
        ip=$(ipconfig 2>/dev/null | grep -E "IPv4|以太网" -A1 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | grep '^192\.168\.' | head -1)
    fi

    # Method 5: Use PowerShell to get host LAN IP (Windows native) - fallback
    if [ -z "$ip" ] && command -v powershell >/dev/null 2>&1; then
        ip=$(powershell -Command "\$idx = (Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Select-Object -First 1).InterfaceIndex; if (\$idx) { (Get-NetIPAddress -InterfaceIndex \$idx -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -First 1).IPAddress }" 2>/dev/null)
    fi

    # Skip if no IP found
    if [ -z "$ip" ]; then
        echo -e "${YELLOW}Could not detect host IP, ADS MCP may not be able to reach host services${NC}"
        return
    fi

    echo -e "${BLUE}Detected host IP: $ip${NC}"

    # Update ADS MCP config.json ads.server.url with detected IP
    # Always update the url field regardless of current value
    if grep -q '"url":' "$ads_mcp_config" 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's|"url": "[^"]*"|"url": "http://'"$ip"':80"|g' "$ads_mcp_config"
        else
            sed -i 's|"url": "[^"]*"|"url": "http://'"$ip"':80"|g' "$ads_mcp_config"
        fi
        echo -e "${GREEN}Updated ADS MCP server URL to http://${ip}:80${NC}"
    else
        echo -e "${YELLOW}ADS MCP config missing url field, skipping update${NC}"
    fi

    # Also update extensions_config.json (the env var consumed by the MCP process)
    local extensions_config="${PROJECT_ROOT}/extensions_config.json"
    if [ -f "$extensions_config" ]; then
        python3 -c "
import json
path = '$extensions_config'
with open(path) as f:
    cfg = json.load(f)
ads = cfg.get('mcpServers', {}).get('ads', {})
env = ads.get('env', {})
if 'ADS_API_BASE_URL' in env:
    env['ADS_API_BASE_URL'] = 'http://$ip:80'
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)
    print('Updated ADS_API_BASE_URL in extensions_config.json')
" 2>/dev/null && echo -e "${GREEN}Updated extensions_config.json ADS_API_BASE_URL to http://${ip}:80${NC}" || echo -e "${YELLOW}extensions_config.json ADS_API_BASE_URL not found or update failed, skipping${NC}"
    else
        echo -e "${YELLOW}extensions_config.json not found, skipping update${NC}"
    fi
}

# Start Docker development environment
start() {
    local sandbox_mode
    local services

    if [ "$#" -gt 0 ]; then
        echo -e "${YELLOW}Unknown option for start: $1${NC}"
        echo "Usage: $0 start"
        exit 1
    fi

    echo "=========================================="
    echo "  Starting DeerFlow Docker Development"
    echo "=========================================="
    echo ""

    sandbox_mode="$(detect_sandbox_mode)"

    services="frontend gateway nginx"
    if [ "$sandbox_mode" = "provisioner" ]; then
        services="frontend gateway provisioner nginx"
    fi

    echo -e "${BLUE}Runtime: Gateway embedded agent runtime${NC}"
    echo -e "${BLUE}Detected sandbox mode: $sandbox_mode${NC}"
    if [ "$sandbox_mode" = "provisioner" ]; then
        echo -e "${BLUE}Provisioner enabled (Kubernetes mode).${NC}"
    else
        echo -e "${BLUE}Provisioner disabled (not required for this sandbox mode).${NC}"
    fi
    echo ""
    
    # Set DEER_FLOW_ROOT for provisioner if not already set
    if [ -z "$DEER_FLOW_ROOT" ]; then
        export DEER_FLOW_ROOT="$PROJECT_ROOT"
        echo -e "${BLUE}Setting DEER_FLOW_ROOT=$DEER_FLOW_ROOT${NC}"
        echo ""
    fi
    
    # Ensure config.yaml exists before starting.
    if [ ! -f "$PROJECT_ROOT/config.yaml" ]; then
        if [ -f "$PROJECT_ROOT/config.example.yaml" ]; then
            cp "$PROJECT_ROOT/config.example.yaml" "$PROJECT_ROOT/config.yaml"
            echo ""
            echo -e "${YELLOW}============================================================${NC}"
            echo -e "${YELLOW}  config.yaml has been created from config.example.yaml.${NC}"
            echo -e "${YELLOW}  Please edit config.yaml to set your API keys and model   ${NC}"
            echo -e "${YELLOW}  configuration before starting DeerFlow.                  ${NC}"
            echo -e "${YELLOW}============================================================${NC}"
            echo ""
            echo -e "${YELLOW}  Recommended: run 'make setup' before starting Docker.    ${NC}"
            echo -e "${YELLOW}  Edit the file:  $PROJECT_ROOT/config.yaml${NC}"
            echo -e "${YELLOW}  Then run:        make docker-start${NC}"
            echo ""
            exit 0
        else
            echo -e "${YELLOW}✗ config.yaml not found and no config.example.yaml to copy from.${NC}"
            exit 1
        fi
    fi

    # Ensure BETTER_AUTH_SECRET exists in .env (required for Next.js prod mode).
    if [ ! -f "$PROJECT_ROOT/.env" ] || ! grep -q "BETTER_AUTH_SECRET=" "$PROJECT_ROOT/.env" 2>/dev/null; then
        local secret
        secret=$(python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null) || \
        secret=$(openssl rand -hex 16 2>/dev/null) || \
        secret="fallback-secret-$(date +%s)"
        echo "BETTER_AUTH_SECRET=$secret" >> "$PROJECT_ROOT/.env"
        echo -e "${BLUE}Created BETTER_AUTH_SECRET in .env${NC}"
    fi

    # Ensure extensions_config.json exists as a file before mounting.
    # Docker creates a directory when bind-mounting a non-existent host path.
    if [ ! -f "$PROJECT_ROOT/extensions_config.json" ]; then
        if [ -f "$PROJECT_ROOT/extensions_config.example.json" ]; then
            cp "$PROJECT_ROOT/extensions_config.example.json" "$PROJECT_ROOT/extensions_config.json"
            echo -e "${BLUE}Created extensions_config.json from example${NC}"
        else
            echo "{}" > "$PROJECT_ROOT/extensions_config.json"
            echo -e "${BLUE}Created empty extensions_config.json${NC}"
        fi
    fi

<<<<<<< HEAD
    # Auto-detect host IP and update ADS MCP configuration
    detect_and_update_ads_host_ip

    # Set nginx routing for gateway mode (envsubst in nginx container)
    if $gateway_mode; then
        export LANGGRAPH_UPSTREAM=gateway:8001
        export LANGGRAPH_REWRITE=/api/
    fi

    echo "Cleaning up old containers..."
    cd "$DOCKER_DIR" && $COMPOSE_CMD down > /dev/null 2>&1 || true

=======
>>>>>>> 7bf618de (Refactor DeerFlow to use Gateway's LangGraph-compatible API)
    echo "Building and starting containers..."
    cd "$DOCKER_DIR" && $COMPOSE_CMD up --build -d --remove-orphans $services
    echo ""
    echo "=========================================="
    echo "  DeerFlow Docker is starting!"
    echo "=========================================="
    echo ""
    echo "  🌐 Application: http://localhost:2026"
    echo "  📡 API Gateway: http://localhost:2026/api/*"
    echo "  🤖 Runtime:     Gateway embedded"
    echo "  API:            /api/langgraph/* → Gateway"
    echo ""
    echo "  📋 View logs: make docker-logs"
    echo "  🛑 Stop:      make docker-stop"
    echo ""
}

# View Docker development logs
logs() {
    local service=""
    
    case "$1" in
        --frontend)
            service="frontend"
            echo -e "${BLUE}Viewing frontend logs...${NC}"
            ;;
        --gateway)
            service="gateway"
            echo -e "${BLUE}Viewing gateway logs...${NC}"
            ;;
        --nginx)
            service="nginx"
            echo -e "${BLUE}Viewing nginx logs...${NC}"
            ;;
        --provisioner)
            service="provisioner"
            echo -e "${BLUE}Viewing provisioner logs...${NC}"
            ;;
        "")
            echo -e "${BLUE}Viewing all logs...${NC}"
            ;;
        *)
            echo -e "${YELLOW}Unknown option: $1${NC}"
            echo "Usage: $0 logs [--frontend|--gateway|--nginx|--provisioner]"
            exit 1
            ;;
    esac
    
    cd "$DOCKER_DIR" && $COMPOSE_CMD logs -f $service
}

# Stop Docker development environment
stop() {
    # DEER_FLOW_ROOT is referenced in docker-compose-dev.yaml; set it before
    # running compose down to suppress "variable is not set" warnings.
    if [ -z "$DEER_FLOW_ROOT" ]; then
        export DEER_FLOW_ROOT="$PROJECT_ROOT"
    fi
    echo "Stopping Docker development services..."
    cd "$DOCKER_DIR" && $COMPOSE_CMD down
    echo "Cleaning up sandbox containers..."
    "$SCRIPT_DIR/cleanup-containers.sh" deer-flow-sandbox 2>/dev/null || true
    echo -e "${GREEN}✓ Docker services stopped${NC}"
}

# Restart Docker development environment
restart() {
    echo "========================================"
    echo "  Restarting DeerFlow Docker Services"
    echo "========================================"
    echo ""

    # Auto-detect host IP and update ADS MCP configuration before restart
    detect_and_update_ads_host_ip

    echo ""
    echo -e "${BLUE}Restarting containers...${NC}"
    cd "$DOCKER_DIR" && $COMPOSE_CMD restart
    echo ""
    echo -e "${GREEN}✓ Docker services restarted${NC}"
    echo ""
    echo "  🌐 Application: http://localhost:2026"
    echo "  📋 View logs: make docker-logs"
    echo ""
}

# Show help
help() {
    echo "DeerFlow Docker Management Script"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  init              - Pull the sandbox image (speeds up first Pod startup)"
    echo "  start             - Start Docker services (auto-detects sandbox mode from config.yaml)"
    echo "  restart           - Restart all running Docker services"
    echo "  logs [option] - View Docker development logs"
    echo "                  --frontend   View frontend logs only"
    echo "                  --gateway    View gateway logs only"
    echo "                  --nginx      View nginx logs only"
    echo "                  --provisioner View provisioner logs only"
    echo "  stop          - Stop Docker development services"
    echo "  help          - Show this help message"
    echo ""
}

main() {
    # Main command dispatcher
    case "$1" in
        init)
            init
            ;;
        start)
            shift
            start "$@"
            ;;
        restart)
            restart
            ;;
        logs)
            logs "$2"
            ;;
        stop)
            stop
            ;;
        help|--help|-h|"")
            help
            ;;
        *)
            echo -e "${YELLOW}Unknown command: $1${NC}"
            echo ""
            help
            exit 1
            ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
