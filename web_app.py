#!/usr/bin/env python3
"""A reader-focused local UI for PDF extraction and translation."""

import base64
import html
import json
import re
import subprocess
import threading
import time
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "pdfs"
OUTPUT_DIR = ROOT / "output"
WORKSPACE = ROOT / "workspace"
TASK_PID_FILE = WORKSPACE / "web_workflow.pid"


@st.cache_resource
def task_state():
    return {"running": False, "exit_code": None, "started": None, "lock": threading.Lock()}


TASK = task_state()


def run_workflow():
    with TASK["lock"]:
        TASK.update(running=True, exit_code=None, started=time.time())
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    code = 1
    try:
        with (WORKSPACE / "web_workflow.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/run_all.py")],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            )
            TASK_PID_FILE.write_text(str(process.pid), encoding="ascii")
            code = process.wait()
    finally:
        TASK_PID_FILE.unlink(missing_ok=True)
        with TASK["lock"]:
            TASK.update(running=False, exit_code=code)


def start_workflow():
    with TASK["lock"]:
        if TASK["running"]:
            return False
        TASK["running"] = True
    threading.Thread(target=run_workflow, daemon=True).start()
    return True


def compose_services():
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"], cwd=ROOT,
        capture_output=True, text=True,
    )
    services = set()
    for line in result.stdout.splitlines():
        try:
            item = json.loads(line)
            if item.get("State") == "running":
                services.add(item.get("Service"))
        except json.JSONDecodeError:
            pass
    return services


def latest_percentage(text, patterns):
    """Return the most recent percentage emitted by a worker."""
    values = []
    for pattern in patterns:
        values.extend(float(value) for value in re.findall(pattern, text))
    return int(max(0, min(values[-1], 100))) if values else 0


