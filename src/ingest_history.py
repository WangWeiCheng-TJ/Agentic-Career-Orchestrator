# src/ingest_history.py
import os
import glob
import chromadb
from pypdf import PdfReader
from termcolor import cprint
from dotenv import load_dotenv
import time
import google.generativeai as genai # 還是需要這個來 configure API Key

from utils import gemini_ocr

load_dotenv()
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-pro")

# 對應 docker-compose.yml 的掛載點
PATH_ONGOING = "/app/data/history/ongoing"
PATH_REJECTED = "/app/data/history/rejected"

def process_folder(base_path, status_label, collection):
    """
    掃描指定目錄下的 PDF，優先使用 pypdf，若無效則呼叫 utils.gemini_ocr。
    """
    search_path = os.path.join(base_path, "**", "*.pdf")
    files = glob.glob(search_path, recursive=True)
    
    documents = []
    metadatas = []
    ids = []
    count = 0
    
    # [新增] 避免重複 ID 的計數器 (防呆用)
    seen_ids = set() 
    
    for filepath in files:
        filename = os.path.basename(filepath).lower()
        
        # 關鍵字過濾
        if any(k in filename for k in ["jd", "job", "description", "vacancy", "role"]):
            text = ""
            used_ocr = False
            
            # --- 1. pypdf ---
            try:
                reader = PdfReader(filepath)
                for page in reader.pages: 
                    extract = page.extract_text()
                    if extract: text += extract + "\n"
            except: pass

            # --- 2. OCR ---
            if len(text) < 50:
                text = gemini_ocr(filepath, model_name=MODEL_NAME)
                if text: used_ocr = True
            
            # --- 3. 寫入 ---
            if text and len(text) > 50:
                folder_path = os.path.dirname(filepath)
                folder_name = os.path.basename(folder_path)
                original_filename = os.path.basename(filepath) # 取得原始檔名
                
                # [修正重點] 產生唯一 ID
                # 1. 把 status 裡的特殊符號拿掉 (Ongoing/Pending -> Ongoing_Pending)
                safe_status = status_label.replace("/", "_").replace(" ", "_")
                # 2. 組合: history_狀態_公司_檔名
                doc_id = f"history_{safe_status}_{folder_name}_{original_filename}"
                
                # [雙重防呆] 如果真的有兩個一模一樣檔名的檔案，加個後綴
                if doc_id in seen_ids:
                    doc_id = f"{doc_id}_{int(time.time())}"
                seen_ids.add(doc_id)

                documents.append(text)
                metadatas.append({
                    "folder_path": folder_path, 
                    "company_role": folder_name,
                    "filename": original_filename, # 多記一個檔名方便除錯
                    "status": status_label 
                })
                ids.append(doc_id)
                count += 1
                
                msg = f"   ➕ [{status_label}] 索引: {folder_name}/{original_filename}"
                if used_ocr:
                    msg += " (OCR ✅)"
                    time.sleep(4) 
                print(msg)
            else:
                cprint(f"   ⚠️ 跳過: {filename}", "yellow")

    if documents:
        # 注意：upsert 會覆蓋舊 ID。
        # 因為我們改了 ID 格式，舊的 (以資料夾命名的) 資料會變成垃圾留在 DB 裡，
        # 但這不影響運作，只是多佔一點點空間。
        collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
    
    return count

def ingest_history_jds():
    cprint("📜 正在建立歷史戰役索引 (Indexing Past JDs)...", "cyan")
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="past_applications_jds")
    
    total = 0
    
    # 1. 處理 Ongoing (Applied -> Pending)
    if os.path.exists(PATH_ONGOING):
        total += process_folder(PATH_ONGOING, "Ongoing/Pending", collection)
    else:
        cprint(f"⚠️ 路徑不存在: {PATH_ONGOING}", "yellow")
        
    # 2. 處理 Rejected (已拒絕)
    if os.path.exists(PATH_REJECTED):
        total += process_folder(PATH_REJECTED, "Rejected", collection)
    else:
        cprint(f"⚠️ 路徑不存在: {PATH_REJECTED}", "yellow")

    cprint(f"✅ 歷史 JD 索引完成！總共 {total} 筆戰績已入庫。", "green")

if __name__ == "__main__":
    ingest_history_jds()