import os
import glob
import time
import chromadb
import google.generativeai as genai
from termcolor import colored, cprint # 改用 colored 來產生字串，交給 tqdm 印
from dotenv import load_dotenv
from pypdf import PdfReader
from tqdm import tqdm # 引入進度條

# === 引入工具 ===
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.utils import safe_generate_json, gemini_ocr 

load_dotenv()
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")

# 路徑設定
PATH_ONGOING = "/app/data/history/ongoing"
PATH_REJECTED = "/app/data/history/rejected"

FORCE_UPDATE = os.getenv("FORCE_UPDATE", "False").lower() == "true"

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

def extract_text_smart(filepath):
    """智慧讀取：PDF -> Text, 失敗轉 OCR"""
    text = ""
    used_ocr = False
    
    try:
        reader = PdfReader(filepath)
        for page in reader.pages:
            content = page.extract_text()
            if content: text += content + "\n"
    except Exception:
        pass 

    # OCR 判斷
    if len(text.strip()) < 50:
        # 這裡不 print 了，交給外層顯示狀態，保持進度條乾淨
        text = gemini_ocr(filepath, model_name=MODEL_NAME)
        used_ocr = True
    
    return text, used_ocr

def indexer_agent_history(filename, text, status):
    """🤖 History Indexer Agent"""
    prompt = f"""
    You are analyzing a PAST JOB APPLICATION (JD).
    Filename: {filename}
    Status: {status}
    Snippet: {text[:8000]}
    
    Extract JSON:
    {{
        "role": "Title",
        "experience_level": "Experience Level",
        "domain": "Domain",
        "tech_stack": ["Skill1", "Skill2"],
        "summary": "One liner",
        "tags": ["#Tag1"]
    }}
    """
    default = {"role": "Unknown", "experience_level": "Unknown", "domain": "Unknown", "tech_stack": [], "summary": "", "tags": []}
    return safe_generate_json(model, prompt, retries=3, default_output=default)

def process_folder(base_path, status_label, collection):
    search_path = os.path.join(base_path, "**", "*.pdf")
    files = glob.glob(search_path, recursive=True)
    
    if not files: return 0

    # 這裡用 cprint 沒關係，因為進度條還沒開始
    cprint(f"📂 掃描目錄: {base_path} ({len(files)} files)", "white")

    count = 0
    skipped_count = 0
    seen_ids = set() 

    # === [NEW] 初始化進度條 ===
    # desc: 進度條左邊的文字
    # unit: 單位
    pbar = tqdm(files, desc=f"Processing {status_label}", unit="file")

    for filepath in pbar:
        filename = os.path.basename(filepath)
        folder_name = os.path.basename(os.path.dirname(filepath))
        
        # 動態更新進度條右邊的資訊 (顯示當前正在看哪個檔案)
        pbar.set_postfix(file=filename[:20]) # 只顯示前20字元避免太長

        # 1. 計算 ID
        safe_status = status_label.replace("/", "_").replace(" ", "_")
        doc_id = f"history_{safe_status}_{folder_name}_{filename}"
        
        # 2. 檢查是否存在
        if not FORCE_UPDATE:
            existing = collection.get(ids=[doc_id])
            if existing and existing['ids']:
                skipped_count += 1
                continue # tqdm 會自動推進進度條，不用手動 update

        # --- 進入處理流程 (會花時間) ---
        
        # 3. 讀取文字
        text, used_ocr = extract_text_smart(filepath)
        if not text or len(text) < 50:
            # 使用 tqdm.write 避免打亂進度條
            tqdm.write(colored(f"   ⚠️ [Skip] Empty content: {filename}", "yellow"))
            continue

        # 4. Agent 分析
        # 在做 LLM 這種耗時操作時，可以更新一下 description 讓使用者知道沒卡死
        pbar.set_description(f"🤖 AI Analyzing: {filename[:15]}...")
        
        meta = indexer_agent_history(filename, text, status_label)

        # 5. 準備 Metadata
        storage_meta = {
            "source": "history",
            "folder": folder_name,
            "filename": filename,
            "status": status_label,
            "role": meta.get("role", "Unknown"),
            "experience_level": meta.get("experience_level", "Unknown"),
            "domain": meta.get("domain", "Unknown"),
            "skills": ", ".join(meta.get("tech_stack", [])),
            "tags": ", ".join(meta.get("tags", [])),
            "summary": meta.get("summary", "")
        }

        # 6. 寫入 DB
        collection.upsert(
            documents=[text],
            metadatas=[storage_meta],
            ids=[doc_id]
        )
        
        # 顯示成功訊息 (印在進度條上方)
        ocr_tag = colored(" [OCR]", "magenta") if used_ocr else ""
        msg = colored(f"   ✅ Indexed: {meta.get('role')} @ {folder_name}", "green")
        tqdm.write(msg + ocr_tag)
        
        count += 1
        
        # 恢復原本的 Description
        pbar.set_description(f"Processing {status_label}")
        
        if used_ocr: time.sleep(2)

    # 跑完該目錄後的總結
    if skipped_count > 0:
        tqdm.write(colored(f"   (Skipped {skipped_count} existing files)", "light_grey"))
        
    return count

def ingest_history_jds():
    cprint("\n📜 [Level 0] Building History Index (Incremental)...", "cyan", attrs=['bold'])
    
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="past_applications_jds")
    
    total_new = 0
    
    if os.path.exists(PATH_ONGOING):
        total_new += process_folder(PATH_ONGOING, "Ongoing", collection)
    
    print("-" * 40) # 分隔線
    
    if os.path.exists(PATH_REJECTED):
        total_new += process_folder(PATH_REJECTED, "Rejected", collection)

    cprint(f"\n✅ All Done! Added {total_new} new records.", "magenta", attrs=['bold'])

if __name__ == "__main__":
    ingest_history_jds()