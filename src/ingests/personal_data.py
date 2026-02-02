import os
import glob
import chromadb
import google.generativeai as genai
from termcolor import cprint
from dotenv import load_dotenv
import json

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.utils import safe_generate_json
from src.utils import extract_text_from_pdf

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
            # 使用 utils 中的 extract_text_from_pdf (基於 utils.py:12)
            text, used_ocr = extract_text_from_pdf(file_path, model_name=MODEL_NAME)
            # [修正點 1] 回傳通用的 "pdf_document"，不要在這裡定死它是 resume
            return text, "pdf_document"

        # === 處理筆記 (MD/TXT) ===
        elif ext in [".md", ".txt"]:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read(), "personal_note"

        # === [NEW] 處理 JSON (user_profile.json) ===
        elif ext == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                json_content = json.load(f)
                
                # 如果是 user_profile.json，標記為特殊類型，不要過度 summarize
                if filename == "user_profile.json":
                    text = json.dumps(json_content, indent=2, ensure_ascii=False)
                    return text, "user_profile"  # 特殊 doc_type
                else:
                    text = json.dumps(json_content, indent=2, ensure_ascii=False)
                    return text, "structured_data"

        else:
            return None, None

    except Exception as e:
        cprint(f"❌ 讀取檔案失敗 {file_path}: {e}", "red")
        return None, None

