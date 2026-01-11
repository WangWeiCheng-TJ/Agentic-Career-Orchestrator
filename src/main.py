import os
import re
import glob
import time
import json
import csv
import google.generativeai as genai
import chromadb
from termcolor import cprint
from dotenv import load_dotenv
from pypdf import PdfReader
from pathlib import Path

# --- 配置區 ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-pro")
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")
INPUT_DIR = "/app/data/jds"
OUTPUT_DIR = "/app/data/reports"

# 初始化
genai.configure(api_key=API_KEY)
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

class PrivacyShield:
    def __init__(self):
        self.patterns = {
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}': '[EMAIL_REDACTED]',
            r'\+?[0-9\s\-\(\)]{8,}': '[PHONE_REDACTED]',
        }
    def sanitize(self, text):
        for pattern, replacement in self.patterns.items():
            text = re.sub(pattern, replacement, text)
        return text

class AgentBrain:
    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME)
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.memory = self.chroma_client.get_or_create_collection(name="job_experiences")
        self.shield = PrivacyShield()

    def ocr_image_pdf(self, filepath):
        cprint(f"   👁️ 啟動 Gemini Vision 進行雲端 OCR...", "magenta")
        try:
            sample_file = genai.upload_file(path=filepath, display_name="JD File")
            while sample_file.state.name == "PROCESSING":
                time.sleep(1)
                sample_file = genai.get_file(sample_file.name)
            
            prompt = "Extract all text from this document accurately."
            response = self.model.generate_content([sample_file, prompt])
            return response.text
        except Exception as e:
            cprint(f"   ❌ Cloud OCR 失敗: {e}", "red")
            return None

    def retrieve_context(self, jd_text, n_results=3):
        query_text = jd_text[:500] 
        results = self.memory.query(query_texts=[query_text], n_results=n_results)
        
        context_str = ""
        sources_list = []
        if results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                source = meta.get('source', 'Unknown')
                sources_list.append(source)
                context_str += f"\n[Evidence {i+1} from {source}]:\n{doc}\n"
        
        return context_str, list(set(sources_list))

    def think(self, jd_text, filename):
        safe_jd = self.shield.sanitize(jd_text)
        retrieved_knowledge, sources = self.retrieve_context(safe_jd)
        source_msg = ', '.join(sources) if sources else "None"

        prompt = f"""
        You are a specialized Career Agent. Target Job File: {filename}
        
        USER CONTEXT (My background):
        {retrieved_knowledge}
        
        USER VALUES:
        - Goal: Financial independence (>125k USD/EUR), Avoid "Box 3" wealth tax traps.
        - Tech: Prefer "Black Tech" / Optimization / Privacy AI. Hate maintenance of legacy code.
        - Visa: Needs Visa Sponsorship (Non-EU citizen).

        TARGET JOB DESCRIPTION:
        {safe_jd}

        ---
        MISSION:
        1. Analyze this job using the 3-Agent Persona.
        2. **CRITICAL**: Output a JSON block at the end.

        ### 🛡️ AGENT 1: BLIND-SPOT RADAR
        ### 💀 AGENT 2: DEVIL'S ADVOCATE
        ### ♟️ AGENT 3: THE STRATEGIST

        ---
        ### 📊 SCORING (JSON Format)
        Provide valid JSON inside ```json``` tags.
        Keys: "company_name", "role_name", "match_score" (0-100), "risk_level" (Low/Medium/High), "salary_potential", "visa_friendly", "one_line_summary".
        """

        response = self.model.generate_content(prompt)
        return response.text, source_msg

