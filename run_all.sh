#!/bin/bash

# Set colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}📄 PDF Processing and Translation Automation Workflow${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"

# 0. Activate Conda environment
source ~/anaconda3/etc/profile.d/conda.sh 2>/dev/null || source ~/miniconda3/etc/profile.d/conda.sh 2>/dev/null
conda activate LocalScholar-Flow 2>/dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to activate Conda environment: LocalScholar-Flow${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Conda environment activated: LocalScholar-Flow${NC}"

# 1. Generate state (scan PDF files from pdfs directory)
echo -e "\n${CYAN}[1/3] Scanning pdfs directory and generating state...${NC}"
python src/generate_state.py
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ State generation failed${NC}"
    exit 1
fi

# 2. PDF to Markdown (read from pdfs directory, output to output/pdf2md directory)
echo -e "\n${CYAN}[2/3] Converting PDF to Markdown...${NC}"
echo -e "${YELLOW}   Input: pdfs/*.pdf${NC}"
echo -e "${YELLOW}   Output: output/pdf2md/${NC}"
python src/pdf_to_md.py
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ PDF conversion failed${NC}"
    exit 1
fi

# 3. Translate Markdown (read from output/pdf2md, output to output/mdTrans)
echo -e "\n${CYAN}[3/3] Translating Markdown...${NC}"
echo -e "${YELLOW}   Input: output/pdf2md/${NC}"
echo -e "${YELLOW}   Output: output/mdTrans/${NC}"
python src/translate_md.py
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Translation failed${NC}"
    exit 1
fi

echo -e "\n${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ All steps completed!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "\n${YELLOW}📂 Output directory structure:${NC}"
echo -e "   pdfs/              → PDF source files"
echo -e "   output/pdf2md/     → PDF converted to Markdown"
echo -e "   output/mdTrans/    → Translated Markdown"
