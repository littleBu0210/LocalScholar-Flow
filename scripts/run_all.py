#!/usr/bin/env python3
"""
LocalScholar-Flow Workflow Runner (Cross-platform)
Automates PDF processing and translation workflow
Replaces: run_all.sh

Usage:
    python scripts/run_all.py
"""
import os
import sys
import platform
import subprocess
import time
import urllib.request
from pathlib import Path
from loguru import logger


# ============================================
# Cross-platform utilities
# ============================================

def is_windows():
    """Check if running on Windows"""
    return platform.system() == 'Windows'


def activate_conda_env(env_name="LocalScholar-Flow"):
    """
    Verify conda environment is active
    On Unix, can also activate the environment
    """
    # Check if we're already in the right environment
    conda_env = os.environ.get('CONDA_DEFAULT_ENV')
    if conda_env == env_name:
        logger.success(f"✅ Conda environment active: {env_name}")
        return True

    # Try to activate on Unix systems
    if not is_windows():
        conda_paths = [
            Path.home() / "anaconda3" / "etc" / "profile.d" / "conda.sh",
            Path.home() / "miniconda3" / "etc" / "profile.d" / "conda.sh",
        ]

        for conda_sh in conda_paths:
            if conda_sh.exists():
                try:
                    # Source conda.sh and activate
                    result = subprocess.run(
                        f"source {conda_sh} && conda activate {env_name}",
                        shell=True,
                        executable="/bin/bash",
                        capture_output=True
                    )
                    if result.returncode == 0:
                        logger.success(f"✅ Conda environment activated: {env_name}")
                        return True
                except Exception as e:
                    logger.debug(f"Could not activate conda: {e}")
                    continue

    # On Windows or if activation failed, just check if conda is available
    try:
        result = subprocess.run(
            ["conda", "env", "list"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=True
        )
        if env_name in result.stdout:
            logger.warning(
                f"⚠️  Conda environment '{env_name}' exists but may not be active"
            )
            logger.warning(
                "   Please activate it first: conda activate LocalScholar-Flow"
            )
            return False
        else:
            logger.error(f"❌ Conda environment '{env_name}' not found")
            logger.error(
                "   Please create it first using the project setup instructions"
            )
            return False
    except Exception as e:
        logger.error(f"❌ Failed to check conda environment: {e}")
        logger.error("   Please ensure conda is installed and environment is active")
        return False


def run_python_script(script_path, description):
    """
    Run a Python script
    :param script_path: Path to the Python script
    :param description: Description of what the script does
    :return: True if successful, False otherwise
    """
    logger.info(f"{description}")

    script = Path(script_path)
    if not script.exists():
        logger.error(f"❌ Script not found: {script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            check=True,
            capture_output=False,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        logger.success(f"✅ {description.replace('[', '').replace(']', '')} complete")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {description.replace('[', '').replace(']', '')} failed")
        logger.error(f"   Exit code: {e.returncode}")
        return False
    except Exception as e:
        logger.error(f"❌ Error running script: {e}")
        return False


def compose(project_dir, *args):
    """Run Docker Compose from the project directory."""
    result = subprocess.run(["docker", "compose", *args], cwd=project_dir)
    return result.returncode == 0


def wait_for_url(url, timeout=300):
    """Wait until an HTTP endpoint answers successfully."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def select_gpu_service(project_dir, service):
    """Keep only one vLLM model resident, required for 8GB GPUs."""
    other = "hunyuan" if service == "mineru" else "mineru"
    logger.info(f"Switching GPU service: {other} -> {service}")
    if not compose(project_dir, "stop", other):
        return False
    if not compose(project_dir, "up", "-d", "mongodb", service):
        return False
    ready_url = ("http://localhost:8000/docs" if service == "mineru"
                 else "http://localhost:8001/v1/models")
    if not wait_for_url(ready_url):
        logger.error(f"Service did not become ready: {service}")
        return False
    return True

# ============================================
# Workflow steps
# ============================================

def step_1_generate_state(project_dir):
    """Step 1: Generate state (scan PDF files from pdfs directory)"""
    logger.info("")
    logger.info("[1/3] Scanning pdfs directory and generating state...")

    script = project_dir / "src" / "generate_state.py"
    return run_python_script(
        script,
        "[1/3] Generating state..."
    )


def step_2_pdf_to_markdown(project_dir):
    """Step 2: PDF to Markdown conversion"""
    logger.info("")
    logger.info("[2/3] Converting PDF to Markdown...")
    logger.info("   Input: pdfs/*.pdf")
    logger.info("   Output: output/pdf2md/")

    script = project_dir / "src" / "pdf_to_md.py"
    success = run_python_script(
        script,
        "[2/3] Converting PDF to Markdown..."
    )
    return success


def step_3_translate_markdown(project_dir):
    """Step 3: Translate Markdown"""
    logger.info("")
    logger.info("[3/3] Translating Markdown...")
    logger.info("   Input: output/pdf2md/")
    logger.info("   Output: output/mdTrans/")

    script = project_dir / "src" / "translate_md.py"
    success = run_python_script(
        script,
        "[3/3] Translating Markdown..."
    )
    return success


def display_output_structure():
    """Display output directory structure"""
    logger.info("")
    logger.info("📂 Output directory structure:")
    logger.info("   pdfs/              → PDF source files")
    logger.info("   output/pdf2md/     → PDF converted to Markdown")
    logger.info("   output/mdTrans/    → Translated Markdown")
    logger.info("")


# ============================================
# Main workflow
# ============================================

def main():
    """Main workflow function"""
    logger.info("=" * 60)
    logger.info("📄 PDF Processing and Translation Automation Workflow")
    logger.info("=" * 60)
    logger.info("")

    # Get project directory
    script_dir = Path(__file__).parent.absolute()
    project_dir = script_dir.parent

    # Step 1: Generate state
    if not compose(project_dir, "up", "-d", "mongodb"):
        logger.error("❌ Could not start MongoDB")
        sys.exit(1)
    if not step_1_generate_state(project_dir):
        logger.error("")
        logger.error("❌ State generation failed")
        sys.exit(1)

    # Step 2: PDF to Markdown
    if not select_gpu_service(project_dir, "mineru"):
        sys.exit(1)
    if not step_2_pdf_to_markdown(project_dir):
        logger.error("")
        logger.error("❌ PDF conversion failed")
        sys.exit(1)

    # Step 3: Translate Markdown
    if not select_gpu_service(project_dir, "hunyuan"):
        sys.exit(1)
    if not step_3_translate_markdown(project_dir):
        logger.error("")
        logger.error("❌ Translation failed")
        sys.exit(1)

    # All steps complete
    logger.info("")
    logger.success("=" * 60)
    logger.success("✅ All steps completed!")
    logger.success("=" * 60)

    # Display output structure
    display_output_structure()


if __name__ == "__main__":
    main()