def smart_extract_text(filepath, agent):
    path = Path(filepath)
    text = ""
    
    # --- 快取機制 (Caching Strategy) ---
    # 如果是 PDF，先檢查旁邊有沒有同名的 .txt
    cached_txt_path = path.with_suffix('.txt')
    
    if path.suffix.lower() == '.pdf' and cached_txt_path.exists():
        cprint(f"   ⚡ 發現本地緩存 (Cached Text): {cached_txt_path.name}", "cyan")
        try:
            with open(cached_txt_path, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > 50:
                return content
        except Exception:
            cprint("   ⚠️ 緩存讀取失敗，重新進行提取...", "yellow")

    # --- 沒緩存，開始提取 ---
    try:
        if path.suffix.lower() == '.pdf':
            reader = PdfReader(filepath)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted: text += extracted + "\n"
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
    except Exception:
        pass

    # --- 判斷是否需要 OCR ---
    if len(text.strip()) < 50 and path.suffix.lower() == '.pdf':
        cprint(f"   ⚠️ 本地提取失敗，切換至 Cloud OCR...", "yellow")
        text = agent.ocr_image_pdf(filepath)
        
        # --- OCR 成功後，寫入緩存 ---
        if text and len(text) > 50:
            try:
                with open(cached_txt_path, "w", encoding="utf-8") as f:
                    f.write(text)
                cprint(f"   💾 OCR 結果已保存至: {cached_txt_path.name}", "blue")
            except Exception as e:
                cprint(f"   ❌ 緩存寫入失敗: {e}", "red")
    
    return text

def extract_json_score(text):
    try:
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match: return json.loads(match.group(1))
        match = re.search(r"(\{.*\"match_score\".*\})", text, re.DOTALL)
        if match: return json.loads(match.group(1))
    except Exception:
        pass
    return None

def batch_process():
    cprint(f"🚀 啟動戰略分析模式 (With Local Caching)", "cyan")
    
    files = sorted(glob.glob(os.path.join(INPUT_DIR, "*")))
    # 只抓 .pdf 和 .txt (.md)
    files = [f for f in files if f.lower().endswith(('.pdf', '.txt', '.md'))]

    if not files:
        cprint("⚠️ data/jds/ 目錄為空", "red")
        return

    agent = AgentBrain()
    leaderboard_data = []
    
    # 建立一個已處理的集合，避免重複處理 (例如同時有 JD.pdf 和 JD.txt)
    processed_stems = set()

    for idx, filepath in enumerate(files):
        filename = os.path.basename(filepath)
        file_stem = os.path.splitext(filename)[0] # 檔名不含副檔名
        path_obj = Path(filepath)

        # 邏輯優化：如果這個檔名的 PDF 已經處理過，或是現在遇到 TXT 但旁邊有 PDF，就跳過 TXT
        # (優先處理 PDF，因為 PDF 處理流程會自動讀/寫 TXT)
        if path_obj.suffix.lower() == '.txt':
             pdf_version = path_obj.with_suffix('.pdf')
             if pdf_version.exists():
                 # 讓迴圈跑到 PDF 那一次再處理，這裡先跳過
                 continue
        
        cprint(f"[{idx+1}/{len(files)}] 分析: {filename} ...", "yellow")

        content = smart_extract_text(filepath, agent)
        if not content or len(content) < 50:
            cprint(f"   ❌ 跳過 (無內容)", "red")
            continue

        try:
            # 1. AI 思考
            analysis_text, used_sources = agent.think(content, filename)
            
            # 2. 提取分數
            score_data = extract_json_score(analysis_text)
            
            if score_data:
                score_data['filename'] = filename
                leaderboard_data.append(score_data)
                score = score_data.get('match_score', 0)
                risk = score_data.get('risk_level', 'Unknown')
                cprint(f"   ✅ 完成 | 分數: {score} | 風險: {risk}", "green")
            else:
                cprint(f"   ⚠️ 完成但無法提取分數", "yellow")

            # 3. 存報告
            report_filename = f"Analysis_{file_stem}.md"
            with open(os.path.join(OUTPUT_DIR, report_filename), "w", encoding="utf-8") as f:
                f.write(f"# Job Analysis: {filename}\n")
                f.write(f"**Sources:** {used_sources}\n\n")
                f.write(analysis_text)
            
        except Exception as e:
            cprint(f"   ❌ Error: {e}", "red")

    # --- 生成 Leaderboard CSV ---
    if leaderboard_data:
        cprint("\n📊 正在生成戰略排行榜...", "cyan")
        csv_path = os.path.join(OUTPUT_DIR, "Strategic_Leaderboard.csv")
        leaderboard_data.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        keys = ["match_score", "company_name", "role_name", "risk_level", "salary_potential", "visa_friendly", "one_line_summary", "filename"]
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for row in leaderboard_data:
                filtered_row = {k: row.get(k, "N/A") for k in keys}
                writer.writerow(filtered_row)     
        cprint(f"🏆 排行榜已建立: {csv_path}", "green")

if __name__ == "__main__":
    batch_process()