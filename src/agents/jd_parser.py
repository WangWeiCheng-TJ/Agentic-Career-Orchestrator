import json
import re
from termcolor import cprint

class JDParserAgent:
    def __init__(self, model):
        self.model = model

    def parse(self, jd_text: str) -> dict:
        """
        分析 JD 文字，提取出工具需要的參數。
        """
        # 移除 [:3000] 的限制！讓 Gemini 讀整份文件！
        # 就算 JD 有 100 頁 PDF，Gemini 1.5 Pro 也吃得下。
        
        prompt = f"""
        You are a Data Extraction Specialist.
        Extract the following metadata from the Job Description.
        
        RETURN JSON ONLY. No markdown formatting, no code blocks.
        
        Fields:
        1. "role": The exact job title.
        2. "company": The hiring company name.
        3. "location": City/Country (default "US" if not found).
        4. "keywords": A list of 3-5 specific technical keywords for identifying the specific team/lab (e.g., "Large Language Models", "Computer Vision").
        
        JD Text:
        {jd_text}  <-- 這裡是完整的全文
        """

        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            
            # 清理 JSON
            text = re.sub(r"```json", "", text)
            text = re.sub(r"```", "", text).strip()
            
            data = json.loads(text)
            return data
            
        except Exception as e:
            cprint(f"   ⚠️ JD Parser 解析失敗: {e}", "yellow")
            return {
                "role": "Engineer",
                "company": "Unknown Company",
                "location": "Remote",
                "keywords": []
            }