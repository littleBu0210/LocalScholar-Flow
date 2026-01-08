import os
import json
from pathlib import Path
from database import Database

def load_config():
    with open('./json/config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_pdf_base_name(pdf_filename):
    return os.path.splitext(pdf_filename)[0]

def check_folder_exists(base_path, target_name):
    """
    Check if a folder exists.
    Rule: Case-insensitive matching
    """
    directory = Path(base_path)
    if not directory.exists():
        return False

    # Convert target filename to lowercase
    target_clean = target_name.strip().lower()

    try:
        # Iterate through all subdirectories in the directory
        for item in directory.iterdir():
            if item.is_dir() and item.name.strip().lower() == target_clean:
                return True
    except OSError:
        pass

    return False

def generate_state_json():
    paths = load_config()['paths']

    pdf_folder = Path(paths['pdf_dir'])
    pdf2md_folder = Path(paths['pdf2md_dir'])
    mdTrans_folder = Path(paths['mdTrans_dir'])

    # Ensure PDF directory exists
    if not pdf_folder.exists():
        print(f"❌ PDF directory does not exist: {pdf_folder}")
        return

    # Get all PDF files
    pdf_files = [f for f in os.listdir(pdf_folder) if f.endswith('.pdf')]

    # Initialize database
    db = Database()

    # Clear existing states (optional: comment out this line if you don't want to clear)
    # db.clear_all_states()

    stats = {"pdf2md": 0, "translated": 0}

    for pdf_file in pdf_files:
        base_name = get_pdf_base_name(pdf_file)

        # Check pdf2md directory
        pdf2md = check_folder_exists(pdf2md_folder, base_name)

        # Check mdTrans directory
        is_translated = check_folder_exists(mdTrans_folder, base_name)

        if pdf2md: stats["pdf2md"] += 1
        if is_translated: stats["translated"] += 1

        # Update to MongoDB
        state_data = {
            "pdf2md": pdf2md,
            "is_translated": is_translated
        }
        db.update_paper_state(base_name, state_data)

    pending_convert = len(pdf_files) - stats["pdf2md"]
    print(f"✅ Total {len(pdf_files)} papers | {pending_convert} pending conversion")

    # Print database statistics
    db_stats = db.get_stats()
    print(f"📊 Database stats: {db_stats['pdf2md']} converted | {db_stats['translated']} translated")

if __name__ == '__main__':
    generate_state_json()
