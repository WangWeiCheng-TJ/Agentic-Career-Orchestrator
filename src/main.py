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
from utils import gemini_ocr
from utils import identify_application_packet

# --- 配置區 ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-pro")
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")
INPUT_DIR = "/app/data/jds"
OUTPUT_DIR = "/app/data/reports"
RAW_DIR = "/app/data/raw"  # [新增] 用來讀 AboutMe.md

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

        # [新增] 啟動時載入 User Values
        self.user_values = self.load_user_profile()

    def load_user_profile(self):
        """ [新功能] 從 raw/AboutMe.md 讀取價值觀，而不是寫死在 Code 裡 """
        profile_path = os.path.join(RAW_DIR, "AboutMe.md")
        default_values = "- Goal: Find a job.\n- Visa: Need sponsorship."
        
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    cprint("   👤 已載入個人價值觀 (AboutMe.md)", "cyan")
                    return content
            except Exception as e:
                cprint(f"   ⚠️ 讀取 AboutMe.md 失敗: {e}", "red")
        else:
            cprint("   ⚠️ 找不到 AboutMe.md，使用預設值", "yellow")
        
        return default_values

    # def ocr_image_pdf(self, filepath):
    #     cprint(f"   👁️ 啟動 Gemini Vision 進行雲端 OCR...", "magenta")
    #     try:
    #         sample_file = genai.upload_file(path=filepath, display_name="JD File")
    #         while sample_file.state.name == "PROCESSING":
    #             time.sleep(1)
    #             sample_file = genai.get_file(sample_file.name)
            
    #         prompt = "Extract all text from this document accurately."
    #         response = self.model.generate_content([sample_file, prompt])
    #         return response.text
    #     except Exception as e:
    #         cprint(f"   ❌ Cloud OCR 失敗: {e}", "red")
    #         return None

    def generate_search_query(self, jd_text):
        """ 用 AI 提取關鍵字 """
        try:
            prompt = f"""
            Find the minimal and preferred requirements from this Job Description.
            Return ONLY a comma-separated string.
            JD: {jd_text[:3000]}
            """
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except:
            return jd_text[:500]

    def recall_past_lessons(self, jd_text):
        """ 
        [修正] 先用 generate_search_query 提取關鍵字，再去搜歷史 JD 
        """
        # 1. 取得歷史資料庫 (如果 ingest_history.py 沒跑過，這裡會是空的)
        history_collection = self.chroma_client.get_or_create_collection(name="past_applications_jds")
        if history_collection.count() == 0:
            return "No historical data indexed yet."

        # 2. [關鍵修正] 使用提取出的 Keyword 進行搜尋，而非原始 JD 全文
        search_query = self.generate_search_query(jd_text)
        # cprint(f"   🕰️ 歷史檢索關鍵字: {search_query}", "cyan")

        results = history_collection.query(
            query_texts=[search_query], 
            n_results=1
        )
        
        lesson_context = "No similar past application found."
        
        if results['documents'] and results['documents'][0]:
            # 這裡簡單判斷距離，實際可調
            meta = results['metadatas'][0][0]
            folder_path = meta['folder_path']
            company_role = meta['company_role']
            
            # 嘗試讀取 outcome
            outcome_text = "Unknown"
            outcome_files = glob.glob(os.path.join(folder_path, "*outcome*")) + glob.glob(os.path.join(folder_path, "*reject*"))
            if outcome_files:
                try:
                    with open(outcome_files[0], 'r', encoding='utf-8', errors='ignore') as f:
                        outcome_text = f.read()[:500] # 只讀前500字避免太長
                        # 未來應該要改成 smart_extract_text
                except: pass

            lesson_context = f"""
            *** HISTORY RECALL ALERT ***
            This new job matches keywords with a past application: '{company_role}'.
            
            Path: {folder_path}
            Past Outcome: {outcome_text}
            
            STRATEGIC INSTRUCTION:
            - If outcome was POSITIVE: Check the resume in that folder for reusable phrasing.
            - If outcome was NEGATIVE: Analyze the outcome text to avoid repeating mistakes.
            """
            
        return lesson_context

    def retrieve_context(self, jd_text, n_results=3):
        # 使用關鍵字搜尋個人背景
        query_text = self.generate_search_query(jd_text)
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
    
    # 在 AgentBrain class 內新增
    def recall_past_lessons(self, current_jd_text):
        """
        搜尋歷史資料庫，看有沒有類似的職缺，並提取當時的策略與結果。
        """
        # 1. 連接歷史 JD 資料庫
        history_collection = self.chroma_client.get_collection(name="past_applications_jds")
        
        # 2. 搜尋最像的 1 筆
        results = history_collection.query(
            query_texts=[current_jd_text[:1000]], # 用新 JD 的前 1000 字去搜
            n_results=1
        )
        
        lesson_context = "No similar past application found."
        
        if results['documents'] and results['documents'][0]:
            # 找到相似案例了！
            similarity_dist = results['distances'][0][0] # 距離越小越像
            meta = results['metadatas'][0][0]
            folder_path = meta['folder_path']
            company_role = meta['company_role']
            
            # 設定一個相似度門檻 (視距離算法而定，假設是 L2 distance)
            # 這裡先假設如果有找到就回傳，讓 LLM 自己判斷像不像
            
            # 3. 去那個資料夾挖出當時的 Resume 和 Outcome (如果有)
            
            packet = identify_application_packet(folder_path)
            
            outcome_text = "Unknown/Pending"
            if packet['outcome']:
                with open(packet['outcome'], 'r', encoding='utf-8', errors='ignore') as f:
                    outcome_text = f.read()
            
            resume_path = packet['resume'] if packet['resume'] else "Unknown"

            lesson_context = f"""
            *** HISTORY RECALL ALERT ***
            This new job is highly similar to a past application: '{company_role}'.
            
            Path: {folder_path}
            Past Outcome: {outcome_text}
            
            STRATEGIC ADVICE REQUEST:
            - If the past outcome was POSITIVE (Interview), checking the resume at '{resume_path}' might reveal reusable keywords or phrasing.
            - If the past outcome was NEGATIVE (Reject), analyze the outcome text above to avoid the same mistake.
            """
            
        return lesson_context

    def think(self, jd_text, filename):
        safe_jd = self.shield.sanitize(jd_text)
        
        # 1. RAG: 找我的相關經驗
        retrieved_knowledge, sources = self.retrieve_context(safe_jd)
        source_msg = ', '.join(sources) if sources else "None"

        # 2. History RAG: 找類似的戰役
        history_insight = self.recall_past_lessons(jd_text)

        # 3. [修正] Prompt 強化：讀取外部 AboutMe，並整合 Agent 3/4
        prompt = f"""
            You are the **Chief Career Strategist** for user.
            Your goal is not just to "match" keywords, but to calculate the **Return on Investment (ROI)** of applying to this specific job.

            ### 📂 INTELLIGENCE BRIEFING
            1. **CANDIDATE PROFILE (RAG Context)**:
            {retrieved_knowledge}

            2. **CORE VALUES & CONSTRAINTS (AboutMe)**:
            {self.user_values}

            3. **TARGET (JD)**:
            {safe_jd}

            4. **WAR ROOM ARCHIVE (Past Battle Data)**:
            {history_insight}

            ---

            ### ⚔️ MISSION OBJECTIVES
            Perform a deep strategic analysis using the following modules. Be **critical, concise, and direct**.

            #### 🔍 MODULE 1: REALITY CHECK (The Gatekeeper)
            - Identify the **Requirements** and **preference** from the JD.
            - For each, provide a **Verdict**: [✅ STRONG MATCH] / [⚠️ BRIDGING NEEDED] / [❌ CRITICAL GAP].
            - **CRITICAL:** If there is a [❌ CRITICAL GAP], propose a **"Pivot Strategy"**: How can he use his past work to distract/compensate for this missing skill?

            #### 🛡️ MODULE 2: RISK RADAR (The Cynic)
            - **Financial/Visa Trap**: Based on his "Green/Red Zone" preferences, is this job in a tax-heavy region (e.g., Netherlands Box 3) or visa-unfriendly?
            - **R&D vs. Ops Balance**: The candidate is research-oriented. Does this JD look like a pure "Ops/Support/Maintenance" role with zero innovation?
            - ⚠️ **Warning**: If the JD emphasizes "24/7 support", "legacy migration", or "ticket handling" over "model development" or "experimentation".

            #### ♟️ MODULE 3: THE BATTLE PLAN (The Strategist)
            - **HISTORY INTEL**: Analyze the `WAR ROOM ARCHIVE`.
                - If we applied to a similar role/company before and *failed*, explicitly state: **"⚠️ WARNING: Last time at [Company], we failed due to [Reason]. Do NOT repeat [Action]."**
                - If we had success/interviews, state: **"✅ BLUEPRINT: Reuse the [Specific Story] from the [Company] application."**
            - **The "Hook"**: Draft **ONE** killer sentence for the Cover Letter opening that connects his "Lab-to-Street" philosophy directly to their company mission.

            ---

            ### 📊 OUTPUT FORMAT (Strict JSON)
            Generate a JSON object inside ```json``` tags. Do not output any text outside the tags.

            {{
            "company_name": "Extract from JD",
            "role_name": "Extract from JD",
            "match_score": (Integer 0-100, be strict. Deduct for Visa risks.),
            "risk_level": "Low" | "Medium" | "High",
            "salary_potential": "Unknown" | "High" | "Low" (Guess based on location/tier),
            "visa_friendly": true | false (Infer from context),
            "critical_gaps": ["List top gaps"],
            "strategic_advice": "One sentence summary of whether to apply and how.",
            "history_alert": "None" | "Specific warning from War Room"
            }}
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
        text = gemini_ocr(filepath, model_name=MODEL_NAME)
        
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