def current_stage():
    services = compose_services()
    elapsed = int(time.time() - TASK["started"]) if TASK["started"] else 0
    if "mineru" in services:
        logs = subprocess.run(
            ["docker", "compose", "logs", "--no-color", "--tail", "300", "mineru"],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout
        percent = latest_percentage(logs, [r"Two Step Extraction:\s*(\d+)%"])
        return f"MinerU 提取中 {percent}%", percent / 100, elapsed
    if "hunyuan" in services:
        log_path = WORKSPACE / "web_workflow.log"
        logs = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        percent = latest_percentage(
            logs,
            [r"Block Progress[^\r\n]*?([0-9]+(?:\.[0-9]+)?)%"],
        )
        return f"翻译中 {percent}%", percent / 100, elapsed
    return "正在准备 0%", 0.0, elapsed


def papers():
    names = set()
    for base in (OUTPUT_DIR / "mdTrans", OUTPUT_DIR / "pdf2md"):
        if base.exists():
            names.update(p.name for p in base.iterdir() if p.is_dir())
    return sorted(names)


def find_markdown(base, name):
    folder = base / name
    if not folder.exists():
        return None
    preferred = folder / f"{name.replace(' ', '_')}.md"
    if preferred.exists():
        return preferred
    return next(folder.glob("*.md"), None)


def inject_images(markdown, images_dir):
    if not images_dir.exists():
        return markdown

    def replace(match):
        relative = match.group(2)
        image_path = images_dir / Path(relative).name
        if not image_path.exists():
            return match.group(0)
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"![{match.group(1)}](data:{mime};base64,{encoded})"

    return re.sub(r"!\[(.*?)\]\((.*?)\)", replace, markdown)


def pdf_viewer(pdf_path):
    st.pdf(pdf_path, height=1080)


st.set_page_config(page_title="LocalScholar Reader", page_icon="◐", layout="wide")
st.markdown("""
<style>
:root { --ink:#18322b; --paper:#fbfaf6; --sage:#719187; --line:#deddd5; }
.stApp { background:var(--paper); color:var(--ink); }
.block-container { max-width:none; width:100%; padding:1.8rem 2rem 4rem; }
h1,h2,h3 { font-family:"Noto Serif CJK SC","Source Han Serif SC",serif !important; color:var(--ink) !important; }
p,button,label,[data-testid="stWidgetLabel"] { font-family:Inter,"Noto Sans CJK SC","Microsoft YaHei",sans-serif; }
.hero { padding:1.1rem 0 1.8rem; border-bottom:1px solid var(--line); margin-bottom:2rem; }
.eyebrow { color:#718078; letter-spacing:.16em; font-size:.72rem; font-weight:600; text-transform:uppercase; }
.hero h1 { font-size:2.55rem; line-height:1.15; margin:.55rem 0 .55rem; }
.hero p { color:#64736d; max-width:680px; font-size:1.02rem; }
.upload-title { font-family:"Noto Serif CJK SC","Source Han Serif SC",serif;font-size:1.16rem;font-weight:600;color:var(--ink);margin:.1rem 0 .15rem; }
.upload-note { color:#7b8782;font-size:.86rem;margin-bottom:.9rem; }
.reading-head { border-bottom:1px solid var(--line);padding-bottom:.7rem;margin-top:1.5rem; }
[data-testid="stFileUploader"] { background:#f5f3ec;border:1px dashed #aebbb4;border-radius:16px;padding:.5rem; }
[data-testid="stFileUploaderDropzone"] { min-height:118px;padding:1rem 1.25rem; }
[data-testid="stFileUploaderDropzone"] > div { gap:.35rem; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--line) !important;border-radius:15px !important;background:#fffefa; }
.stButton > button[kind="primary"] { background:var(--ink);border-color:var(--ink);border-radius:10px; }
[data-testid="stMarkdownContainer"] img { border-radius:8px;box-shadow:0 5px 24px #263b3214; }
.status-card { background:#edf3ef;border:1px solid #cad9d1;border-radius:14px;padding:1rem 1.2rem;margin:.8rem 0; }
.status-card strong { color:#244b40; }.status-card small { color:#728078; }
#MainMenu, footer, header { visibility:hidden; }
@media (max-width: 900px) {
  .block-container { padding:1.25rem 1rem 3rem; }
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<section class="hero">
  <div class="eyebrow">LOCAL · PRIVATE · GPU POWERED</div>
  <h1>论文阅读与翻译</h1>
  <p>在本地提取并翻译 PDF，随时对照原文阅读。</p>
</section>
""", unsafe_allow_html=True)

with st.container(border=True):
    st.markdown('<div class="upload-title">上传论文</div><div class="upload-note">支持同时选择多篇 PDF</div>', unsafe_allow_html=True)
    uploads = st.file_uploader(
        "选择 PDF", type=["pdf"], accept_multiple_files=True,
        label_visibility="collapsed",
    )
    action, spacer = st.columns([1, 4])
    with action:
        start = st.button("开始提取与翻译", type="primary", width="stretch", disabled=TASK["running"])

    if start:
        if not uploads:
            st.warning("请先选择至少一篇 PDF。")
        else:
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            for upload in uploads:
                (PDF_DIR / Path(upload.name).name).write_bytes(upload.getbuffer())
            start_workflow()
            st.rerun()

if TASK["running"]:
    stage, progress, elapsed = current_stage()
    st.markdown(
        f'<div class="status-card"><strong>{html.escape(stage)}</strong><br>'
        f'<small>已用时 {elapsed // 60} 分 {elapsed % 60:02d} 秒 · 全部计算均在本机完成</small></div>',
        unsafe_allow_html=True,
    )
    st.progress(progress)
    time.sleep(4)
    st.rerun()
elif TASK["exit_code"] == 0:
    st.success("论文已经处理完成，可以开始阅读。")
elif TASK["exit_code"] is not None:
    st.error("处理未能完成。请重新启动页面后再试；若问题持续，请检查本地模型服务。")

available = papers()
if not available:
    st.markdown("### 阅读区")
    st.caption("处理完成的论文会出现在这里。")
    st.stop()

st.markdown('<div class="reading-head"><div class="eyebrow">READING DESK</div><h2>论文对照阅读</h2></div>', unsafe_allow_html=True)
toolbar_left, toolbar_right = st.columns([3, 2], vertical_alignment="bottom")
with toolbar_left:
    selected = st.selectbox("选择论文", available, label_visibility="collapsed")
with toolbar_right:
    view = st.segmented_control("阅读内容", ["译文", "提取原文"], default="译文", label_visibility="collapsed")

source_md = find_markdown(OUTPUT_DIR / "pdf2md", selected)
translated_md = find_markdown(OUTPUT_DIR / "mdTrans", selected)
chosen_md = translated_md if view == "译文" and translated_md else source_md
pdf_path = PDF_DIR / f"{selected}.pdf"
images_dir = (chosen_md.parent / "images") if chosen_md else Path()

text_col, pdf_col = st.columns([9, 11], gap="large")
with text_col:
    st.caption("译文" if view == "译文" and translated_md else "提取原文")
    with st.container(height=1080, border=True):
        if chosen_md:
            content = chosen_md.read_text(encoding="utf-8", errors="replace")
            st.markdown(inject_images(content, images_dir), unsafe_allow_html=True)
        else:
            st.info("当前内容尚未生成。")
with pdf_col:
    st.caption("原始 PDF")
    if pdf_path.exists():
        pdf_viewer(pdf_path)
    else:
        st.info("未找到原始 PDF。")
