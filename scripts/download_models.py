#!/usr/bin/env python3
"""
LocalScholar-Flow Model Download Script
Purpose: Download models from ModelScope or HuggingFace and organize them into a standard
         directory structure ready for Docker mounting.
Features: No symlinks used, direct file movement, fully compatible with Windows/Linux.
"""
import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from loguru import logger

# Try importing download libraries
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


class ModelDownloader:
    # Define model IDs
    MS_MINERU = "OpenDataLab/MinerU2.5-2509-1.2B"
    HF_MINERU = "opendatalab/MinerU2.5-2509-1.2B"

    MS_HUNYUAN = "Tencent-Hunyuan/HY-MT1.5-1.8B"
    HF_HUNYUAN = "tencent/HY-MT1.5-1.8B"

    # Define standardized local directory names (Docker will mount these directly)
    DIR_MINERU = "MinerU-VLM"
    DIR_HUNYUAN = "HY-MT1.5-1.8B"

    def __init__(self, base_dir="./models", source="modelscope"):
        self.base_dir = Path(base_dir).resolve()
        self.source = source
        self.temp_dir = self.base_dir / "temp_download_cache"
        
        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self._check_dependencies()

    def _check_dependencies(self):
        if self.source == "modelscope" and not MODELSCOPE_AVAILABLE:
            logger.error("Please install modelscope: pip install modelscope")
            sys.exit(1)
        if self.source == "huggingface" and not HUGGINGFACE_AVAILABLE:
            logger.error("Please install huggingface_hub: pip install huggingface_hub")
            sys.exit(1)

    def _find_actual_model_dir(self, search_path: Path):
        """
        Recursively find directory containing config.json in download cache
        """
        for path in search_path.rglob("config.json"):
            # Exclude some hidden directories or temporary files that may exist
            if ".cache" not in str(path) and "blobs" not in str(path):
                return path.parent
        return None

    def _move_and_organize(self, source_path: Path, target_name: str):
        """
        Move downloaded model files to final standard directory
        """
        final_path = self.base_dir / target_name

        # If target exists and is not empty, ask whether to skip
        if final_path.exists():
            if any(final_path.iterdir()):
                logger.warning(f"Target directory already exists and is not empty: {final_path}")
                logger.info("Skipping move operation (assuming model is ready)")
                return
            else:
                # It's an empty folder, delete it to allow move
                shutil.rmtree(final_path)

        logger.info(f"Moving model to standard location: {final_path}")
        try:
            # shutil.move behaves differently across drives or specific systems,
            # ensure it's a move operation here
            shutil.move(str(source_path), str(final_path))
            logger.success(f"✅ Model ready: {final_path}")
        except Exception as e:
            logger.error(f"Failed to move files: {e}")
            # Try copying as fallback
            try:
                shutil.copytree(source_path, final_path)
                logger.success(f"✅ Model copied to place: {final_path}")
            except Exception as e2:
                logger.error(f"Copy also failed: {e2}")
                sys.exit(1)

    def download_model(self, model_key, target_dir_name):
        """Common download logic"""
        final_target = self.base_dir / target_dir_name
        if final_target.exists() and any(final_target.iterdir()):
            logger.info(f"✅ Model {target_dir_name} already exists, skipping download.")
            return

        logger.info(f"⬇️ Starting download {target_dir_name} (source: {self.source})...")

        # Use independent temporary directory to avoid confusion
        current_temp = self.temp_dir / target_dir_name
        if current_temp.exists():
            shutil.rmtree(current_temp)

        model_id = ""
        try:
            download_path = ""
            if self.source == "modelscope":
                model_id = self.MS_MINERU if target_dir_name == self.DIR_MINERU else self.MS_HUNYUAN
                # ModelScope download
                download_path = ms_snapshot_download(
                    model_id,
                    cache_dir=str(current_temp),
                    revision='master'
                )
            else:
                model_id = self.HF_MINERU if target_dir_name == self.DIR_MINERU else self.HF_HUNYUAN
                # HuggingFace download
                download_path = hf_snapshot_download(
                    repo_id=model_id,
                    cache_dir=str(current_temp),
                    local_dir_use_symlinks=False, # Key: HF don't use symlinks, download files directly
                    resume_download=True
                )

            # Find the actual model folder (handle nested directory structure)
            actual_path = self._find_actual_model_dir(Path(current_temp))

            if not actual_path:
                # If config.json is not found, the download path itself may be the root directory
                # (depending on library version)
                if (Path(download_path) / "config.json").exists():
                    actual_path = Path(download_path)
                else:
                    logger.error("❌ Download completed but config.json not found in directory")
                    return

            # Move to final location
            self._move_and_organize(actual_path, target_dir_name)

        except Exception as e:
            logger.error(f"❌ Download or processing failed: {e}")
            sys.exit(1)
        finally:
            # Clean up temporary download directory
            if self.temp_dir.exists():
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except:
                    pass

    def generate_mineru_config(self):
        """Generate mineru.json"""
        logger.info("⚙️ Generating MinerU configuration file...")

        # The path here is inside the Docker container, it's fixed
        container_model_path = f"/data/models/{self.DIR_MINERU}"

        config = {
            "config_version": "1.3.1",
            "models-dir": {
                "vlm": container_model_path
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

        config_path = self.base_dir / "mineru.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        logger.success(f"✅ Configuration file generated: {config_path}")

    def run(self):
        logger.info(f"📂 Model save directory: {self.base_dir}")

        # 1. Download MinerU
        self.download_model("mineru", self.DIR_MINERU)

        # 2. Download Hunyuan
        self.download_model("hunyuan", self.DIR_HUNYUAN)

        # 3. Generate configuration
        self.generate_mineru_config()

        logger.info("="*50)
        logger.success("🎉 All models ready!")
        logger.info("You can now start services with 'docker compose up'.")

def main():
    parser = argparse.ArgumentParser(description="LocalScholar-Flow Model Download Tool")
    parser.add_argument("--source", choices=["modelscope", "huggingface"], default="modelscope", help="Download source")
    parser.add_argument("--models-dir", default="./models", help="Model save path")
    
    args = parser.parse_args()
    
    downloader = ModelDownloader(args.models_dir, args.source)
    downloader.run()

if __name__ == "__main__":
    main()