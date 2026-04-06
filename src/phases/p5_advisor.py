import json
import os
import glob
from termcolor import colored, cprint
from dotenv import load_dotenv
import re
import sys

# === 路徑設定 ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))) 
sys.path.append(os.path.abspath(".")) 

# === IMPORTS ===
from src.tools.model_gateway import SmartModelGateway
from src.tools.db_connector import db_connector 
from src.tools.data_manager import JobDataManager
from src.agents.character_setting.prompt_loader import PromptFactory

load_dotenv()

# 路徑設定
DIR_P3_INPUT = "/app/data/processed/pending_council"
DIR_P4_INPUT = "/app/data/processed/battle_plan/final_battle_plan.json"
DIR_OUTPUT = "/app/data/processed/editor_reports"
os.makedirs(DIR_OUTPUT, exist_ok=True)
EDITOR_REUSE = os.getenv("EDITOR_REUSE")

class WarRoomEditor:
    def __init__(self):
        self.battle_plan = []
        self.resume_content = ""
        
        # 初始化元件
        self.gateway = SmartModelGateway(os.environ.get("GOOGLE_API_KEY"))
        self.db_connector = db_connector # 假設這裡不需要參數，依你的實作調整

        # [新增] 初始化 DataManager
        self.data_manager = JobDataManager(DIR_P3_INPUT)
        self.prompt_manager = PromptFactory(root_dir=os.path.abspath("src/agents"))
        # self.prompt_manager = factory.create_editor_prompt()

    def load_resources(self):
        # 1. Load Battle Plan (P4)
        if not os.path.exists(DIR_P4_INPUT):
            cprint("❌ No Battle Plan found. Run P4 first.", "red")
            return False
        with open(DIR_P4_INPUT, 'r', encoding='utf-8') as f:
            self.battle_plan = json.load(f)

        # 2. Load Resume from DB (P2 已經建立好的 Context)
        cprint("📥 Fetching Resume Context from Database...", "cyan")
        try:
            # 這裡直接呼叫你在 P2 用過的方法
            self.resume_content = self.db_connector.get_resume_bullets_context()
            
            if not self.resume_content or len(self.resume_content) < 50:
                cprint("⚠️ Warning: Resume content from DB seems empty!", "yellow")
        except Exception as e:
            cprint(f"❌ DB Error: {e}", "red")
            self.resume_content = "[ERROR LOADING RESUME DB]"
            return False

        # === [NEW] 3. Load User Profile ===
        cprint("📥 Fetching User Profile...", "cyan")
        try:
            # 使用 db_connector 的 fallback 邏輯 (manual → auto → ChromaDB)
            self.user_profile = self.db_connector.get_user_profile()
            
            if not self.user_profile or self.user_profile == "{}":
                cprint("⚠️ Warning: User profile is empty!", "yellow")
        except Exception as e:
            cprint(f"⚠️ User Profile Error: {e}", "yellow")
            self.user_profile = "{}"
            
        return True

    def generate_briefing(self):
        """Step 1: 閱兵"""
        cprint("\n📊 STRATEGIC BRIEFING", "white", attrs=['bold', 'reverse'])
        
        clusters = self.battle_plan
        # 兼容性處理
        if isinstance(self.battle_plan, dict) and "valid_clusters" in self.battle_plan:
             # 這裡假設 P4 格式，需根據實際情況調整，這裡先假設是 list
             pass 

        valid_clusters = [c for c in clusters if c.get('cluster_id') != -1]
        
        for idx, c in enumerate(valid_clusters):
            cid = c['cluster_id']
            flavor = ", ".join(c.get('flavors', [])[:5])
            gaps = ", ".join(c.get('common_gaps', [])[:5])
            print(f"\n[{idx}] Cluster {cid} | Size: {c['size']} | ROI: {c['roi_score']}")
            print(f"    🎯 Theme: {flavor}")
            print(f"    ⚠️  Main Gaps: {gaps}")
            print("   --------------🏢 Targets--------------")

            for job in c['jobs'][:5]:

                print(f"   - {job['basic_info']['company']}: {job['basic_info']['role']} (Cost: {job['effort_cost']})")

            if len(c['jobs']) > 5: print(f"     ... {len(c['jobs'])-5} more")
            
        return valid_clusters

    # def _get_expert_voices(self, p3_data):
    #     """提取 P3 專家的 Must Have 要求"""
    #     council = p3_data.get('expert_council', {})
    #     voices = []
    #     for expert_id, data in council.get('skill_analysis', {}).items():
    #         must_haves = [s['topic'] for s in data.get('required_skills', []) if s['priority'] == 'MUST_HAVE']
    #         if must_haves:
    #             voices.append(f"- **{expert_id}** demands: {', '.join(must_haves)}")
    #     return "\n".join(voices)

    def _prepare_council_opinions(self, p3_data):
        """
        將 P3 JSON 資料轉換成 Jinja2 模板看得懂的 List 結構
        """
        council = p3_data.get('expert_council', {})
        opinions = []
        
        # 遍歷 skill_analysis (或是 gap_analysis，看你想呈現什麼)
        for expert_id, data in council.get('skill_analysis', {}).items():
            # 抓出該專家堅持的 Must Haves
            must_haves = [s['topic'] for s in data.get('required_skills', []) if s['priority'] == 'MUST_HAVE']
            
            if must_haves:
                opinions.append({
                    "role_name": expert_id.split('_')[0], # 簡單處理名稱
                    "expert_id": expert_id,
                    "must_haves": must_haves # 這是一個 list ["Python", "K8s"]
                })
                
        return opinions

    def _render_editor_report(self, company, role, items):
        """產生 Markdown 表格"""
        md = [
            f"# 📝 Tactical Execution Plan: {company}", 
            f"**Role:** {role}",
            f"**Generated by:** War Room Editor",
            "\n---",
            "| # | Topic | Action | Content / Instruction | Note |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]
        
        # 解析 items
        for item in items:
            i_id = item.get('ID', '-')
            topic = item.get('TOPIC', '')
            source = item.get('SOURCE', 'UNKNOWN').upper()
            content = item.get('CONTENT', '').replace('\n', ' ')
            note = item.get('NOTE', '')
            
            # Visual Candy
            if "REUSE" in source: icon = "✅ REUSE"
            elif "TWEAK" in source: icon = "🔧 TWEAK"
            elif "NEW" in source: icon = "✨ NEW"
            elif "COVER" in source: icon = "✉️ LETTER"
            else: icon = f"❓ {source}"
            
            md.append(f"| {i_id} | {topic} | {icon} | {content} | {note} |")
            
        return "\n".join(md)

    # 新增 helper function: 把 P3 資料轉成 List
    def _prepare_council_opinions(self, p3_data):
        council = p3_data.get('expert_council', {})
        opinions = []
        for expert_id, data in council.get('skill_analysis', {}).items():
            must_haves = [s['topic'] for s in data.get('required_skills', []) if s['priority'] == 'MUST_HAVE']
            if must_haves:
                opinions.append({
                    "role_name": expert_id.split('_')[0], 
                    "expert_id": expert_id,
                    "must_haves": must_haves
                })
        return opinions

    def _process_single_job(self, job):
        jid = job['id'] 
        
        # 1. 先讀取資料 (為了拿到 Company Name 來組檔名)
        p3_data = self.data_manager.load_job_data(jid)
        if not p3_data:
            cprint(f"⚠️ P3 data missing for ID: {jid}, skipping.", "red")
            return

        company = p3_data['basic_info']['company']
        role = p3_data['basic_info']['role']

        # 2. [REUSE Logic] 提早計算輸出檔名
        # 必須跟最後存檔的邏輯完全一致，才能正確比對
        safe_comp = "".join([c for c in company if c.isalnum() or c in (' ','-')]).strip().replace(' ', '_')
        fname = f"Plan_{safe_comp}_{jid[:6]}.md"
        output_path = os.path.join(DIR_OUTPUT, fname)

        # 3. [Check] 檢查檔案是否存在
        if os.path.exists(output_path):
            # 如果存在，印個灰色的字跳過，不呼叫 LLM
            cprint(f"  ⏭️  Skipping {company} (File exists: {fname})", "dark_grey")
            return 
        
        # ==========================================
        # 只有檔案不存在時，才會執行以下昂貴的操作
        # ==========================================

        # 4. 準備 Prompt 變數
        council_opinions = self._prepare_council_opinions(p3_data)
        
        # 5. 渲染 Prompt
        # cprint(f"  📜 Loading Prompt Template...", "cyan") # 這行太吵可以拿掉
        prompt = self.prompt_manager.create_editor_prompt(
            council_opinions=council_opinions,
            user_profile=self.user_profile,
            context_data={
                "company": company,
                "role": role,
                "resume_text": self.resume_content
            }
        )
        
        # 6. 呼叫 Gateway (燒錢的地方)
        cprint(f"  ✍️  Drafting plan for {company}...", "yellow")
        response = self.gateway.generate(prompt, use_gemma=True)
        
        # 7. 解析與存檔
        items = response.get('editor_plan', [])
        # Fallback 邏輯...
        if not items and isinstance(response, dict): items = response.get('strategic_advice', [])
        if not items and isinstance(response, list): items = response
        
        report = self._render_editor_report(company, role, items)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
            
        cprint(f"  ✅ Saved: {fname}", "green")
        
    def run_editor_session(self, selection):
        """
        :param selection: 可能是整數 index (e.g., 1) 或是字串 'all'
        """
        # 1. 取得所有可用的 Clusters (這裡已經過濾掉 -1 noise 了)
        valid_clusters = self.generate_briefing()
        
        # 2. 決定要跑哪些 Cluster
        # [核心邏輯] 建立 target_clusters 列表
        target_clusters = []
        
        if str(selection).lower() in ['all', 'a']:
            # 如果是全選，直接把整個 List 拿來用
            # 完全不需要 numpy，Python list 本身就是可迭代的
            target_clusters = valid_clusters
            cprint(f"\n🔥 BATCH MODE: Processing ALL {len(target_clusters)} clusters...", "magenta", attrs=['bold'])
        else:
            # 如果是單選，轉成 int 並檢查範圍
            try:
                idx = int(selection)
                if 0 <= idx < len(valid_clusters):
                    # 把單一物件放進 list，這樣下面可以用同一套 for loop 處理
                    target_clusters = [valid_clusters[idx]]
                else:
                    cprint("❌ Index out of bounds.", "red")
                    return
            except ValueError:
                cprint("❌ Invalid input. Enter a number or 'all'.", "red")
                return

        # 3. 統一迴圈處理 (不管是一個還是一百個，邏輯都一樣)
        for cluster in target_clusters:
            # 顯示當前進度
            cid = cluster['cluster_id']
            cprint(f"\n👉 Processing Cluster {cid}...", "cyan")
            
            # --- 以下是你原本的處理邏輯 (找工作 -> 找 P3 -> 生成 Prompt) ---
            target_jobs = cluster['jobs'] # 每個 Cluster 取前 3 高分
            
            for job in target_jobs:
                self._process_single_job(job)
                

    def execute(self):
        if not self.load_resources(): return
        
        # 這裡不需要先 generate_briefing，因為 run_editor_session 裡面會 call
        # 但為了讓使用者先看盤再選，我們先 call 一次顯示給他看
        self.generate_briefing()
        
        while True:
            # 提示使用者可以輸入 'all'
            sel = input("\nSelect Cluster ID (0-N) or 'all' to batch run (q to quit): ")
            if sel.lower() == 'q': 
                break
            
            try:
                self.run_editor_session(sel)
            except ValueError:
                print("Invalid input.")

if __name__ == "__main__":
    WarRoomEditor().execute()