import sys
import os

# 確保引用路徑正確
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.utils import safe_generate_json

class JDParserAgent:
    def __init__(self, model):
        self.model = model

    def parse(self, jd_text: str, filename: str = "Unknown") -> dict:
        """
        Phase 1 Scout 的核心大腦。
        負責從雜亂的 JD 文字中，提取出結構化的情報。
        """
        
        # 定義我們要提取的資料結構
        prompt = f"""
        You are an elite Headhunter and Resume Strategist.
        Analyze the following Job Description (JD) to extract critical intelligence.
        
        Source File: {filename}
        
        ### JD CONTENT (Truncated):
        {jd_text[:15000]} 
        
        ### EXTRACTION TASKS
        1. **Basic Info**: Extract Role, Company, Location.
        2. **Experience Level**: Classify the seniority of the role based on Title and Years of Experience.
           - **STRICT BUCKETS**: "Intern", "Junior" (0-2y), "Mid" (2-5y), "Senior" (5-8y), "Staff/Lead" (8y+), "Principal/Executive".
           - *Note: If the title contains 'Staff', 'Principal', or 'Director', classify accordingly.*
        3. **Salary Context**: Does it mention a salary range? (Extract raw text or null).
        4. **Key Tech Stack**: List top 5-7 hard skills (e.g., "PyTorch", "Kubernetes").
        5. **Search Keywords**: Generate 3 specific keywords to search for recent papers/news (e.g., "Generative AI", "Edge Computing").
        6. **Domain Label**: Classify into one bucket (e.g., "CV", "NLP", "Infra", "Backend").
        
        ### OUTPUT JSON FORMAT ONLY
        {{
            "role": "Senior Computer Vision Engineer",
            "company": "NVIDIA",
            "location": "Santa Clara, CA (or Remote)",
            "experience_level": "Senior", 
            "salary_raw": "$180k - $250k" or null,
            "tech_stack": ["CUDA", "TensorRT", "C++", "Python", "PyTorch"],
            "search_keywords": ["Model Quantization", "Autonomous Driving", "Vision Transformers"],
            "domain": "Computer Vision",
            "summary": "One sentence summary of the role's core responsibility."
        }}
        """

        # 設定預設值 (萬一 LLM 炸開，至少程式不會停)
        default_output = {
            "role": "Unknown Role",
            "company": "Unknown Company",
            "location": "Unknown",
            "experience_level": "Unknown", # [新增] 用於 Phase 2 過濾
            "salary_raw": None,
            "tech_stack": [],
            "search_keywords": [],
            "domain": "General",
            "summary": "Parser failed to extract data."
        }

        # 使用我們寫好的防呆工具
        return safe_generate_json(
            model=self.model,
            prompt=prompt,
            retries=3,
            default_output=default_output
        )