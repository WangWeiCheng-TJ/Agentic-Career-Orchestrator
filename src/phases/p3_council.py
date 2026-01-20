import os
import glob
import json
import sys
from termcolor import colored, cprint
from tqdm import tqdm
import google.generativeai as genai
from dotenv import load_dotenv

# === 路徑設定 ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))) 
sys.path.append(os.path.abspath(".")) 

# 引入工具
try:
    from src.agents.character_setting.prompt_loader import PromptFactory
    from src.tools.retry import generate_with_retry, validate_council_skill
    
    # [修正] 根據你的指示，cache_manager 現在在 agents 裡
    from src.agents.cache_manager import council_memory 
except ImportError as e:
    cprint(f"❌ Error: Import failed. {e}", "red")
    sys.exit(1)

# === CONFIG ===
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")

DIR_PENDING = "/app/data/processed/pending_council" # 這裡應該是 Phase 2 產出的檔案
DIR_READY = "/app/data/processed/ready_to_apply"

# 除非你要調 Prompt，否則設為 False 以節省金錢
FORCE_REFRESH = True 

# === 關鍵：角色名稱對照表 (Name to ID Mapping) ===
ROLE_NAME_TO_ID = {
    "HR Gatekeeper": "E1",
    "Tech Lead": "E2",
    "Strategist": "E3",
    "Visa Officer": "E4",
    "Academic Reviewer": "E5",
    "Academic": "E5", # 容錯
    "System Architect": "E6",
    "Leadership Scout": "E7",
    "Startup Veteran": "E8"
}

def get_expert_color(eid):
    colors = { "E1": "cyan", "E2": "magenta", "E3": "green", "E4": "red", "E5": "blue", "E6": "yellow", "E7": "white", "E8": "light_green" }
    return colors.get(eid, "white")

def get_target_experts(dossier):
    """
    🕵️‍♂️ 智慧路由：支援兩種格式的輸入
    """
    target_ids = []
    
    # === 模式 A: 讀取 Triage Result (ActiveFence 格式) ===
    # 位置: triage_result -> referral_analysis
    referral = dossier.get('triage_result', {}).get('referral_analysis', {})
    
    if referral and isinstance(referral, dict):
        for eid, data in referral.items():
            if not eid.startswith("E"): continue
            
            score = data.get('relevance', 0)
            note = data.get('note', '').lower()
            
            # [優化邏輯]
            # 1. 強制召喚：標籤是 Must, Important, Relevant (不管分數)
            if note in ['must', 'important', 'relevant']:
                target_ids.append(eid)
                
            # 2. 條件召喚：分數 >= 6 (即使標籤只是 Helpful 或 N/A)
            # 這樣可以過濾掉 E3 (Score 3, Helpful) 和 E7 (Score 5, Helpful) -> 省錢！
            elif score >= 6:
                target_ids.append(eid)
                
        if target_ids:
            return sorted(list(set(target_ids)))

    # === 模式 B: 讀取 Role Name List (Blackshark 格式) ===
    # 位置: council_strategy -> active_experts
    strategy = dossier.get('council_strategy', {})
    active_roles = strategy.get('active_experts', [])
    
    if active_roles and isinstance(active_roles, list):
        for role in active_roles:
            eid = ROLE_NAME_TO_ID.get(role)
            if eid:
                target_ids.append(eid)
        if target_ids:
            return sorted(list(set(target_ids)))

    # === 預設 (Fallback) ===
    return ["E1", "E2"]


def run_phase3_dynamic_execution():
    cprint("\n🏛️  [Phase 3] EXPERT COUNCIL: Dynamic Diagnosis", "magenta", attrs=['bold', 'reverse'])
    
    # 初始化 (省略部分與之前相同...)
    if not API_KEY: return
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    try:
        # PromptFactory 需要「包含 character_setting 的目錄」= src/agents
        # 從本檔 (src/phases/p3_council.py) 往回推，避免依賴 cwd，本地 / Docker 都能用
        _src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pf_root = os.path.join(_src, "agents")
        factory = PromptFactory(root_dir=pf_root)
    except Exception as e:
        cprint(f"❌ Error: {e}", "red"); return

    files = glob.glob(os.path.join(DIR_PENDING, "*.json"))
    pbar = tqdm(files, desc="🧠 Processing Dossiers", unit="job")
    
    for filepath in pbar:
        filename = os.path.basename(filepath)
        target_path = os.path.join(DIR_READY, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            dossier = json.load(f)

        company = dossier.get('basic_info', {}).get('company', 'Unknown')
        raw_jd = dossier.get('raw_content', '')
        
        # === 1. 決定要叫誰 (Router) ===
        # 這裡不再用寫死的 ACTIVE_EXPERTS，而是看這份 JD 需要誰
        target_experts = get_target_experts(dossier)
        
        pbar.set_postfix(company=company[:10], experts=len(target_experts))
        tqdm.write(colored(f"\nTarget: {company}", "white", attrs=['bold']) + 
                   colored(f" | Summoning: {', '.join(target_experts)}", "yellow"))

        context_data = {
            "job_title": dossier.get('basic_info', {}).get('role', ''),
            "company_name": company,
            "raw_jd_text": raw_jd
        }

        expert_results = {}
        
        # === 2. 針對名單上的專家執行分析 (含 Cache) ===
        for eid in target_experts:
            try:
                # [Cache Check]
                cached_data = council_memory.get(raw_jd, eid, "SKILL") # 注意：這裡假設還是在做 Skill 分析
                
                if cached_data and not FORCE_REFRESH:
                    expert_results[eid] = cached_data
                    tqdm.write(colored(f"  🧠 {eid}: Cache Hit", get_expert_color(eid)))
                    continue

                # [LLM Call]
                prompt = factory.create_expert_prompt(eid, "SKILL", context_data)
                result_json = generate_with_retry(
                    model=model, 
                    prompt=prompt, 
                    validator_func=validate_council_skill,
                    max_retries=2
                )
                
                # [Cache Save]
                council_memory.save(raw_jd, eid, "SKILL", result_json)
                expert_results[eid] = result_json
                
                # Visual
                count = len(result_json.get("required_skills", []))
                tqdm.write(colored(f"  👤 {eid}: Analyzed ({count} skills)", get_expert_color(eid)))
            
            except Exception as e:
                tqdm.write(colored(f"  ❌ {eid} Failed: {e}", "red"))

        # === 3. 存檔 ===
        if 'expert_council' not in dossier:
            dossier['expert_council'] = {}
            
        dossier['expert_council']['skill_analysis'] = expert_results
        
        # 這裡示範直接覆蓋原始檔案 (Updating In-Place)，或者存到 DIR_READY
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(dossier, f, indent=2, ensure_ascii=False)

    cprint("\n🎉 Diagnosis Complete.", "green")

if __name__ == "__main__":
    run_phase3_dynamic_execution()