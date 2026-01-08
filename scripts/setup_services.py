#!/usr/bin/env python3
"""
LocalScholar-Flow Service Setup Script (Cross-platform)
Used to build and start Docker services required by LocalScholar-Flow
Replaces: scripts/setup_services.sh

Usage:
    python scripts/setup_services.py
"""
import os
import sys
import json
import shutil
import time
import platform
import subprocess
from pathlib import Path
from loguru import logger


# ============================================
# Cross-platform utilities
# ============================================

def is_windows():
    """Check if running on Windows"""
    return platform.system() == 'Windows'


def run_command(cmd, check=True, capture_output=False):
    """
    Run command with cross-platform support
    :param cmd: Command as list or string
    :param check: Raise exception if command fails
    :param capture_output: Capture stdout and stderr
    :return: CompletedProcess object
    """
    if isinstance(cmd, str):
        # For string commands, use shell
        shell = True
        if is_windows():
            # On Windows, might need to handle differently
            pass
    else:
        shell = False

    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            check=check,
            capture_output=capture_output,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        if capture_output:
            logger.error(f"Command failed: {cmd}")
            logger.error(f"Error output: {e.stderr}")
        raise


def check_docker():
    """Check if Docker is installed and running"""
    logger.info("Checking Docker environment...")

    # Check Docker is installed
    try:
        result = run_command(["docker", "--version"], check=True, capture_output=True)
        logger.success(f"✅ Docker found: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("❌ Error: Docker not found")
        logger.error("Please install Docker first: https://docs.docker.com/get-docker/")
        return False

    # Check Docker Compose is available
    try:
        result = run_command(
            ["docker", "compose", "version"],
            check=True,
            capture_output=True
        )
        logger.success(f"✅ Docker Compose found: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("❌ Error: Docker Compose not available")
        logger.error("Please ensure Docker Compose V2 is installed")
        return False

    # Check Docker is running
    try:
        run_command(["docker", "ps"], check=True, capture_output=True)
        logger.success("✅ Docker is running")
    except subprocess.CalledProcessError:
        logger.error("❌ Error: Docker is not running")
        logger.error("Please start Docker Desktop or Docker daemon")
        return False

    return True


def create_symlink(source, target):
    """
    Create symlink with cross-platform support
    Uses relative paths for Docker compatibility
    On Windows without admin privileges, falls back to junction or copy
    """
    target = Path(target)
    source = Path(source)

    # Remove existing symlink/file with cross-platform support
    # On Windows, os.remove() works for both file and directory symlinks
    # On Unix, use rmdir() for directory symlinks, unlink() for file symlinks
    if target.exists() or target.is_symlink():
        try:
            if is_windows():
                # Windows: use os.remove() for all symlink types
                os.remove(str(target))
            else:
                # Unix: use os.remove() for symlinks (works for both file and directory)
                # For real directories, we need shutil.rmtree()
                if target.is_symlink():
                    os.remove(str(target))
                elif target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink()
            logger.debug(f"Removed existing target: {target}")
        except Exception as e:
            logger.debug(f"Could not remove existing target with normal method: {e}")
            # Fallback to force removal
            try:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
                logger.debug(f"Force removed target: {target}")
            except Exception as e2:
                logger.warning(f"Failed to remove target {target}: {e2}")
                # Continue anyway, symlink_to might still work

    try:
        # Calculate relative path from target's parent to source
        # This is crucial for Docker volume mounting compatibility
        try:
            relative_source = os.path.relpath(source, target.parent)
        except ValueError:
            # If on different drives (Windows), fall back to absolute path
            relative_source = source

        # Double-check target doesn't exist before creating symlink
        if target.exists() or target.is_symlink():
            logger.debug(f"Target still exists, removing again: {target}")
            try:
                if target.is_symlink() or target.is_file():
                    os.remove(str(target))
                elif target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
            except Exception as e:
                logger.debug(f"Failed to remove target again: {e}")

        # Try creating a symlink with relative path
        target.symlink_to(relative_source)
        logger.info(f"✅ Created symlink: {target} -> {relative_source}")
        return True
    except FileExistsError:
        # This shouldn't happen after our checks, but handle it gracefully
        logger.warning(f"⚠️  Symlink target already exists: {target}")
        # Verify it's pointing to the right place
        if target.is_symlink():
            try:
                existing_target = os.readlink(target)
                logger.info(f"   Existing symlink points to: {existing_target}")
                return True
            except Exception:
                pass
        return False
    except OSError as e:
        if is_windows():
            # Windows: try junction for directories
            if source.is_dir():
                try:
                    import ctypes
                    from ctypes import wintypes

                    # Create junction (requires no admin rights)
                    CreateJunction = ctypes.windll.kernel32.CreateJunctionW
                    CreateJunction.argtypes = [
                        wintypes.LPCWSTR,
                        wintypes.LPCWSTR
                    ]

                    target.mkdir(parents=True, exist_ok=True)
                    if CreateJunction(str(target), str(source)):
                        logger.info(f"✅ Created junction: {target} -> {source}")
                        return True
                except Exception:
                    pass

            # Fallback: copy directory (slow but works)
            logger.warning(f"⚠️ Cannot create symlink, copying files instead...")
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
                logger.info(f"✅ Copied directory: {target}")
                return True
            else:
                shutil.copy2(source, target)
                logger.info(f"✅ Copied file: {target}")
                return True
        else:
            logger.error(f"❌ Failed to create symlink: {e}")
            return False


def find_path_by_pattern(base_dir, pattern):
    """
    Find paths matching a pattern
    Returns list of matching paths
    """
    base_path = Path(base_dir)
    if not base_path.exists():
        return []

    # Use pathlib's glob for cross-platform pattern matching
    return list(base_path.glob(pattern))


# ============================================
# Model path fixing
# ============================================

def fix_hunyuan_path(models_dir):
    """Fix Hunyuan model path - create 'current' symlink"""
    logger.info("[2/4] Fixing model paths...")
    logger.info("  Checking Hunyuan model...")

    models_path = Path(models_dir) / "HY-MT1.5-1.8B"
    target_dir = models_path / "current"
    source_dir = None

    # Check ModelScope format
    ms_path = models_path / "Tencent-Hunyuan" / "HY-MT1___5-1___8B"
    if ms_path.exists() and ms_path.is_dir():
        source_dir = ms_path
        logger.info("  ✅ Found ModelScope format model")

    # Check HuggingFace format
    if source_dir is None:
        hf_patterns = list(models_path.glob("models--tencent--HY-MT1.5-1.8B/snapshots/*"))
        if hf_patterns:
            source_dir = hf_patterns[0]
            logger.info("  ✅ Found HuggingFace format model")

    if source_dir is None:
        logger.warning("  ⚠️  Hunyuan model not found or already fixed")
        return False

    # Check config.json exists
    config_file = source_dir / "config.json"
    if not config_file.exists():
        logger.error("  ❌ Invalid model directory: missing config.json")
        return False

    # Remove old symlink if exists - use cross-platform removal
    if target_dir.is_symlink() or target_dir.exists():
        try:
            if is_windows():
                # Windows: use os.remove() for all symlink types
                os.remove(str(target_dir))
            else:
                # Unix: handle directory vs file symlinks
                if target_dir.is_dir() and target_dir.is_symlink():
                    target_dir.rmdir()
                else:
                    target_dir.unlink()
            logger.info("  🗑️  Deleted old symlink")
        except Exception as e:
            logger.debug(f"Could not remove existing symlink with normal method: {e}")
            # Fallback to force removal
            if target_dir.is_dir():
                shutil.rmtree(target_dir, ignore_errors=True)
            else:
                target_dir.unlink(missing_ok=True)

    # Create symlink
    success = create_symlink(source_dir, target_dir)
    if success:
        logger.success("  ✅ Hunyuan model path fixed")

    return success


def fix_mineru_path(models_dir):
    """Fix MinerU model path - generate mineru.json config"""
    logger.info("  Checking MinerU model...")

    vlm_path = None
    mineru_base = Path(models_dir) / "MinerU-VLM"

    # Check HuggingFace format (priority)
    hf_paths = find_path_by_pattern(mineru_base, "**/snapshots/*/config.json")
    if hf_paths:
        vlm_path = hf_paths[0].parent
        logger.info("  ✅ Found HuggingFace format model")

    # If HuggingFace not found, check ModelScope format
    if vlm_path is None:
        ms_paths = find_path_by_pattern(
            mineru_base,
            "**/OpenDataLab/MinerU2.5-2509-1.2B/config.json"
        )
        if ms_paths:
            vlm_path = ms_paths[0].parent
            logger.info("  ✅ Found ModelScope format model")

    # If still not found, try generic search
    if vlm_path is None:
        all_paths = find_path_by_pattern(mineru_base, "**/config.json")
        # Filter out temporary paths
        valid_paths = [
            p.parent for p in all_paths
            if ".____" not in str(p) and "/." not in str(p).replace("\\", "/")
        ]
        if valid_paths:
            vlm_path = valid_paths[0]
            logger.info("  ✅ Found model (generic format)")

    if vlm_path is None:
        logger.warning("  ⚠️  MinerU model not found or already configured")
        return False

    # Calculate relative path
    try:
        models_path = Path(models_dir)
        rel_path = vlm_path.relative_to(models_path)
    except ValueError:
        logger.error("  ❌ Cannot calculate relative path")
        return False

    # Container path
    container_vlm_path = f"/data/models/{rel_path.as_posix()}"

    # Generate config JSON
    config = {
        "config_version": "1.3.1",
        "models-dir": {
            "vlm": container_vlm_path
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

    # Save config file
    config_file = Path(models_dir) / "mineru.json"
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.success("  ✅ MinerU configuration updated")
        return True
    except Exception as e:
        logger.error(f"  ❌ Failed to write configuration file: {e}")
        return False


def check_models_exist(models_dir):
    """Check if required models exist"""
    logger.info("[1/4] Checking model files...")

    models_path = Path(models_dir)

    hunyuan_path = models_path / "HY-MT1.5-1.8B"
    if not hunyuan_path.exists():
        logger.error("❌ Hunyuan model not found")
        logger.error("   Please run first: python scripts/download_models.py")
        return False

    mineru_path = models_path / "MinerU-VLM"
    if not mineru_path.exists():
        logger.error("❌ MinerU model not found")
        logger.error("   Please run first: python scripts/download_models.py")
        return False

    logger.success("✅ Model files exist")
    return True


def fix_model_paths(models_dir):
    """Fix all model paths"""
    success = True

    if not fix_hunyuan_path(models_dir):
        # Not necessarily a failure - might already be fixed
        pass

    if not fix_mineru_path(models_dir):
        # Not necessarily a failure - might already be fixed
        pass

    if success:
        logger.success("✅ Model paths fixed")

    return success


def check_docker_images():
    """Check if Docker images need to be built"""
    logger.info("[3/4] Checking Docker images...")

    build_needed = False

    # Check MinerU image
    try:
        result = run_command(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
            capture_output=True,
            check=True
        )
        images = result.stdout.strip().split('\n')

        if not any("mineru" in img and "latest" in img for img in images):
            logger.warning("⚠️  MinerU image does not exist")
            build_needed = True
        else:
            logger.success("✅ MinerU image exists")
    except subprocess.CalledProcessError:
        build_needed = True

    # Check Hunyuan image
    try:
        if not build_needed:
            result = run_command(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                check=True
            )
            images = result.stdout.strip().split('\n')

            if not any("localscholar-flow-hunyuan" in img and "latest" in img for img in images):
                logger.warning("⚠️  Hunyuan image does not exist")
                build_needed = True
            else:
                logger.success("✅ Hunyuan image exists")
    except subprocess.CalledProcessError:
        build_needed = True

    if not build_needed:
        logger.success("✅ Docker images already exist")
        # Ask user if they want to rebuild (handle non-interactive environments)
        try:
            response = input("Rebuild images? (y/N): ").strip().lower()
            if response == 'y':
                build_needed = True
        except EOFError:
            # Non-interactive environment, don't rebuild
            logger.info("Non-interactive environment detected, skipping rebuild")

    return build_needed


def build_docker_images(project_dir):
    """Build Docker images"""
    logger.info("[3/4] Building Docker images...")
    logger.info("")

    # Change to project directory
    original_dir = os.getcwd()
    os.chdir(project_dir)

    try:
        # Build MinerU service
        logger.info("Building MinerU service...")
        try:
            run_command(["docker", "compose", "build", "--no-cache", "mineru"], check=True)
            logger.success("✅ MinerU build complete")
        except subprocess.CalledProcessError:
            logger.error("❌ MinerU build failed")
            return False

        logger.info("")

        # Build Hunyuan service
        logger.info("Building Hunyuan service...")
        try:
            run_command(
                ["docker", "compose", "build", "--no-cache", "hunyuan"],
                check=True
            )
            logger.success("✅ Hunyuan build complete")
        except subprocess.CalledProcessError:
            logger.error("❌ Hunyuan build failed")
            return False

        logger.success("✅ Image build complete")
        return True

    finally:
        os.chdir(original_dir)


def start_docker_services(project_dir):
    """Start Docker services"""
    logger.info("[4/4] Starting Docker services...")
    logger.info("")

    # Change to project directory
    original_dir = os.getcwd()
    os.chdir(project_dir)

    try:
        # Stop existing containers
        logger.info("Stopping existing containers...")
        run_command(
            ["docker", "compose", "down"],
            check=False,
            capture_output=True
        )
        logger.info("")

        # Start containers
        logger.info("Starting containers...")
        try:
            run_command(["docker", "compose", "up", "-d"], check=True)
            logger.success("✅ Services started successfully!")
        except subprocess.CalledProcessError:
            logger.error("❌ Docker container startup failed")
            return False

        logger.info("")
        logger.info("Service information:")
        logger.info("   MongoDB:        localhost:27016")
        logger.info("   MinerU API:     http://localhost:8000")
        logger.info("   Hunyuan API:    http://localhost:8001")
        logger.info("")

        # Wait for services to be ready
        logger.info("Waiting for services to be fully ready...")
        max_wait = 120
        waited = 0

        import urllib.request
        import urllib.error
        import socket

        while waited < max_wait:
            try:
                with urllib.request.urlopen(
                    "http://localhost:8001/v1/models",
                    timeout=2
                ) as response:
                    if response.status == 200:
                        logger.success("✅ All services ready")
                        break
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                ConnectionResetError,
                socket.error
            ):
                pass

            time.sleep(2)
            waited += 2
            print(".", end="", flush=True)

        if waited >= max_wait:
            print()
            logger.warning("⚠️  Services starting, please check status later")
            logger.info("   Run: docker compose logs -f")
        else:
            print()  # New line after dots

        return True

    finally:
        os.chdir(original_dir)


# ============================================
# Main setup flow
# ============================================

def main():
    """Main setup function"""
    logger.info("=" * 60)
    logger.info("🐳 LocalScholar-Flow Service Setup Tool")
    logger.info("=" * 60)
    logger.info("")

    # Get script directory
    script_dir = Path(__file__).parent.absolute()
    project_dir = script_dir.parent
    models_dir = project_dir / "models"

    # Check Docker
    if not check_docker():
        sys.exit(1)

    logger.info("")

    # Check models exist
    if not check_models_exist(models_dir):
        sys.exit(1)

    logger.info("")

    # Fix model paths
    if not fix_model_paths(models_dir):
        logger.warning("⚠️  Some model paths could not be fixed")
        logger.warning("   You may need to fix them manually")

    logger.info("")

    # Check and build images
    build_needed = check_docker_images()

    if build_needed:
        if not build_docker_images(project_dir):
            sys.exit(1)
    else:
        logger.success("✅ Skipping image build")

    logger.info("")

    # Start services
    if not start_docker_services(project_dir):
        sys.exit(1)

    logger.info("")
    logger.success("=" * 60)
    logger.success("✅ Setup complete!")
    logger.success("=" * 60)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  Run workflow: python scripts/run_all.py")
    logger.info("")


if __name__ == "__main__":
    main()
