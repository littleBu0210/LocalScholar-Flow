#!/usr/bin/env python3
"""
Markdown Translation Tool
Translation tool based on paragraph segmentation and async models
Fully implemented following ref/translator.py
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from pathlib import Path
import aiohttp
import requests
from database import Database


# ==================== Progress Bar Utility ====================
def print_block_progress(current: int, total: int, failed: int = 0, prefix: str = '  Block Progress'):
    """Print translation block progress (single line update)"""
    percent = current / max(total, 1) * 100
    filled = int(20 * current // max(total, 1))
    bar = '▓' * filled + '░' * (20 - filled)
    fail_info = f' ❌{failed}' if failed > 0 else ''
    sys.stdout.write(f'\r{prefix} |{bar}| {percent:5.1f}% ({current}/{total}){fail_info}')
    sys.stdout.flush()


@dataclass
class TranslationBlock:
    """Translation block: Contains paragraphs that need translation"""
    index: int  # Sequential index in the original text
    paragraphs: List[str]  # List of original paragraphs
    original_text: str  # Merged original text
    formulas: dict = field(default_factory=dict)  # Formula placeholder mapping
    translated_text: str = ""  # Translated text
    success: bool = False  # Whether translation succeeded
    error: str = ""  # Error message


@dataclass
class NonTranslationBlock:
    """Non-translation block: Images, block formulas, and other content that doesn't need translation"""
    index: int  # Sequential index in the original text
    content: str  # Original content (unchanged)


class FormulaHandler:
    """Handle placeholder replacement for inline formulas"""

    # Match inline formulas: $...$ (but not $$...$$)
    INLINE_FORMULA_PATTERN = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)')

    def __init__(self):
        self.formula_map = {}
        self.counter = 0

    def replace_formulas(self, text: str) -> Tuple[str, dict]:
        """Replace inline formulas with placeholders, return processed text and formula mapping"""
        self.formula_map = {}
        self.counter = 0

        def replacer(match):
            formula = match.group(0)  # 包含$符号的完整公式
            placeholder = f"<FORMULA_{self.counter}>"
            self.formula_map[placeholder] = formula
            self.counter += 1
            return placeholder

        processed_text = self.INLINE_FORMULA_PATTERN.sub(replacer, text)
        return processed_text, self.formula_map.copy()

    @staticmethod
    def restore_formulas(text: str, formula_map: dict) -> str:
        """Restore placeholders to original formulas"""
        result = text
        for placeholder, formula in formula_map.items():
            result = result.replace(placeholder, formula)
        return result


