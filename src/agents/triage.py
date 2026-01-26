import sys
import os
import json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.utils import safe_generate_json

class TriageAgent:
    def __init__(self, model):
        self.model = model
        self.personas = self._load_personas()

    def _load_personas(self):
        # 取得 council_pool.json 的路徑
        path = os.path.join(os.path.dirname(__file__), 'character_setting/personas.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def evaluate(self, dossier: dict, user_profile: str, extra_prompt={}) -> dict:
        # 抓取完整的 JD 內容，避免遺漏底部資訊
        full_jd = dossier.get('raw_content', '')
        
        # 這裡可以加入簡單的清洗 (例如去除多餘換行)，但保留結構
        cleaned_jd = "\n".join([line.strip() for line in full_jd.splitlines() if line.strip()])

        roster_desc = "\n".join([
            f"- {eid} {p.get('role_name', 'Unknown')} (Focus: {p.get('focus_area', 'N/A')})"
            for eid, p in self.personas.items()
        ])

        prompt = f"""
        You are the "Case Officer" for the Expert Council. 
        Analyze the JD and decide if we should summon specific experts from our roster.

        IMPORTANT OUTPUT RULES:
        1. You must provide a `reason` for EVERY expert. 
        2. The `reason` must be a specific sentence explaining the score (e.g., "Candidate's PhD matches the research focus").
        3. Do NOT leave `reason` empty. Do NOT just repeat the tag name.
        4. {extra_prompt}

        ### 1. CANDIDATE PROFILE
        {user_profile}
        
        ### 2. JOB DESCRIPTION
        {cleaned_jd}

        ### 3. THE COUNCIL ROSTER for referrance
        {roster_desc}

        ### YOUR TASK:
        1. Decide PASS/FAIL based on the hard constraints such as Visa.
        2. Write a "Referral Report" for the Council to decide which expert to call: For each expert, with one word note (e.g. relevant, must, irrelvant, helpful) and why.

        ### OUTPUT FORMAT (JSON) (contents are just for reference):
        {{
            "decision": "PASS" or "FAIL",
            "reason": "Overall triage logic.",
            "referral_analysis": {{
                "E1": {{ "relevance": 10, "note": "Mandatory for soft skills check." }},
                "E2": {{ "relevance": 9, "note": "Core tech stack matches candidate's strengths." }},
                "E3": {{ "relevance": 2, "note": "Salary info is vague; minimal strategic ROI input needed." }},
                "E4": {{ "relevance": 0, "note": "Candidate already has local working rights." }},
                ... (continue for all E8)
            }},
            "clustering_specs": {{
                "tech_domain": ["Skill A", "Skill B"],
                "economic_tier": "Tier 1/2/3",
                "location_context": "..."
            }}
        }}
        """

        # 完整的保險絲設定
        default_output = {
            "decision": "PASS",
            "reason": "Defaulting to PASS due to technical error.",
            "referral_analysis": { f"E{i}": {"relevance": 5, "note": "Error recovery"} for i in range(1, 9) },
            "clustering_specs": {
                "tech_domain": [], "economic_tier": "N/A", "location_context": "N/A"
            }
        }

        return safe_generate_json(self.model, prompt, retries=3, default_output=default_output)