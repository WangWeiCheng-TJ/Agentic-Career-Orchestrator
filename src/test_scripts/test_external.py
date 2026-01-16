import os
import sys
import json
from termcolor import cprint
from dotenv import load_dotenv
import google.generativeai as genai

# --- 設定路徑，確保可以 import src 裡面的模組 ---
# 這樣你不管在根目錄跑還是在 tests 目錄跑都能抓到
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))

from src.agents.jd_parser import JDParserAgent
from src.tools.tool import ToolRegistry

# --- 載入 API Key ---
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-pro")

if not API_KEY:
    cprint("❌ 錯誤: 找不到 GOOGLE_API_KEY，請檢查 .env 檔案", "red")
    sys.exit(1)

genai.configure(api_key=API_KEY)

# --- 模擬一份 JD (這裡用 Anthropic 的真實職缺範例，比較容易搜到東西) ---
SAMPLE_JD_TEXT = """
Company: Anthropic
Role: Research Engineer, Alignment
Location: San Francisco, CA

About Us:
Anthropic is an AI safety and research company. We're working to build reliable, interpretable, and steerable AI systems.

The Role:
We are looking for a Research Engineer to join our Alignment team. You will work on training large language models to be helpful, honest, and harmless.
You will run experiments on our cluster, implement new algorithms, and analyze the results.

Requirements:
- Strong experience with Python and PyTorch.
- Experience training Large Language Models (LLMs) or similar deep learning models.
- Familiarity with Reinforcement Learning from Human Feedback (RLHF).
- Publications in top conferences (NeurIPS, ICML, ICLR) is a plus.
"""

def test_v2_flow():
    cprint("🚀 [TEST] 啟動 V2 Agentic 核心流程測試", "magenta")

    # 1. 初始化模型 (只為了給 Parser 用)
    cprint(f"📦 初始化 Gemini Model ({MODEL_NAME})...", "cyan")
    model = genai.GenerativeModel(MODEL_NAME)

    # 2. 測試 JD Parser
    cprint("\n--- [Step 1] 測試 JD Parser Agent ---", "yellow")
    parser = JDParserAgent(model)
    
    cprint("🤖 正在解析 Sample JD...", "cyan")
    try:
        jd_params = parser.parse(SAMPLE_JD_TEXT)
        cprint(f"✅ 解析成功!", "green")
        print(json.dumps(jd_params, indent=2, ensure_ascii=False))
        
        # 簡單驗證欄位是否存在
        if "company" not in jd_params or "role" not in jd_params:
            cprint("❌ 解析結果缺少關鍵欄位!", "red")
            return
    except Exception as e:
        cprint(f"❌ Parser 發生錯誤: {e}", "red")
        return

    # 3. 測試 Tools (Salary + Arxiv)
    cprint("\n--- [Step 2] 測試 Tool Registry (真實連網) ---", "yellow")
    try:
        tools = ToolRegistry()
        cprint("🌍 正在呼叫外部工具 (DuckDuckGo & ArXiv)...", "cyan")
        
        # 這裡會真的去打 API，所以需要網路
        report = tools.run_tools(jd_params)
        
        cprint(f"✅ 工具執行完畢!", "green")
        cprint("\n⬇️⬇️⬇️ 以下是 Agent 搜集到的真實情報 ⬇️⬇️⬇️", "white")
        print("="*50)
        print(report)
        print("="*50)
        
        # 檢查是否有抓到東西
        if "Salary" in report and "ArXiv" in report:
            cprint("\n🎉 V2 流程測試通過！Parser 與 Tools 串接正常。", "green", attrs=['bold'])
        else:
            cprint("\n⚠️ 警告: 工具回傳內容似乎不完整，請檢查內容。", "yellow")

    except Exception as e:
        cprint(f"❌ Tools 發生錯誤: {e}", "red")

if __name__ == "__main__":
    test_v2_flow()