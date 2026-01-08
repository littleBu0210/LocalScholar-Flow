import json
import os
import shutil
import zipfile
import requests
from pathlib import Path
from database import Database

def load_config():
    with open('./json/config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def process_pdf(pdf_name, pdf_path, db, config):
    api_url = config['miner_u']['api_url']
    paths = config['paths']

    # 1. Create local temporary workspace (for extracting API returned zip)
    work_base = Path(__file__).parent.parent / "workspace"
    work_base.mkdir(parents=True, exist_ok=True)

    zip_path = work_base / f"{pdf_name}.zip"
    extract_root = work_base / f"{pdf_name}_extract"

    try:
        # Step 1: Call API to download conversion results
        for attempt in range(3):
            try:
                with open(pdf_path, 'rb') as f:
                    files = [
                        ('files', (os.path.basename(pdf_path), f, 'application/pdf')),
                        ('backend', (None, 'vlm-vllm-async-engine')),
                        ('output_dir', (None, '/tmp/output')),
                        ('return_content_list', (None, 'false')),
                        ('return_images', (None, 'true')),
                        ('response_format_zip', (None, 'true')),
                    ]
                    response = requests.post(api_url, files=files, headers={'accept': 'application/json'}, timeout=120)
                    if response.status_code == 200: break
            except:
                if attempt == 2: return False
                continue

        # Check if response is valid zip (zip files start with PK)
        if not response.content.startswith(b'PK'):
            # Try to parse error message
            try:
                err_msg = response.json().get('detail', response.text[:1000])
            except:
                err_msg = response.text[:1000] if len(response.content) < 500 else "Response too large"
            print(f"   ⚠ API error: {err_msg}")
            return False

        with open(zip_path, 'wb') as f:
            f.write(response.content)

        # Step 2: Extract ZIP
        if extract_root.exists(): shutil.rmtree(extract_root)
        extract_root.mkdir()

        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_root)

        content_dir = None
        for item in extract_root.iterdir():
            if item.is_dir():
                content_dir = item
                break

        if not content_dir: return False

        # Step 3: Determine target path and move files
        target_parent = Path(paths['pdf2md_dir'])
        final_target_dir = target_parent / pdf_name

        # Step 4: Move files
        if final_target_dir.exists():
            shutil.rmtree(final_target_dir)

        shutil.copytree(content_dir, final_target_dir)

        # Update state to MongoDB
        state_data = {
            "pdf2md": True,
            "is_translated": False
        }

        # Delete old translation files (ensure version sync)
        trans_path = Path(paths['mdTrans_dir']) / pdf_name
        if trans_path.exists():
            print(f"   🗑️ Deleting old translation files to ensure version sync")
            shutil.rmtree(trans_path)
        # is_translated is always False, needs re-translation

        db.update_paper_state(pdf_name, state_data)

        return True

    except Exception as e:
        print(f"   ❌ Exception: {str(e)[:50]}")
        return False

    finally:
        # Clean up temporary files
        if zip_path.exists(): os.remove(zip_path)
        if extract_root.exists(): shutil.rmtree(extract_root)

def main():
    config = load_config()

    pdf_dir = Path(config['paths']['pdf_dir'])

    if not pdf_dir.exists():
        print(f"❌ PDF directory does not exist: {pdf_dir}")
        return

    # Initialize database
    db = Database()

    # Get all states
    state_data = db.get_all_states()

    todos = [k for k, v in state_data.items() if not v.get("pdf2md", False)]
    total = len(todos)

    if total == 0:
        print("✅ No PDFs to convert")
        return

    success_count = 0
    for idx, pdf_name in enumerate(todos):
        pdf_path = pdf_dir / f"{pdf_name}.pdf"

        display_name = pdf_name[:40] + "..." if len(pdf_name) > 43 else pdf_name

        if not pdf_path.exists():
            print(f"⚠ [{idx+1}/{total}] Not found: {display_name}")
            continue

        print(f"🔄 [{idx+1}/{total}] {display_name}")

        if process_pdf(pdf_name, pdf_path, db, config):
            success_count += 1

    print(f"✅ Complete: {success_count}/{total} successful")

if __name__ == "__main__":
    main()
