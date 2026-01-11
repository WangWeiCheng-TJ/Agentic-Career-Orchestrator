import os
import glob
import chromadb
from pypdf import PdfReader
from termcolor import cprint
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")
RAW_DATA_PATH = "/app/data/raw"

def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print(f"❌ 無法讀取 PDF {file_path}: {e}")
        return None

def ingest_data():
    cprint(f"🚀 開始資料注入流程...", "cyan")
    cprint(f"📂 掃描目錄: {RAW_DATA_PATH}", "cyan")

    # 1. 連接資料庫
    # 注意：這裡使用 Chroma 預設的 Embedding 模型 (all-MiniLM-L6-v2)
    # 它會自動下載並在本地 CPU 執行，完全免費且隱私。
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="job_experiences")

    # 2. 掃描檔案
    files = glob.glob(os.path.join(RAW_DATA_PATH, "*"))
    documents = []
    metadatas = []
    ids = []

    for file_path in files:
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        
        cprint(f"   📄 處理檔案: {filename}", "white")
        
        content = ""
        doc_type = "unknown"

        if ext == ".pdf":
            content = extract_text_from_pdf(file_path)
            doc_type = "cv_or_paper"
        elif ext in [".txt", ".md"]:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            doc_type = "notes"
        else:
            print(f"   ⚠️ 跳過不支援的格式: {filename}")
            continue

        if not content:
            continue

        # 3. 簡單切分 (Chunking)
        # 為了 MVP，我們用簡單的字元切分。
        # 進階版可以用 RecursiveCharacterTextSplitter (LangChain)
        chunk_size = 1000
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

        for idx, chunk in enumerate(chunks):
            documents.append(chunk)
            metadatas.append({"source": filename, "type": doc_type, "chunk_index": idx})
            ids.append(f"{filename}_chunk_{idx}")

    # 4. 寫入資料庫
    if documents:
        cprint(f"💾 正在寫入 {len(documents)} 筆資料片段到 ChromaDB...", "yellow")
        try:
            collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            cprint(f"✅ 資料注入完成！Collection 總筆數: {collection.count()}", "green")
        except Exception as e:
            cprint(f"❌ 寫入失敗: {e}", "red")
    else:
        cprint("⚠️ 沒有發現有效的文字資料。", "yellow")

if __name__ == "__main__":
    ingest_data()