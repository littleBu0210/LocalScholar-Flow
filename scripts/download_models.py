#!/usr/bin/env python3
"""
LocalScholar-Flow Model Download Script
Supports downloading required model files from ModelScope or HuggingFace
"""
import os
import sys
import json
import argparse
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


class ModelDownloader:
    """Model downloader"""

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
            raise ValueError(f"Unsupported download source: {source}, please use 'modelscope' or 'huggingface'")

        logger.info(f"Models will be saved to: {self.models_dir}")
        logger.info(f"Download source: {self.source}")

        # Check if required libraries are installed
        self._check_dependencies()

    def _check_dependencies(self):
        """Check dependencies required by download source"""
        if self.source == "modelscope":
            if not MODELSCOPE_AVAILABLE:
                logger.error("Using ModelScope requires modelscope library to be installed first")
                logger.error("Please run: pip install modelscope")
                sys.exit(1)
        elif self.source == "huggingface":
            if not HUGGINGFACE_AVAILABLE:
                logger.error("Using HuggingFace requires huggingface_hub library to be installed first")
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
    def create_mineru_config(self, container_root="/data/models"):
        """
        Generate Docker-compatible mineru.json
        (Fixed version: automatically filters out temporary directories like ._____temp)
        """
        logger.info("Generating Docker-compatible MinerU configuration file...")

        # ---------------------------------------------------------
        # 1. Locate VLM model path on host machine
        # ---------------------------------------------------------
        # Search for all matching paths
        all_matches = list(self.models_dir.glob("MinerU-VLM/**/MinerU2.5-2509-1.2B"))

        # [Key fix] Filter out paths with temporary file characteristics (like ._____temp, .cache)
        valid_matches = [
            p for p in all_matches
            if ".____" not in str(p) and "/." not in str(p).replace("\\", "/")
        ]

        if not valid_matches:
            # Try searching for HuggingFace format paths
            all_matches = list(self.models_dir.glob("MinerU-VLM/**/*--MinerU2.5-2509-1.2B"))
            valid_matches = [
                p for p in all_matches
                if ".____" not in str(p) and "/." not in str(p).replace("\\", "/")
            ]

        if not valid_matches:
            logger.error(f"No valid VLM model found under {self.models_dir}!")
            logger.warning(f"Found but filtered paths: {all_matches}")
            logger.error("Please check if the model download is complete. It's recommended to delete models/MinerU-VLM folder and re-download.")
            return

        # Take the first non-temporary valid path
        host_vlm_path = valid_matches[0]
        logger.success(f"Located valid model path: {host_vlm_path}")

        # ---------------------------------------------------------
        # 2. Convert path: host path -> container absolute path
        # ---------------------------------------------------------
        try:
            rel_path = host_vlm_path.relative_to(self.models_dir)
        except ValueError:
            logger.error("Model files are not under the specified models directory, cannot generate configuration")
            return

        # Concatenate container path
        container_vlm_full_path = (Path(container_root) / rel_path).as_posix()

        # ---------------------------------------------------------
        # 3. Build JSON content
        # ---------------------------------------------------------
        config = {
            "config_version": "1.3.1",
            "models-dir": {
                "vlm": container_vlm_full_path
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

        # ---------------------------------------------------------
        # 4. Save file
        # ---------------------------------------------------------
        config_file_path = self.models_dir / "mineru.json"

        try:
            with open(config_file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            logger.success(f"Configuration file fixed and regenerated: {config_file_path}")
            logger.info(f"Container model path will point to: {container_vlm_full_path}")
        except Exception as e:
            logger.error(f"Failed to write configuration file: {e}")

    def download_all(self):
        """
        Download all models (MinerU VLM + Hunyuan)
        """
        logger.info("=" * 60)
        logger.info("LocalScholar-Flow Model Download")
        logger.info(f"Download source: {self.source}")
        logger.info("=" * 60)

        try:
            # Download MinerU VLM model
            self.download_mineru_vlm()
            print()

            # Download Hunyuan model
            self.download_hunyuan_model()
            print()

            # Create configuration file
            self.create_mineru_config(container_root="/data/models")

            logger.success("=" * 60)
            logger.success("All models downloaded!")
            logger.success("=" * 60)
            logger.info(f"Models saved in: {self.models_dir}")
            logger.info("Configuration file: mineru.json")
            logger.info("\nDocker usage instructions:")
            logger.info("1. MinerU container will automatically load configuration from mineru.json")
            logger.info("2. Hunyuan container needs to mount models directory: -v ./models:/models")
            logger.info("3. Hunyuan model path: /models/HY-MT1.5-1.8B")

        except Exception as e:
            logger.error(f"Error occurred during download: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="LocalScholar-Flow Model Download Script - Download MinerU VLM and Tencent Hunyuan models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all models from ModelScope (default)
  python download_models.py
  bash download.sh

  # Download all models from HuggingFace
  python download_models.py --source huggingface
  bash download.sh huggingface

  # Specify model save directory
  python download_models.py --models-dir /path/to/models

  # Download from HuggingFace and specify save directory
  python download_models.py --source huggingface --models-dir /path/to/models
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