def indexer_agent_process(filename, text, doc_type):
    # 如果是 user_profile，直接跳過 LLM，用原始 metadata
    if doc_type == "user_profile":
        return {
            "summary": "User Profile (Pre-computed cheat sheet)",
            "domain": "Career Profile",
            "tags": ["#UserProfile", "#Skills", "#Education"],
            "is_resume": False
        }
    else:
        prompt = f"""
        You are my Personal Data Archivist.
        I am ingesting a document into my personal knowledge base.
        
        Filename: {filename}
        Type: {doc_type}
        Content Snippet: {text}
        
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

def generate_user_profile_from_raw():
    """
    [NEW] 從 raw/ 資料夾中的所有檔案自動產生 user_profile.json
    """
    cprint("🤖 自動產生 user_profile.json...", "cyan")
    
    # 讀取所有 raw 檔案內容
    raw_content = ""
    for file_path in glob.glob(os.path.join(RAW_DATA_PATH, "*")):
        filename = os.path.basename(file_path)
        
        # 跳過 user_profile.json 本身
        if filename == "user_profile.json":
            continue
        
        content, doc_type = extract_text(file_path)
        if content:
            raw_content += f"\n\n=== {filename} ===\n{content}\n"
    
    if not raw_content:
        cprint("❌ 沒有可用的 raw 檔案來產生 user_profile", "red")
        return None
    
    # 用 LLM 產生結構化 user_profile
    prompt = f"""
    You are extracting a structured user profile from personal documents.
    
    ### SOURCE DATA:
    {raw_content}
    
    ### TASK:
    Extract the following information into a structured JSON format:
    
    ### OUTPUT JSON SCHEMA:
    {{
      "name": "User's full name",
      "current_position": "Current job title",
      "education": [
        {{"degree": "PhD/Master/Bachelor", "field": "...", "institution": "...", "year": "..."}}
      ],
      "skills": ["Skill1", "Skill2", ...],
      "experience": [
        {{"role": "Job Title", "company": "...", "duration": "...", "highlights": ["..."]}}
      ],
      "research_interests": ["Topic1", "Topic2", ...],
      "languages": ["English", "Chinese", ...],
      "summary": "Brief professional summary in 2-3 sentences"
    }}
    
    Important: Extract ONLY information that is explicitly present in the documents. Use "Unknown" for missing fields.
    """
    
    default_profile = {
        "name": "Unknown",
        "current_position": "Unknown",
        "education": [],
        "skills": [],
        "experience": [],
        "summary": "Auto-generated profile from raw data"
    }
    
    generated_profile = safe_generate_json(model, prompt, retries=3, default_output=default_profile)
    
    # 加入 metadata
    generated_profile["_metadata"] = {
        "source": "auto_generated",
        "generated_from": "data/raw/*",
        "note": "This is an automatically generated profile. For better results, manually create user_profile.json"
    }
    
    return generated_profile

def ingest_personal_data():
    cprint(f"🚀 [Level 0] 開始建置個人知識庫 (Ingesting Personal Data)...", "cyan", attrs=['bold'])
    
    # === [NEW] Step 1: 檢查並處理 user_profile.json ===
    manual_profile_path = os.path.join(RAW_DATA_PATH, "user_profile.json")
    auto_profile_path = os.path.join(CHROMA_PATH, "auto_generated_user_profile.json")
    
    has_manual_profile = os.path.exists(manual_profile_path)
    
    if has_manual_profile:
        cprint("✅ 偵測到手動 user_profile.json，將跳過其 ChromaDB ingestion", "green")
        cprint("   → Phase 3 會直接讀取此檔案，保留完整結構", "green")
    else:
        cprint("⚠️ 未偵測到 user_profile.json，啟動自動產生模式...", "yellow")
        
        # 檢查是否已經有 auto_generated 版本
        if os.path.exists(auto_profile_path):
            cprint(f"ℹ️  已存在 auto_generated_user_profile.json，跳過重新產生", "cyan")
        else:
            # 產生新的 auto_generated_user_profile.json
            generated_profile = generate_user_profile_from_raw()
            
            if generated_profile:
                os.makedirs(CHROMA_PATH, exist_ok=True)
                with open(auto_profile_path, 'w', encoding='utf-8') as f:
                    json.dump(generated_profile, f, indent=2, ensure_ascii=False)
                cprint(f"✅ 自動產生完成: {auto_profile_path}", "green")
            else:
                cprint("❌ 自動產生失敗，Phase 3 將僅使用 ChromaDB 查詢", "red")
    
    # === Step 2: 開始 ChromaDB Ingestion ===
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(name="personal_knowledge")
    
    files = glob.glob(os.path.join(RAW_DATA_PATH, "*"))
    
    count = 0
    skipped_count = 0
    
    for file_path in files:
        filename = os.path.basename(file_path)
        
        # 1. 讀取
        content, doc_type = extract_text(file_path)
        if not content:
            continue
        
        # === [CRITICAL] 跳過 user_profile.json 的 ingestion ===
        if filename == "user_profile.json":
            cprint(f"\n⏭️  跳過 {filename} (Phase 3 會直接讀取，避免被壓縮)", "yellow")
            skipped_count += 1
            continue
        
        cprint(f"\n📄 分析檔案: {filename} ({doc_type})", "white")
        
        # 2. AI 理解 & 標記
        cprint("  🤖 Indexer Agent Analyzing...", "blue")
        metadata = indexer_agent_process(filename, content, doc_type)
        cprint(f"  🏷️  Domain: {metadata.get('domain')}", "green")
        cprint(f"  📝 Summary: {metadata.get('summary')}", "green")
        
        # 3. 格式化 Metadata
        storage_meta = {
            "filename": filename,
            "doc_type": doc_type,
            "domain": metadata.get("domain", "Unknown"),
            "tags": ", ".join(metadata.get("tags", [])),
            "is_resume": str(metadata.get("is_resume", False)),
            "summary": metadata.get("summary", "")
        }
        
        # 4. 存入 ChromaDB
        try:
            collection.upsert(
                documents=[content],
                metadatas=[storage_meta],
                ids=[filename]
            )
            cprint("  ✅ Saved to Knowledge Base", "magenta")
            count += 1
        except Exception as e:
            cprint(f"❌ DB Error: {e}", "red")
    
    cprint(f"\n🎉 建置完成！你的數位分身現在擁有 {count} 份記憶。", "cyan", attrs=['bold'])
    if skipped_count > 0:
        cprint(f"   (跳過 {skipped_count} 個檔案以保護結構)", "yellow")

        
if __name__ == "__main__":
    ingest_personal_data()