import os
import glob
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from termcolor import colored, cprint
import google.generativeai as genai
from tqdm import tqdm  # [New] 進度條

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

# 確保輸出目錄存在
os.makedirs(DIR_PROCESSED, exist_ok=True)
if not os.path.exists(DIR_INCOMING):
    cprint(f"⚠️ Warning: {DIR_INCOMING} does not exist inside container.", "yellow")

# [測試設定] 設定為整數 (e.g., 3) 只跑前 3 筆。設定為 None 則跑全部。
TEST_LIMIT = None 

# ==========================================
# 🔧 Worker Function
# ==========================================
def _scout_worker(filepath, parser, tools):
    """單一 PDF 的處理 worker，給 ThreadPoolExecutor 用"""
    filename = os.path.basename(filepath)
    
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
            "id": f"job_{int(time.time())}_{filename[:10]}",
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
        output_filename = f"{os.path.splitext(filename)[0]}_dossier.json"
        output_path = os.path.join(DIR_PROCESSED, output_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(dossier, f, indent=2, ensure_ascii=False)

        role = parsed_data.get('role', 'Unknown')
        company = parsed_data.get('company', 'Unknown')
        ocr_tag = colored(" [OCR]", "magenta") if used_ocr else ""
        tqdm.write(colored(f"✅ Saved: {company} - {role}", "green") + ocr_tag)
        return filename

    except Exception as e:
        tqdm.write(colored(f"❌ Worker Error [{filename}]: {e}", "red"))
        return None

def run_scout():
    # 顯示目前模式
    mode_msg = f"(Testing Mode: First {TEST_LIMIT} files)" if TEST_LIMIT else "(Full Batch Mode)"
    cprint(f"\n🕵️  [Phase 1] SCOUT AGENT STARTED {mode_msg}", "cyan", attrs=['bold', 'reverse'])
    
    # 1. 初始化
    if not API_KEY:
        cprint("❌ Error: API Key missing.", "red")
        return

    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    parser = JDParserAgent(model)
    
    cprint("🧰 Initializing Tool Registry...", "white")
    tools = ToolRegistry()
    
    # 2. 掃描檔案
    all_files = glob.glob(os.path.join(DIR_INCOMING, "*.pdf"))
    if not all_files:
        cprint(f"😴 No PDF files found in {DIR_INCOMING}", "yellow")
        return

    # [關鍵] 切片：只取前 N 筆做測試
    target_files = all_files[:TEST_LIMIT] if TEST_LIMIT else all_files
    
    cprint(f"📂 Found {len(all_files)} files. Processing {len(target_files)}...", "white")
    print("-" * 40)

    success_count = 0
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_scout_worker, fp, parser, tools): fp
            for fp in target_files
        }
        pbar = tqdm(as_completed(futures), total=len(futures), desc="🚀 Scouting", unit="jd")
        for future in pbar:
            result = future.result()
            if result:
                success_count += 1
                pbar.set_postfix(done=f"{success_count}/{len(target_files)}")

    cprint(f"\n🎉 Scout Complete! ({success_count}/{len(target_files)} success)", "magenta", attrs=['bold'])
    cprint(f"📁 Check output at: {DIR_PROCESSED}", "white")

if __name__ == "__main__":
    run_scout()