class MarkdownParser:
    """Markdown parser: Responsible for splitting and reassembling documents"""

    # Match references section heading
    REFERENCES_PATTERN = re.compile(r'\n#+.*(References?|REFERENCES?).*\n')

    def __init__(self, config: Dict):
        self.config = config['translation']
        self.formula_handler = FormulaHandler()

    def find_references_position(self, content: str) -> int:
        """Find the position of references, return the end position of content before references (if multiple matches, take the last one)"""
        matches = list(self.REFERENCES_PATTERN.finditer(content))
        if matches:
            return matches[-1].start()
        return len(content)

    def split_by_separators(self, content: str) -> List[Tuple[str, bool]]:
        """
        Split content by images and block-level formulas
        Returns: [(text_content, needs_translation), ...]
        """
        parts = []
        last_end = 0

        # Find all images and block-level formulas
        separators = []

        # Find consecutive image blocks
        for match in re.finditer(r'((?:^!\[.*?\]\([^)]+\)\s*\n?)+)', content, re.MULTILINE):
            separators.append((match.start(), match.end(), match.group(0)))

        # Find block-level formulas
        for match in re.finditer(r'(^\$\$[\s\S]*?\$\$\s*$)', content, re.MULTILINE):
            separators.append((match.start(), match.end(), match.group(0)))

        # Sort by position
        separators.sort(key=lambda x: x[0])

        # Merge overlapping or adjacent separators
        merged_separators = []
        for start, end, text in separators:
            if merged_separators and start <= merged_separators[-1][1]:
                prev_start, prev_end, prev_text = merged_separators[-1]
                merged_separators[-1] = (prev_start, max(end, prev_end), content[prev_start:max(end, prev_end)])
            else:
                merged_separators.append((start, end, text))

        # Build split results
        for start, end, sep_text in merged_separators:
            if start > last_end:
                text_before = content[last_end:start]
                if text_before.strip():
                    parts.append((text_before, True))

            parts.append((sep_text, False))
            last_end = end

        # Add text after the last separator
        if last_end < len(content):
            remaining = content[last_end:]
            if remaining.strip():
                parts.append((remaining, True))

        # If no separators found, return entire content
        if not parts:
            parts.append((content, True))

        return parts

    def split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs (separated by blank lines)"""
        paragraphs = re.split(r'\n\n+', text)
        return [p for p in paragraphs if p.strip()]

    def create_translation_blocks(self, paragraphs: List[str]) -> List[TranslationBlock]:
        """
        Combine paragraphs into translation blocks
        Each block contains multiple paragraphs, but total characters don't exceed max_text_length
        """
        max_text_length = self.config.get("max_text_length", 3000)
        max_paragraphs = self.config.get("max_paragraphs_per_request", 10)

        blocks = []
        current_paragraphs = []
        current_length = 0
        block_index = 0

        for para in paragraphs:
            para_length = len(para)

            should_start_new_block = (
                current_length + para_length > max_text_length and current_paragraphs
            ) or (
                len(current_paragraphs) >= max_paragraphs
            )

            if should_start_new_block:
                combined_text = "\n\n".join(current_paragraphs)
                processed_text, formulas = self.formula_handler.replace_formulas(combined_text)
                blocks.append(TranslationBlock(
                    index=block_index,
                    paragraphs=current_paragraphs.copy(),
                    original_text=processed_text,
                    formulas=formulas
                ))
                block_index += 1
                current_paragraphs = []
                current_length = 0

            if para_length > max_text_length:
                if current_paragraphs:
                    combined_text = "\n\n".join(current_paragraphs)
                    processed_text, formulas = self.formula_handler.replace_formulas(combined_text)
                    blocks.append(TranslationBlock(
                        index=block_index,
                        paragraphs=current_paragraphs.copy(),
                        original_text=processed_text,
                        formulas=formulas
                    ))
                    block_index += 1
                    current_paragraphs = []
                    current_length = 0

                processed_text, formulas = self.formula_handler.replace_formulas(para)
                blocks.append(TranslationBlock(
                    index=block_index,
                    paragraphs=[para],
                    original_text=processed_text,
                    formulas=formulas
                ))
                block_index += 1
            else:
                current_paragraphs.append(para)
                current_length += para_length + 2

        if current_paragraphs:
            combined_text = "\n\n".join(current_paragraphs)
            processed_text, formulas = self.formula_handler.replace_formulas(combined_text)
            blocks.append(TranslationBlock(
                index=block_index,
                paragraphs=current_paragraphs,
                original_text=processed_text,
                formulas=formulas
            ))

        return blocks

    def parse(self, content: str) -> Tuple[List, str]:
        """
        Parse Markdown document
        Returns: (block_list, references_and_after_content)
        """
        ref_pos = self.find_references_position(content)
        content_to_translate = content[:ref_pos]
        references_section = content[ref_pos:]

        parts = self.split_by_separators(content_to_translate)

        all_blocks = []
        block_index = 0

        for text, needs_translation in parts:
            if needs_translation:
                paragraphs = self.split_into_paragraphs(text)
                if paragraphs:
                    translation_blocks = self.create_translation_blocks(paragraphs)
                    for block in translation_blocks:
                        block.index = block_index
                        all_blocks.append(block)
                        block_index += 1
            else:
                all_blocks.append(NonTranslationBlock(
                    index=block_index,
                    content=text
                ))
                block_index += 1

        return all_blocks, references_section


class RateLimiter:
    """Rate limiter: Control maximum requests per second"""

    def __init__(self, max_requests_per_second: int):
        self.max_requests = max_requests_per_second
        self.interval = 1.0 / max_requests_per_second
        self.semaphore = asyncio.Semaphore(max_requests_per_second)
        self.last_request_time = 0
        self.lock = asyncio.Lock()

    async def acquire(self):
        """Acquire request permission"""
        async with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time

            if time_since_last < self.interval:
                await asyncio.sleep(self.interval - time_since_last)

            self.last_request_time = time.time()

        await self.semaphore.acquire()

    def release(self):
        """Release request permission"""
        self.semaphore.release()


class Translator:
    """Translator: Responsible for calling local API for translation"""

    def __init__(self, config: Dict):
        self.config = config['translation']
        max_requests = self.config.get("max_requests_per_second", 5)
        self.rate_limiter = RateLimiter(max_requests)

    async def translate_text(self, session: aiohttp.ClientSession, text: str) -> str:
        """Call API to translate text"""
        await self.rate_limiter.acquire()

        try:
            headers = {
                "Content-Type": "application/json",
            }
            api_key = self.config.get("api_key", "")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            # Build prompt
            system_prompt = self.config.get("system_prompt",
                "You are a professional translator. Translate the text accurately while preserving the original formatting and structure. Note: Text containing <FORMULA_N> are placeholders for inline mathematical formulas - keep them exactly as they are without any modification.")

            user_prompt_template = self.config.get("user_prompt",
                "Translate the following segment into {target_language}, without additional explanation.\n{source_text}")

            target_language = self.config.get("target_language", "Chinese")
            user_message = user_prompt_template.format(
                target_language=target_language,
                source_text=text
            )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_message})

            payload = {
                "model": self.config.get("model", "hunyuan"),
                "messages": messages,
                "temperature": self.config.get("temperature", 0.3),
            }

            base_url = self.config.get("base_url", "http://localhost:8001/v1/chat/completions")
            timeout = aiohttp.ClientTimeout(total=self.config.get("request_timeout", 120))

            async with session.post(
                base_url,
                headers=headers,
                json=payload,
                timeout=timeout
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API request failed (status code: {response.status}): {error_text}")

                result = await response.json()
                translated = result["choices"][0]["message"]["content"]
                return translated.strip()

        finally:
            self.rate_limiter.release()

    async def translate_block(
        self,
        session: aiohttp.ClientSession,
        block: TranslationBlock,
        progress_callback = None
    ) -> TranslationBlock:
        """Translate a single translation block"""
        try:
            translated = await self.translate_text(session, block.original_text)
            block.translated_text = FormulaHandler.restore_formulas(translated, block.formulas)
            block.success = True
            if progress_callback:
                progress_callback(True)
        except Exception as e:
            # Translation failed, keep original text
            block.translated_text = FormulaHandler.restore_formulas(block.original_text, block.formulas)
            block.success = False
            block.error = str(e)
            if progress_callback:
                progress_callback(False, str(e))

        return block


class TranslationPipeline:
    """Translation pipeline"""

    def __init__(self, config: Dict):
        self.config = config
        self.parser = MarkdownParser(config)
        self.translator = Translator(config)

    async def process_file(self, md_file: Path, output_file: Path, file_idx: int = 0, file_total: int = 1) -> bool:
        """Process a single file"""
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            blocks, references_section = self.parser.parse(content)

            translation_blocks = [b for b in blocks if isinstance(b, TranslationBlock)]
            total_blocks = len(translation_blocks)
            completed_blocks = 0
            failed_blocks = 0
            last_error = ""

            def on_block_complete(success: bool, error: str = ""):
                nonlocal completed_blocks, failed_blocks, last_error
                completed_blocks += 1
                if not success:
                    failed_blocks += 1
                    last_error = error
                print_block_progress(completed_blocks, total_blocks, failed_blocks)

            # 显示文件名
            display_name = md_file.stem[:40] + "..." if len(md_file.stem) > 43 else md_file.stem
            print(f'🔄 [{file_idx}/{file_total}] {display_name}')

            async with aiohttp.ClientSession() as session:
                tasks = [
                    self.translator.translate_block(session, block, on_block_complete)
                    for block in translation_blocks
                ]
                await asyncio.gather(*tasks)

            # Clear block progress line
            sys.stdout.write(f'\r{" " * 80}\r')

            # Check translation results
            success_blocks = sum(1 for b in translation_blocks if b.success)

            if failed_blocks > 0:
                print(f'   ⚠ Partial failure: {success_blocks}/{total_blocks} blocks successful')
                if last_error:
                    print(f'   Error: {last_error[:60]}...' if len(last_error) > 60 else f'   Error: {last_error}')
            else:
                print(f'   ✅ Complete ({total_blocks} blocks)')

            # Only save results if all blocks succeeded
            if failed_blocks == 0:
                translated_content = self.reassemble_document(blocks, references_section)

                output_file.parent.mkdir(parents=True, exist_ok=True)

                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(translated_content)

                return True
            else:
                # Translation failed, don't output file
                return False

        except Exception as e:
            print(f'   ❌ Failed: {e}')
            return False

    def reassemble_document(self, blocks: List, references_section: str) -> str:
        """Reassemble translated document"""
        sorted_blocks = sorted(blocks, key=lambda b: b.index)

        parts = []
        for block in sorted_blocks:
            if isinstance(block, TranslationBlock):
                parts.append(block.translated_text)
            else:
                parts.append(block.content)

        translated_content = "\n\n".join(parts)

        if references_section:
            translated_content += references_section

        return translated_content


def load_config() -> Dict:
    """Load configuration"""
    # Load unified configuration file
    with open("./json/config.json", 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config


def load_state() -> Dict:
    """Load state from MongoDB"""
    db = Database()
    return db.get_all_states()


def save_state(state: Dict):
    """Save state to MongoDB"""
    db = Database()
    db.update_multiple_states(state)


def get_pending_tasks(state: Dict, config: Dict) -> List[Dict]:
    """Get list of pending translation tasks"""
    tasks = []
    pdf2md_dir = Path(config['paths']['pdf2md_dir'])

    for title, info in state.items():
        # Must have been converted to MD and not yet translated
        if (info.get("pdf2md", False) and
            not info.get("is_translated", False)):
            title_dir = pdf2md_dir / title
            if title_dir.exists():
                md_files = list(title_dir.glob("*.md"))
                if md_files:
                    tasks.append({
                        "title": title,
                        "md_file": md_files[0]
                    })

    return tasks


async def process_task(pipeline: TranslationPipeline, task: Dict, config: Dict, state: Dict,
                       file_idx: int = 0, file_total: int = 1) -> bool:
    """Process a single translation task"""
    title = task["title"]
    md_file = task["md_file"]

    pdf2md_dir = Path(config['paths']['pdf2md_dir'])
    mdTrans_dir = Path(config['paths']['mdTrans_dir'])

    try:
        relative_path = md_file.parent.relative_to(pdf2md_dir)
    except ValueError:
        relative_path = Path(title)

    output_dir = mdTrans_dir / relative_path
    output_file = output_dir / md_file.name

    success = await pipeline.process_file(md_file, output_file, file_idx, file_total)

    if success:
        # Copy images
        images_dir = md_file.parent / "images"
        if images_dir.exists():
            output_images_dir = output_dir / "images"
            if output_images_dir.exists():
                shutil.rmtree(output_images_dir)
            shutil.copytree(images_dir, output_images_dir)

        # Update state
        if title in state:
            state[title]["is_translated"] = True
            save_state(state)

    return success


async def main():
    """Main function"""
    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return

    # Load state
    state = load_state()

    # Get pending translation tasks
    tasks = get_pending_tasks(state, config)
    total_tasks = len(tasks)

    if total_tasks == 0:
        print("✅ No documents to translate")
        return

    # Create translation pipeline
    pipeline = TranslationPipeline(config)

    # Process all tasks
    success_count = 0

    for idx, task in enumerate(tasks, 1):
        success = await process_task(pipeline, task, config, state, idx, total_tasks)
        if success:
            success_count += 1

    print(f"✅ Translation complete: {success_count}/{total_tasks} successful")


if __name__ == "__main__":
    asyncio.run(main())
