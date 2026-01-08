#!/bin/bash
# Model download script
# Used to download model files required by MinerU and Hunyuan
# Usage: bash download.sh [modelscope|huggingface]
# Default is modelscope

set -e

# Set colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Activate Conda environment
source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null
conda activate LocalScholar-Flow 2>/dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to activate Conda environment: LocalScholar-Flow${NC}"
    exit 1
fi

# Get download source parameter, default is modelscope
SOURCE=${1:-modelscope}

# Validate parameter
if [[ "$SOURCE" != "modelscope" && "$SOURCE" != "huggingface" ]]; then
    echo -e "${RED}❌ Error: Unsupported download source '$SOURCE'${NC}"
    echo ""
    echo "Usage: bash download.sh [modelscope|huggingface]"
    echo ""
    echo "Parameter description:"
    echo "  modelscope   - Download from ModelScope (default)"
    echo "  huggingface - Download from HuggingFace"
    echo ""
    echo "Examples:"
    echo "  bash download.sh              # Use default ModelScope"
    echo "  bash download.sh modelscope   # Download from ModelScope"
    echo "  bash download.sh huggingface # Download from HuggingFace"
    exit 1
fi

MODELS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models"

# ============================================
# Model path fix functions
# ============================================

fix_hunyuan_path() {
    local target_dir="$MODELS_DIR/HY-MT1.5-1.8B/current"
    local source_dir=""
    local rel_source_dir=""

    echo "[1/2] Checking Hunyuan model..."

    # Check ModelScope format
    if [ -d "$MODELS_DIR/HY-MT1.5-1.8B/Tencent-Hunyuan/HY-MT1___5-1___8B" ]; then
        source_dir="$MODELS_DIR/HY-MT1.5-1.8B/Tencent-Hunyuan/HY-MT1___5-1___8B"
        rel_source_dir="Tencent-Hunyuan/HY-MT1___5-1___8B"
        echo -e "  ${GREEN}✅ Found ModelScope format model${NC}"

    # Check HuggingFace format
    elif [ -d "$MODELS_DIR/HY-MT1.5-1.8B/models--tencent--HY-MT1.5-1.8B/snapshots" ]; then
        local snapshot_dir=$(find "$MODELS_DIR/HY-MT1.5-1.8B/models--tencent--HY-MT1.5-1.8B/snapshots" -maxdepth 1 -type d ! -name "snapshots" | head -1)
        if [ -n "$snapshot_dir" ]; then
            source_dir="$snapshot_dir"
            rel_source_dir=$(realpath --relative-to="$MODELS_DIR/HY-MT1.5-1.8B" "$snapshot_dir")
            echo -e "  ${GREEN}✅ Found HuggingFace format model${NC}"
        fi
    fi

    if [ -z "$source_dir" ]; then
        echo -e "  ${RED}❌ No valid Hunyuan model found${NC}"
        return 1
    fi

    if [ ! -f "$source_dir/config.json" ]; then
        echo -e "  ${RED}❌ Invalid model directory: missing config.json${NC}"
        return 1
    fi

    if [ -L "$target_dir" ]; then
        rm "$target_dir"
        echo "  🗑️  Deleted old symlink"
    fi

    cd "$MODELS_DIR/HY-MT1.5-1.8B"
    ln -s "$rel_source_dir" "current"
    cd - > /dev/null

    echo -e "  ${GREEN}✅ Created symlink: current -> $rel_source_dir (relative path)${NC}"
    echo ""
}

fix_mineru_path() {
    local target_link="$MODELS_DIR/mineru.json"
    local vlm_path=""

    echo "[2/2] Checking MinerU model..."

    # Check HuggingFace format (priority)
    local hf_path=$(find "$MODELS_DIR/MinerU-VLM" -path "*/snapshots/*/config.json" \( -type f -o -type l \) 2>/dev/null | head -1)
    if [ -n "$hf_path" ]; then
        vlm_path=$(dirname "$hf_path")
        echo -e "  ${GREEN}✅ Found HuggingFace format model${NC}"
    fi

    # If HuggingFace not found, check ModelScope format
    if [ -z "$vlm_path" ]; then
        local ms_path=$(find "$MODELS_DIR/MinerU-VLM" -path "*/OpenDataLab/MinerU2.5-2509-1.2B/config.json" \( -type f -o -type l \) 2>/dev/null | head -1)
        if [ -n "$ms_path" ]; then
            vlm_path=$(dirname "$ms_path")
            echo -e "  ${GREEN}✅ Found ModelScope format model${NC}"
        fi
    fi

    # If still not found, try other possible paths
    if [ -z "$vlm_path" ]; then
        local any_path=$(find "$MODELS_DIR/MinerU-VLM" -name "config.json" \( -type f -o -type l \) 2>/dev/null | head -1)
        if [ -n "$any_path" ]; then
            vlm_path=$(dirname "$any_path")
            echo -e "  ${GREEN}✅ Found model (generic format)${NC}"
        fi
    fi

    if [ -z "$vlm_path" ]; then
        echo -e "  ${RED}❌ No valid MinerU model found${NC}"
        echo "     Please check $MODELS_DIR/MinerU-VLM directory"
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

    echo -e "  ${GREEN}✅ Updated configuration file: mineru.json${NC}"
    echo "     VLM path: $container_vlm_path"
    echo ""
}

fix_model_paths() {
    echo -e "${CYAN}==========================================${NC}"
    echo -e "${CYAN}  Model Path Compatibility Fix Tool${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo ""
    echo "Model directory: $MODELS_DIR"
    echo ""

    cd "$MODELS_DIR"

    fix_hunyuan_path
    fix_mineru_path

    echo -e "${CYAN}==========================================${NC}"
    echo -e "${GREEN}  ✅ Model path fix complete!${NC}"
    echo -e "${CYAN}==========================================${NC}"
    echo ""
    echo "Unified path description:"
    echo "  Hunyuan model: ./models/HY-MT1.5-1.8B/current"
    echo "  MinerU config:  ./models/mineru.json"
    echo ""
}

# ============================================
# Main execution flow
# ============================================

echo -e "${CYAN}=========================================${NC}"
echo -e "${CYAN}  Paper Flow - Model Download Tool${NC}"
echo -e "${CYAN}=========================================${NC}"
echo ""
echo -e "📦 Download source: ${YELLOW}$SOURCE${NC}"
echo ""
echo -e "${CYAN}📦 Starting model download...${NC}"
echo ""

# Run Python download script, pass download source parameter
python scripts/download_models.py --source "$SOURCE"

echo ""
echo -e "${GREEN}✅ Model download complete!${NC}"
echo ""
echo "Model file locations:"
echo "  - MinerU model: ./models/MinerU-VLM/"
echo "  - Hunyuan model: ./models/HY-MT1.5-1.8B/"
echo ""

# Automatically fix paths
fix_model_paths

echo -e "${CYAN}==========================================${NC}"
echo -e "${YELLOW}  📦 Next Steps${NC}"
echo -e "${CYAN}==========================================${NC}"
echo ""
echo -e "For first-time use, you need to build and start Docker services:"
echo -e "  ${CYAN}bash scripts/setup_services.sh${NC}"
echo ""
