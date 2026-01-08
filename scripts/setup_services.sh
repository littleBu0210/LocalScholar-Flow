#!/bin/bash
# Docker service setup script
# Used to build and start Docker services required by LocalScholar-Flow
# Usage: bash setup_services.sh

set -e

# Set colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}🐳 LocalScholar-Flow Service Setup Tool${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker not found${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Error: Docker Compose not available${NC}"
    echo "Please ensure Docker Compose V2 is installed"
    exit 1
fi

echo -e "${GREEN}✅ Docker environment check passed${NC}"
echo ""

# Get absolute path of the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if models exist
MODELS_DIR="$SCRIPT_DIR/../models"

echo -e "${CYAN}[1/4] Checking model files...${NC}"

if [ ! -d "$MODELS_DIR/HY-MT1.5-1.8B" ]; then
    echo -e "${RED}❌ Hunyuan model not found${NC}"
    echo "   Please run first: bash scripts/download.sh"
    exit 1
fi

if [ ! -d "$MODELS_DIR/MinerU-VLM" ]; then
    echo -e "${RED}❌ MinerU model not found${NC}"
    echo "   Please run first: bash scripts/download.sh"
    exit 1
fi

echo -e "${GREEN}✅ Model files exist${NC}"
echo ""

# Fix model paths
echo -e "${CYAN}[2/4] Fixing model paths...${NC}"

fix_hunyuan_path() {
    local target_dir="$MODELS_DIR/HY-MT1.5-1.8B/current"
    local source_dir=""
    local rel_source_dir=""

    # Check ModelScope format
    if [ -d "$MODELS_DIR/HY-MT1.5-1.8B/Tencent-Hunyuan/HY-MT1___5-1___8B" ]; then
        source_dir="$MODELS_DIR/HY-MT1.5-1.8B/Tencent-Hunyuan/HY-MT1___5-1___8B"
        rel_source_dir="Tencent-Hunyuan/HY-MT1___5-1___8B"
    # Check HuggingFace format
    elif [ -d "$MODELS_DIR/HY-MT1.5-1.8B/models--tencent--HY-MT1.5-1.8B/snapshots" ]; then
        local snapshot_dir=$(find "$MODELS_DIR/HY-MT1.5-1.8B/models--tencent--HY-MT1.5-1.8B/snapshots" -maxdepth 1 -type d ! -name "snapshots" | head -1)
        if [ -n "$snapshot_dir" ]; then
            source_dir="$snapshot_dir"
            rel_source_dir=$(realpath --relative-to="$MODELS_DIR/HY-MT1.5-1.8B" "$snapshot_dir")
        fi
    fi

    if [ -z "$source_dir" ]; then
        return 1
    fi

    if [ -L "$target_dir" ]; then
        rm "$target_dir"
    fi

    cd "$MODELS_DIR/HY-MT1.5-1.8B"
    ln -s "$rel_source_dir" "current"
    cd - > /dev/null
}

fix_mineru_path() {
    local target_link="$MODELS_DIR/mineru.json"
    local vlm_path=""

    # Check HuggingFace format (priority)
    local hf_path=$(find "$MODELS_DIR/MinerU-VLM" -path "*/snapshots/*/config.json" \( -type f -o -type l \) 2>/dev/null | head -1)
    if [ -n "$hf_path" ]; then
        vlm_path=$(dirname "$hf_path")
    fi

    # If HuggingFace not found, check ModelScope format
    if [ -z "$vlm_path" ]; then
        local ms_path=$(find "$MODELS_DIR/MinerU-VLM" -path "*/OpenDataLab/MinerU2.5-2509-1.2B/config.json" \( -type f -o -type l \) 2>/dev/null | head -1)
        if [ -n "$ms_path" ]; then
            vlm_path=$(dirname "$ms_path")
        fi
    fi

    # If still not found, try other possible paths
    if [ -z "$vlm_path" ]; then
        local any_path=$(find "$MODELS_DIR/MinerU-VLM" -name "config.json" \( -type f -o -type l \) 2>/dev/null | head -1)
        if [ -n "$any_path" ]; then
            vlm_path=$(dirname "$any_path")
        fi
    fi

    if [ -z "$vlm_path" ]; then
        return 1
    fi

    local rel_path=$(realpath --relative-to="$MODELS_DIR" "$vlm_path")
    local container_vlm_path="/data/models/$rel_path"

    cat > "$target_link" <<EOF
{
    "config_version": "1.3.1",
    "models-dir": {
        "vlm": "$container_vlm_path"
    },
    "device-mode": "cuda",
    "layout-config": {
        "doclayout_yolo": "doclayout_yolo",
        "model_batch_size": 10
    },
    "formula-config": {
        "mfd_model": "yolo_v8_mfd",
        "mfr_model": "unimernet_small",
        "model_batch_size": 10
    }
}
EOF
}

