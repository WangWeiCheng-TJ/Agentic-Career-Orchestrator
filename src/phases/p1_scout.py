import os
import glob
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from termcolor import colored, cprint
import google.generativeai as genai
from tqdm import tqdm  # [New] 進度條
from uuid import uuid4 #prevent name collision perticularly when parallel

import argparse

# === parallel
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# === IMPORTS ===
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.agents.jd_parser import JDParserAgent
from src.utils import extract_text_from_pdf

try:
    from src.tools.tool import ToolRegistry
except ImportError:
    cprint("❌ Error: Could not import ToolRegistry. Check src/tools/registry.py", "red")
    sys.exit(1)

# === CONFIG ===
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")

DIR_INCOMING = "/app/data/jds"

# 輸出路徑 (保持不變，因為這是在 /app/data 下，也會被持久化)
DIR_PROCESSED = "/app/data/processed/dossiers"
MAX_WORKERS = os.getenv("MAX_WORKERS", 5)
FORCE_UPDATE = os.getenv("FORCE_UPDATE", "false").lower() == "true"

# 確保輸出目錄存在
os.makedirs(DIR_PROCESSED, exist_ok=True)
if not os.path.exists(DIR_INCOMING):
    cprint(f"⚠️ Warning: {DIR_INCOMING} does not exist inside container.", "yellow")

# [測試設定] 設定為整數 (e.g., 3) 只跑前 3 筆。設定為 None 則跑全部。
TEST_LIMIT = None


def _get_output_path(filepath: str, output_dir: str) -> str:
    filename = os.path.basename(filepath)
    output_filename = f"{os.path.splitext(filename)[0]}_dossier.json"
    return os.path.join(output_dir, output_filename)
    
# ==========================================
# 🔧 Worker Function
# ==========================================
def _scout_worker(filepath, parser, tools, output_dir, model_name, force_update):
    filename = os.path.basename(filepath)
    output_path = _get_output_path(filepath, output_dir)

    if os.path.exists(output_path) and not force_update:
        tqdm.write(colored(f"⏭️ Skip existing: {filename}", "blue"))
        return "skipped"
    
    try:
        # Step A: 讀檔
        text, used_ocr = extract_text_from_pdf(filepath, model_name=MODEL_NAME)
        if not text or len(text) < 50:
            tqdm.write(colored(f"❌ Read Error (Skipping): {filename}", "red"))
            return None

        # Step B: 解析（parser 內部會走 gateway，rate limit 自動套用）
        parsed_data = parser.parse(text, filename)

        # Step C: 情報增強
        try:
            intel_report = tools.run_tools(parsed_data)
        except Exception as e:
            tqdm.write(colored(f"⚠️ Tool Error [{filename}]: {e}", "yellow"))
            intel_report = "Tool execution failed."

        # Step D: 打包
        dossier = {
            "id": f"{os.path.splitext(filename)[0]}_{uuid4().hex[:8]}",
            "metadata": {
                "source": filename,
                "scanned_at": datetime.now().isoformat(),
                "ocr_used": used_ocr,
                "parser_version": "v3.3"
            },
            "basic_info": parsed_data,
            "intelligence_report": intel_report,
            "raw_content": text
        }

        # Step E: 存檔
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dossier, f, indent=2, ensure_ascii=False)

        role = parsed_data.get("role", "Unknown")
        company = parsed_data.get("company", "Unknown")
        ocr_tag = colored(" [OCR]", "magenta") if used_ocr else ""
        tqdm.write(colored(f"✅ Saved: {company} - {role}", "green") + ocr_tag)
        return "saved"


    except Exception as e:
        tqdm.write(colored(f"❌ Worker Error [{filename}]: {e}", "red"))
        return None

def run_scout(args):
    os.makedirs(args.output_dir, exist_ok=True)

    # 顯示目前模式
    mode_msg = f"(Testing Mode: First {TEST_LIMIT} files)" if TEST_LIMIT else "(Full Batch Mode)"
    force_msg = " [FORCE_UPDATE]" if FORCE_UPDATE else ""
    cprint(f"\n🕵️ [Phase 1] SCOUT AGENT STARTED {mode_msg}{force_msg}", "cyan", attrs=['bold', 'reverse'])
    
    # 1. 初始化
    if not API_KEY:
        cprint("❌ Error: API Key missing.", "red")
        return

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(args.model_name)
    parser = JDParserAgent(model)
    
    cprint("🧰 Initializing Tool Registry...", "white")
    tools = ToolRegistry()
    
    # 2. 掃描檔案
    all_files = sorted(glob.glob(os.path.join(args.input_dir, args.pattern)))
    if not all_files:
        cprint(f"😴 No files found in {args.input_dir} with pattern {args.pattern}", "yellow")
        return
    
    if args.force_update:
        candidate_files = all_files
    else:
        candidate_files = [
            fp for fp in all_files
            if not os.path.exists(_get_output_path(fp, args.output_dir))
        ]

    # [關鍵] 切片：只取前 N 筆做測試
    target_files = candidate_files[:args.test_limit] if args.test_limit else candidate_files

    cprint(f"📂 Found {len(all_files)} files. Pending {len(candidate_files)}. Processing {len(target_files)}...", "white")
    print("-" * 40)

    if not target_files:
        cprint("✅ Nothing to do. All dossiers already exist.", "green")
        return

    saved_count = 0
    skipped_count = 0


    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                _scout_worker, fp, parser, tools, args.output_dir, args.model_name, args.force_update
            ): fp
            for fp in target_files
        }
        
        pbar = tqdm(as_completed(futures), total=len(futures), desc="🚀 Scouting", unit="jd")
        for future in pbar:
            result = future.result()
            if result == "saved":
                saved_count += 1
            elif result == "skipped":
                skipped_count += 1
            pbar.set_postfix(saved=saved_count, skipped=skipped_count)

    cprint(f"\n🎉 Scout Complete! (saved={saved_count}, skipped={skipped_count}, total={len(target_files)})", "magenta", attrs=['bold'])
    cprint(f"📁 Check output at: {args.output_dir}", "white")

def parse_args():
    parser = argparse.ArgumentParser(description="Phase 1 Scout Agent")
    parser.add_argument("--input-dir", default=DIR_INCOMING, help="Directory containing incoming JD PDFs")
    parser.add_argument("--output-dir", default=DIR_PROCESSED, help="Directory to save generated dossiers")
    parser.add_argument("--pattern", default="*.pdf", help="Glob pattern for incoming files")
    parser.add_argument("--test-limit", type=int, default=TEST_LIMIT, help="Only process first N files")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="Number of parallel workers")
    parser.add_argument("--force-update", action="store_true", default=FORCE_UPDATE, help="Re-run even if dossier already exists")
    parser.add_argument("--model-name", default=MODEL_NAME, help="Model name for OCR / parsing")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run_scout(args)

