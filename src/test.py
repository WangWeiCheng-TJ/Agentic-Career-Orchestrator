import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from termcolor import cprint

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 引用你的 Agent
from agents.jd_parser import JDParserAgent

# 載入設定
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")

# 模擬一段 JD (這是假的，但結構很像真的)
SAMPLE_JD_TEXT = """
Job Title: Senior Machine Learning Engineer
Company: Anthropic
Location: San Francisco, CA (Hybrid)

About the role:
We are looking for a Senior Engineer to join our Alignment team.
You will work on training large language models to be helpful, harmless, and honest.

Requirements:
- 5+ years of experience in Software Engineering.
- Strong proficiency in Python, PyTorch, and JAX.
- Experience with distributed training (Kubernetes, Slurm).
- PhD in Computer Science is preferred but not required.
- Published papers in NeurIPS, ICML is a huge plus.

Compensation:
The expected salary range for this role is $220,000 - $320,000 USD per year plus equity.
"""

def test_parser():
    cprint("🧪 Starting Unit Test for JDParserAgent...", "cyan", attrs=['bold'])

    # 1. 初始化
    if not API_KEY:
        cprint("❌ No API Key found!", "red")
        return
        
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    
    agent = JDParserAgent(model)

    # 2. 執行解析
    cprint("🤖 Sending sample JD to Agent...", "white")
    result = agent.parse(SAMPLE_JD_TEXT, filename="test_dummy.txt")

    # 3. 驗證結果
    cprint("\n📊 Extraction Result:", "yellow")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 4. 自動檢查關鍵欄位 (Assertions)
    cprint("\n🔍 Running Assertions...", "blue")
    
    try:
        assert result["role"] != "Unknown Role", "Role extraction failed"
        assert "Anthropic" in result["company"], "Company extraction failed"
        assert result["experience_level"] in ["Senior", "Staff/Lead"], f"Wrong Level: {result.get('experience_level')}"
        assert "PyTorch" in result["tech_stack"], "Tech stack missing PyTorch"
        assert result["salary_raw"] is not None, "Salary should be detected"
        
        cprint("✅ TEST PASSED: Parser is working correctly!", "green", attrs=['bold'])
        
    except AssertionError as e:
        cprint(f"❌ TEST FAILED: {e}", "red", attrs=['bold'])

if __name__ == "__main__":
    test_parser()