cd "$MODELS_DIR"
fix_hunyuan_path
fix_mineru_path
cd - > /dev/null

echo -e "${GREEN}✅ Model paths fixed${NC}"
echo ""

# Check if images need to be built
echo -e "${CYAN}[3/4] Checking Docker images...${NC}"

BUILD_NEEDED=false

if ! docker images | grep -q "mineru.*latest"; then
    echo -e "${YELLOW}⚠️  MinerU image does not exist${NC}"
    BUILD_NEEDED=true
fi

if ! docker images | grep -q "localscholar-flow-hunyuan.*latest"; then
    echo -e "${YELLOW}⚠️  Hunyuan image does not exist${NC}"
    BUILD_NEEDED=true
fi

if [ "$BUILD_NEEDED" = false ]; then
    echo -e "${GREEN}✅ Docker images already exist${NC}"
    echo ""
    read -p "Rebuild images? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        BUILD_NEEDED=true
    fi
fi

# Build images
if [ "$BUILD_NEEDED" = true ]; then
    echo ""
    echo -e "${CYAN}[3/4] Building Docker images...${NC}"
    echo ""

    cd "$SCRIPT_DIR/.."

    echo -e "${YELLOW}Building MinerU service...${NC}"
    if docker compose build --no-cache mineru; then
        echo -e "${GREEN}✅ MinerU build complete${NC}"
    else
        echo -e "${RED}❌ MinerU build failed${NC}"
        exit 1
    fi
    echo ""

    echo -e "${YELLOW}Building Hunyuan service...${NC}"
    if docker compose build --no-cache hunyuan; then
        echo -e "${GREEN}✅ Hunyuan build complete${NC}"
    else
        echo -e "${RED}❌ Hunyuan build failed${NC}"
        exit 1
    fi
    echo ""

    echo -e "${GREEN}✅ Image build complete${NC}"
else
    echo -e "${GREEN}✅ Skipping image build${NC}"
fi

echo ""

# Start services
echo -e "${CYAN}[4/4] Starting Docker services...${NC}"
echo ""

cd "$SCRIPT_DIR/.."

echo -e "${YELLOW}Stopping existing containers...${NC}"
docker compose down 2>/dev/null || true
echo ""

echo -e "${YELLOW}Starting containers...${NC}"
docker compose up -d
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Docker container startup failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ Services started successfully!${NC}"
echo ""
echo -e "${YELLOW}Service information:${NC}"
echo -e "   MongoDB:        localhost:27016"
echo -e "   MinerU API:     http://localhost:8000"
echo -e "   Hunyuan API:    http://localhost:8001"
echo ""

echo -e "${YELLOW}Waiting for services to be fully ready...${NC}"
max_wait=120
waited=0
while [ $waited -lt $max_wait ]; do
    if curl -s http://localhost:8001/v1/models >/dev/null 2>&1; then
        echo -e "${GREEN}✅ All services ready${NC}"
        echo ""
        break
    fi
    sleep 2
    waited=$((waited + 2))
    echo -n "."
done

if [ $waited -ge $max_wait ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Services starting, please check status later${NC}"
    echo -e "   Run: docker compose logs -f"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Setup complete!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  Run workflow: ${CYAN}bash run_all.sh${NC}"
echo ""
