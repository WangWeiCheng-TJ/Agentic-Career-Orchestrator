import os
import glob
from termcolor import cprint
from dotenv import load_dotenv
import google.generativeai as genai
# 引入我們之前寫好的 utils (法醫找檔案)
from utils import identify_application_packet
from main import smart_extract_text, AgentBrain

load_dotenv()

# 設定歷史資料夾路徑 (對應 docker-compose 的 rejected/ongoing 掛載)
HISTORY_REJECTED_PATH = "/app/data/history/rejected"
HISTORY_ONGOING_PATH = "/app/data/history/ongoing"

def review_battle_record():
    cprint("🕯️ 啟動戰史回顧模式 (Post-Mortem Analysis)...", "magenta")
    
    agent = AgentBrain() # 借用 main.py 裡的 Agent 腦袋
    
    # 掃描 Rejected 資料夾
    folders = glob.glob(os.path.join(HISTORY_REJECTED_PATH, "*"))
    cprint(f"\nfind from {folders}", "white")
    
    for folder in folders:
        if not os.path.isdir(folder): continue
        
        folder_name = os.path.basename(folder)
        cprint(f"\n📂 分析案例: {folder_name}", "white")
        
        # 1. 找齊四大件 (JD, Resume, CL, Outcome)
        packet = identify_application_packet(folder)
        
        # 檢查關鍵檔案是否存在
        if not (packet['jd'] and packet['resume'] and packet['outcome']):
            cprint(f"   ⚠️ 資料不全，跳過 (缺 JD, Resume 或 Outcome)", "yellow")
            continue

        # 2. 讀取內容
        jd_text = smart_extract_text(packet['jd'], agent)
        resume_text = smart_extract_text(packet['resume'], agent)
        outcome_text = smart_extract_text(packet['outcome'], agent)
        
        # CL 是選配，有就讀，沒有就空字串
        cl_text = smart_extract_text(packet['cl'], agent) if packet['cl'] else "N/A"

        # 3. 進行死因分析 (這就是你要的邏輯！)
        cprint(f"   🧠 Agent 正在進行四方對比分析...", "cyan")
        
        prompt = f"""
        You are conducting a Post-Mortem Analysis on a failed job application.
        
        DATA PACKAGE:
        1. **TARGET JD**: 
        {jd_text[:2000]}
        
        2. **MY RESUME (Used version)**: 
        {resume_text[:2000]}
        
        3. **MY COVER LETTER**:
        {cl_text[:1000]}
        
        4. **OUTCOME (Rejection)**:
        {outcome_text}
        
        ---
        MISSION:
        Analyze WHY this failed based on the 4 documents above.
        
        1. **Outcome Interpretation**: Is this a generic auto-reject, or a specific skill mismatch? Is it Visa related?
        2. **Resume vs JD Gap**: Did the Resume fail to highlight keywords present in the JD? Which ones?
        3. **Actionable Lesson**: What should I change in my Resume/Strategy for the NEXT similar application?
        
        Output format: Markdown.
        """
        
        response = agent.model.generate_content(prompt)
        
        # 4. 存檔檢討報告
        review_path = os.path.join(folder, "Review_Agent.md")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write(response.text)
            
        cprint(f"   ✅ 檢討報告已寫入: {review_path}", "green")

if __name__ == "__main__":
    review_battle_record()