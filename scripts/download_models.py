#!/usr/bin/env python3
"""
LocalScholar-Flow Model Download Script (Cross-platform)
Supports downloading required model files from ModelScope or HuggingFace
Replaces: scripts/download.sh + original scripts/download_models.py

Usage:
    python scripts/download_models.py                    # Use ModelScope (default)
    python scripts/download_models.py --source huggingface
    python scripts/download_models.py --source modelscope --models-dir /path/to/models
"""
import os
import sys
import json
import shutil
import argparse
import platform
import subprocess
from pathlib import Path
from loguru import logger

# Try to import download libraries
try:
    from modelscope import snapshot_download as ms_snapshot_download
    MODELSCOPE_AVAILABLE = True
except ImportError:
    MODELSCOPE_AVAILABLE = False
    ms_snapshot_download = None

try:
    from huggingface_hub import snapshot_download as hf_snapshot_download
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    HUGGINGFACE_AVAILABLE = False
    hf_snapshot_download = None


# ============================================
# Cross-platform utilities
# ============================================

def is_windows():
    """Check if running on Windows"""
    return platform.system() == 'Windows'


def activate_conda_env(env_name="LocalScholar-Flow"):
    """
    Activate conda environment (cross-platform)
    Note: This is mainly for the Bash script compatibility.
    When running directly with Python, the environment should already be active.
    """
    if is_windows():
        # On Windows, conda should be in PATH if installed
        # Just verify the environment exists
        try:
            result = subprocess.run(
                ["conda", "env", "list"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                check=True
            )
            if env_name not in result.stdout:
                logger.warning(f"Conda environment '{env_name}' not found")
                return False
        except Exception as e:
            logger.warning(f"Could not verify conda environment: {e}")
            return False
    else:
        # On Unix, check standard conda paths
        conda_paths = [
            Path.home() / "anaconda3" / "etc" / "profile.d" / "conda.sh",
            Path.home() / "miniconda3" / "etc" / "profile.d" / "conda.sh",
        ]
        conda_found = any(p.exists() for p in conda_paths)
        if not conda_found:
            logger.warning("Conda not found in standard paths")
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
# Model Downloader
# ============================================

class ModelDownloader:
    """Model downloader with cross-platform support"""

    # ModelScope model IDs
    MS_MINERU_MODEL = "OpenDataLab/MinerU2.5-2509-1.2B"
    MS_HUNYUAN_MODEL = "Tencent-Hunyuan/HY-MT1.5-1.8B"

    # HuggingFace model IDs
    HF_MINERU_MODEL = "opendatalab/MinerU2.5-2509-1.2B"
    HF_HUNYUAN_MODEL = "tencent/HY-MT1.5-1.8B"

    def __init__(self, models_dir: str = "./models", source: str = "modelscope"):
        """
        Initialize downloader
        :param models_dir: Model save directory
        :param source: Download source, optional "modelscope" or "huggingface"
        """
        self.models_dir = Path(models_dir).absolute()
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.source = source.lower()

        if self.source not in ["modelscope", "huggingface"]:
            raise ValueError(
                f"Unsupported download source: {source}, "
                "please use 'modelscope' or 'huggingface'"
            )

        logger.info(f"Models will be saved to: {self.models_dir}")
        logger.info(f"Download source: {self.source}")

        # Check if required libraries are installed
        self._check_dependencies()

    def _check_dependencies(self):
        """Check dependencies required by download source"""
        if self.source == "modelscope":
            if not MODELSCOPE_AVAILABLE:
                logger.error(
                    "Using ModelScope requires modelscope library to be installed first"
                )
                logger.error("Please run: pip install modelscope")
                sys.exit(1)
        elif self.source == "huggingface":
            if not HUGGINGFACE_AVAILABLE:
                logger.error(
                    "Using HuggingFace requires huggingface_hub library to be installed first"
                )
                logger.error("Please run: pip install huggingface_hub")
                sys.exit(1)

    def _snapshot_download(self, model_id: str, cache_dir: str, **kwargs):
        """
        Unified download interface, calls corresponding download function based on selected source
        """
        if self.source == "modelscope":
            return ms_snapshot_download(model_id, cache_dir=cache_dir, **kwargs)
        else:  # huggingface
            return hf_snapshot_download(repo_id=model_id, cache_dir=cache_dir, **kwargs)

    def _get_model_paths(self):
        """Get model paths corresponding to current download source"""
        if self.source == "modelscope":
            mineru_subpath = Path("OpenDataLab") / "MinerU2.5-2509-1.2B"
            hunyuan_subpath = Path("Tencent-Hunyuan") / "HY-MT1___5-1___8B"
        else:  # huggingface
            mineru_subpath = Path("models") / self.HF_MINERU_MODEL.replace("/", "--")
            hunyuan_subpath = Path("models") / self.HF_HUNYUAN_MODEL.replace("/", "--")

        return mineru_subpath, hunyuan_subpath

    def download_mineru_vlm(self):
        """
        Download MinerU VLM model
        ModelScope: OpenDataLab/MinerU2.5-2509-1.2B
        HuggingFace: opendatalab/MinerU2.5-2509-1.2B
        """
        if self.source == "modelscope":
            model_id = self.MS_MINERU_MODEL
        else:
            model_id = self.HF_MINERU_MODEL

        cache_dir = self.models_dir / "MinerU-VLM"
        mineru_subpath, _ = self._get_model_paths()
        vlm_model_path = cache_dir / mineru_subpath

        # Check if model already exists
        if vlm_model_path.exists() and any(vlm_model_path.iterdir()):
            logger.info(f"MinerU VLM model already exists: {vlm_model_path}")
            logger.info("Skipping download")
            return str(vlm_model_path)

        logger.info(f"Starting to download MinerU VLM model from {self.source}...")
        logger.info(f"Model ID: {model_id}")

        try:
            if self.source == "modelscope":
                model_path = self._snapshot_download(
                    model_id,
                    cache_dir=str(cache_dir),
                    revision="master"
                )
            else:  # huggingface
                model_path = self._snapshot_download(
                    model_id,
                    cache_dir=str(cache_dir),
                    resume_download=True
                )

            logger.success(f"MinerU VLM model download complete: {model_path}")
            return model_path
        except Exception as e:
            logger.error(f"Failed to download MinerU VLM model: {e}")
            raise

    def download_hunyuan_model(self):
        """
        Download Tencent Hunyuan model
        ModelScope: Tencent-Hunyuan/HY-MT1.5-1.8B
        HuggingFace: tencent/HY-MT1.5-1.8B
        """
        if self.source == "modelscope":
            model_id = self.MS_HUNYUAN_MODEL
        else:
            model_id = self.HF_HUNYUAN_MODEL

        cache_dir = self.models_dir / "HY-MT1.5-1.8B"
        _, hunyuan_subpath = self._get_model_paths()
        hunyuan_model_path = cache_dir / hunyuan_subpath

        # Check if model already exists
        if hunyuan_model_path.exists() and any(hunyuan_model_path.iterdir()):
            logger.info(f"Tencent Hunyuan model already exists: {hunyuan_model_path}")
            logger.info("Skipping download")
            return str(hunyuan_model_path)

        logger.info(f"Starting to download Tencent Hunyuan model from {self.source}...")
        logger.info(f"Model ID: {model_id}")

        try:
            if self.source == "modelscope":
                model_path = self._snapshot_download(
                    model_id,
                    cache_dir=str(cache_dir),
                    revision="master"
                )
            else:  # huggingface
                model_path = self._snapshot_download(
                    model_id,
                    cache_dir=str(cache_dir),
                    resume_download=True
                )

            logger.success(f"Tencent Hunyuan model download complete: {model_path}")
            return model_path
        except Exception as e:
            logger.error(f"Failed to download Tencent Hunyuan model: {e}")
            raise

    def fix_hunyuan_path(self):
        """
        Fix Hunyuan model path - create 'current' symlink
        Handles both ModelScope and HuggingFace formats
        """
        logger.info("[1/2] Checking Hunyuan model...")

        models_dir = self.models_dir / "HY-MT1.5-1.8B"
        target_dir = models_dir / "current"
        source_dir = None
        rel_source_dir = None

        # Check ModelScope format
        ms_path = models_dir / "Tencent-Hunyuan" / "HY-MT1___5-1___8B"
        if ms_path.exists() and ms_path.is_dir():
            source_dir = ms_path
            rel_source_dir = Path("Tencent-Hunyuan") / "HY-MT1___5-1___8B"
            logger.info("  ✅ Found ModelScope format model")

        # Check HuggingFace format
        if source_dir is None:
            hf_patterns = list(models_dir.glob("models--tencent--HY-MT1.5-1.8B/snapshots/*"))
            if hf_patterns:
                source_dir = hf_patterns[0]
                # Calculate relative path
                rel_source_dir = source_dir.relative_to(models_dir)
                logger.info("  ✅ Found HuggingFace format model")

        if source_dir is None:
            logger.error("  ❌ No valid Hunyuan model found")
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
            logger.success(f"  ✅ Created symlink: current -> {rel_source_dir}")
        else:
            logger.error("  ❌ Failed to create symlink")
            return False

        return True

    def fix_mineru_path(self):
        """
        Fix MinerU model path - generate mineru.json config
        Handles both ModelScope and HuggingFace formats
        """
        logger.info("[2/2] Checking MinerU model...")

        vlm_path = None
        mineru_base = self.models_dir / "MinerU-VLM"

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
            logger.error("  ❌ No valid MinerU model found")
            logger.error(f"     Please check {mineru_base} directory")
            return False

        # Calculate relative path
        try:
            rel_path = vlm_path.relative_to(self.models_dir)
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
        config_file = self.models_dir / "mineru.json"
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.success(f"  ✅ Updated configuration file: mineru.json")
            logger.info(f"     VLM path: {container_vlm_path}")
            return True
        except Exception as e:
            logger.error(f"  ❌ Failed to write configuration file: {e}")
            return False

    def fix_model_paths(self):
        """
        Fix model paths for cross-platform compatibility
        """
        logger.info("=" * 60)
        logger.info("  Model Path Compatibility Fix Tool")
        logger.info("=" * 60)
        logger.info(f"Model directory: {self.models_dir}")
        logger.info("")

        success = True

        # Fix Hunyuan path
        if not self.fix_hunyuan_path():
            success = False

        # Fix MinerU path
        if not self.fix_mineru_path():
            success = False

        if success:
            logger.success("=" * 60)
            logger.success("  ✅ Model path fix complete!")
            logger.success("=" * 60)
            logger.info("")
            logger.info("Unified path description:")
            logger.info("  Hunyuan model: ./models/HY-MT1.5-1.8B/current")
            logger.info("  MinerU config:  ./models/mineru.json")
            logger.info("")

        return success

    def download_all(self):
        """
        Download all models (MinerU VLM + Hunyuan) and fix paths
        """
        logger.info("=" * 60)
        logger.info("  Paper Flow - Model Download Tool")
        logger.info("=" * 60)
        logger.info("")
        logger.info(f"📦 Download source: {self.source}")
        logger.info("")
        logger.info("📦 Starting model download...")
        logger.info("")

        try:
            # Download MinerU VLM model
            self.download_mineru_vlm()
            logger.info("")

            # Download Hunyuan model
            self.download_hunyuan_model()
            logger.info("")

            logger.success("✅ Model download complete!")
            logger.info("")
            logger.info("Model file locations:")
            logger.info("  - MinerU model: ./models/MinerU-VLM/")
            logger.info("  - Hunyuan model: ./models/HY-MT1.5-1.8B/")
            logger.info("")

            # Fix model paths
            self.fix_model_paths()

            logger.info("=" * 60)
            logger.info("  📦 Next Steps")
            logger.info("=" * 60)
            logger.info("")
            logger.info(
                "For first-time use, you need to build and start Docker services:"
            )
            logger.info("  python scripts/setup_services.py")
            logger.info("")

        except Exception as e:
            logger.error(f"Error occurred during download: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="LocalScholar-Flow Model Download Script - "
                    "Download MinerU VLM and Tencent Hunyuan models (Cross-platform)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all models from ModelScope (default)
  python scripts/download_models.py

  # Download all models from HuggingFace
  python scripts/download_models.py --source huggingface

  # Specify model save directory
  python scripts/download_models.py --models-dir /path/to/models

  # Download from HuggingFace and specify save directory
  python scripts/download_models.py --source huggingface --models-dir /path/to/models

Cross-platform support:
  - Windows: python scripts\\download_models.py
  - Linux/macOS: python scripts/download_models.py
        """
    )

    parser.add_argument(
        "--source",
        choices=["modelscope", "huggingface"],
        default="modelscope",
        help="Model download source (default: modelscope)"
    )

    parser.add_argument(
        "--models-dir",
        default="./models",
        help="Model save directory (default: ./models)"
    )

    args = parser.parse_args()

    downloader = ModelDownloader(args.models_dir, args.source)
    downloader.download_all()


if __name__ == "__main__":
    main()
