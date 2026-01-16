import os
import google.generativeai as genai
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

# 1. 載入環境變數
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3-12b-it")
CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "/app/data/chroma_db")

def system_check():
    print("="*40)
    print(f"🚀 系統初始化檢查 (System Check)")
    print(f"🎯 目標模型 (Model): {MODEL_NAME}")
    print(f"💾 資料庫路徑: {CHROMA_PATH}")
    print("="*40)
    
    # --- Check 1: Google Gen AI API ---
    if not API_KEY:
        print("❌ 錯誤: 未檢測到 GOOGLE_API_KEY，請檢查 .env 檔案")
        return

    genai.configure(api_key=API_KEY)

    try:
        print(f">>> 正在呼叫 Google API ({MODEL_NAME})...")
        
        # 使用變數中的模型名稱初始化
        model = genai.GenerativeModel(MODEL_NAME)
        
        # 簡單測試
        response = model.generate_content("Hello! Reply with 'System Online'.")
        print(f"✅ 模型連線成功！回應: {response.text.strip()}")
        
    except Exception as e:
        print(f"❌ 模型連線失敗: {e}")
        print("   (提示: 請檢查 .env 中的 MODEL_NAME 是否正確，Gemma 3 可能需要特定的名稱格式)")

    # --- Check 2: ChromaDB ---
    print(f"\n>>> 正在連接 ChromaDB...")
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        # 隨便 get 一個 collection 測試連線
        collection = client.get_or_create_collection(name="test_connection")
        count = collection.count()
        print(f"✅ ChromaDB 連線成功。現有資料筆數: {count}")
        
    except Exception as e:
        print(f"❌ ChromaDB 錯誤: {e}")

if __name__ == "__main__":
    system_check()