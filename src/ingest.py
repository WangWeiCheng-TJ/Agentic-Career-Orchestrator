import os
import glob
import chromadb
from pypdf import PdfReader
from termcolor import cprint
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

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
    cprint(f"🚀 開始資料注入流程 (Recursive Splitter)...", "cyan")
    
    # 初始化 ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="job_experiences")

    # 初始化 LangChain 切分器
    # 邏輯：優先在 \n\n (段落) 切，不行才在 \n (換行) 切，再不行才在空格切
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", " ", ""]
    )

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
            continue

        if not content: continue

        # --- [升級] 使用 Recursive 切分 ---
        chunks = text_splitter.split_text(content)

        for idx, chunk in enumerate(chunks):
            documents.append(chunk)
            metadatas.append({"source": filename, "type": doc_type, "chunk_index": idx})
            # ID 保持唯一，避免重複寫入
            ids.append(f"{filename}_chunk_{idx}")

    if documents:
        cprint(f"💾 正在寫入 {len(documents)} 筆資料片段...", "yellow")
        try:
            # Upsert: 如果 ID 存在就更新，不存在就新增
            collection.upsert(documents=documents, metadatas=metadatas, ids=ids)
            cprint(f"✅ 資料注入完成！資料庫總筆數: {collection.count()}", "green")
        except Exception as e:
            cprint(f"❌ 寫入失敗: {e}", "red")
    else:
        cprint("⚠️ 無有效資料。", "yellow")

if __name__ == "__main__":
    ingest_data()