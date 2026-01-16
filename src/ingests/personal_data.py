import os
import glob
import chromadb
import google.generativeai as genai
from termcolor import cprint
from dotenv import load_dotenv
from pypdf import PdfReader

# 引入防呆工具 (請確保 src/utils/llm_utils.py 存在)
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.utils import safe_generate_json
from src.utils import gemini_ocr

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")
RAW_DATA_PATH = "/app/data/raw" # 這裡放你所有的個人資料 (PDF/MD/TXT)

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

def extract_text(file_path):
    """
    智慧讀取：先嘗試一般讀取，讀不到就切換 OCR。
    """
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)

    try:
        # === 處理 PDF ===
        if ext == ".pdf":
            text = ""
            try:
                reader = PdfReader(file_path)
                for page in reader.pages:
                    content = page.extract_text()
                    if content:
                        text += content + "\n"
            except Exception as e:
                cprint(f"   ⚠️ pypdf 讀取失敗，嘗試 OCR... ({e})", "yellow")
                text = "" # 設為空，觸發下方的 OCR

            # [OCR 防呆邏輯]
            # 如果讀出來是空的，或是字數太少 (例如 < 100 字，可能只是圖表或 header)，就當作它是掃描檔
            if not text or len(text.strip()) < 50:
                cprint(f"   👁️ 偵測到掃描檔或純圖片 PDF，啟動 Gemini OCR: {filename}", "cyan")
                text = gemini_ocr(file_path, model_name=MODEL_NAME)
            
            # [修正點 1] 回傳通用的 "pdf_document"，不要在這裡定死它是 resume
            return text, "pdf_document"

        # === 處理筆記 (MD/TXT) ===
        elif ext in [".md", ".txt"]:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read(), "personal_note"
        
        else:
            return None, None

    except Exception as e:
        cprint(f"❌ 讀取檔案失敗 {file_path}: {e}", "red")
        return None, None

def indexer_agent_process(filename, text, doc_type):
    """
    🤖 Indexer Agent: 不管是履歷還是筆記，通通貼上標籤
    """
    prompt = f"""
    You are my Personal Data Archivist.
    I am ingesting a document into my personal knowledge base.
    
    Filename: {filename}
    Type: {doc_type}
    Content Snippet: {text[:6000]}
    
    ### TASK
    1. Identify the **Topic/Domain** (e.g., "Resume V1", "Project Alpha Notes", "Research Idea").
    2. Extract **Keywords/Skills** mentioned.
    3. Summarize the content in one sentence.
    
    ### OUTPUT JSON
    {{
        "summary": "Brief summary of this file.",
        "domain": "Computer Vision / System Design / Career Profile",
        "tags": ["#Tag1", "#Tag2"],
        "is_resume": true/false
    }}
    """
    
    default_res = {
        "summary": "Processing Failed",
        "domain": "Unknown",
        "tags": [],
        "is_resume": False
    }

    return safe_generate_json(model, prompt, retries=3, default_output=default_res)

def ingest_personal_data():
    cprint(f"🚀 [Level 0] 開始建置個人知識庫 (Ingesting Personal Data)...", "cyan", attrs=['bold'])
    
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # 我們把 Collection 名字改得更通用一點，叫 "personal_knowledge"
    collection = client.get_or_create_collection(name="personal_knowledge")
    
    files = glob.glob(os.path.join(RAW_DATA_PATH, "*"))
    
    count = 0
    for file_path in files:
        filename = os.path.basename(file_path)
        
        # 1. 讀取
        content, doc_type = extract_text(file_path)
        if not content: continue
        
        cprint(f"\n📄 分析檔案: {filename} ({doc_type})", "white")

        # 2. AI 理解 & 標記
        cprint("   🤖 Indexer Agent Analyzing...", "blue")
        metadata = indexer_agent_process(filename, content, doc_type)

        cprint(f"   🏷️ Domain: {metadata.get('domain')}", "green")
        cprint(f"   📝 Summary: {metadata.get('summary')}", "green")

        # 3. 格式化 Metadata
        storage_meta = {
            "filename": filename,
            "doc_type": doc_type,
            "domain": metadata.get("domain", "Unknown"),
            "tags": ", ".join(metadata.get("tags", [])),
            "is_resume": str(metadata.get("is_resume", False)), # Chroma 不存 bool，轉字串
            "summary": metadata.get("summary", "")
        }

        # 4. 存入 (整份存入，不切塊，保持完整語意)
        try:
            collection.upsert(
                documents=[content],
                metadatas=[storage_meta],
                ids=[filename]
            )
            cprint("   ✅ Saved to Knowledge Base", "magenta")
            count += 1
        except Exception as e:
            cprint(f"❌ DB Error: {e}", "red")

    cprint(f"\n🎉 建置完成！你的數位分身現在擁有 {count} 份記憶。", "cyan", attrs=['bold'])

if __name__ == "__main__":
    ingest_personal_data()