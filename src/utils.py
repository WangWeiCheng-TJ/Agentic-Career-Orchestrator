# src/utils.py
import os
import glob
import re
import time
import json

import google.generativeai as genai 
from termcolor import cprint


def identify_application_packet(folder_path):
    """
    掃描指定資料夾，根據檔名關鍵字識別 JD, CV, Cover Letter 和 Outcome。
    
    Args:
        folder_path (str): 目標資料夾路徑
        
    Returns:
        dict: 包含 'jd', 'resume', 'cl', 'outcome' 路徑的字典
    """
    packet = {
        "jd": None,
        "resume": None,
        "cl": None,
        "outcome": None,
        "folder": folder_path
    }
    
    if not os.path.exists(folder_path):
        return packet

    # 取得所有檔案 (不包含子目錄)
    files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
    
    for f in files:
        fname = f.lower()
        full_path = os.path.join(folder_path, f)
        
        # 1. 識別 JD (優先權：只要有 jd, job 就中)
        if not packet["jd"] and any(x in fname for x in ["jd", "job", "description", "vacancy", "role"]):
            packet["jd"] = full_path
            
        # 2. 識別 Resume/CV
        elif not packet["resume"] and any(x in fname for x in ["resume", "cv", "curriculum"]):
            packet["resume"] = full_path
            
        # 3. 識別 Cover Letter
        elif not packet["cl"] and any(x in fname for x in ["cl", "cover", "letter"]):
            packet["cl"] = full_path
            
        # 4. 識別結果 (Outcome/Status)
        elif not packet["outcome"] and any(x in fname for x in ["outcome", "reject", "decision", "offer", "status", "result"]):
            packet["outcome"] = full_path

    return packet

def list_history_folders(base_path):
    """ 列出該路徑下所有的第一層子資料夾 """
    return [f.path for f in os.scandir(base_path) if f.is_dir()]

# --- [新增] 通用 OCR 工具 ---
def gemini_ocr(filepath, model_name="gemini-1.5-flash"):
    """
    通用 OCR 模組：
    1. 上傳檔案
    2. 等待處理 (Polling)
    3. 呼叫 Vision API 轉文字
    
    預設使用 Flash 模型 (速度快、便宜、Rate Limit 高)
    """
    cprint(f"   👁️ [Utils] 啟動 Cloud OCR: {os.path.basename(filepath)}", "magenta")
    
    try:
        # 1. 上傳
        sample_file = genai.upload_file(path=filepath, display_name="OCR_Target")
        
        # 2. 等待處理
        while sample_file.state.name == "PROCESSING":
            time.sleep(1)
            sample_file = genai.get_file(sample_file.name)
        
        # 3. 生成
        model = genai.GenerativeModel(model_name)
        response = model.generate_content([sample_file, "Extract all text from this document accurately."])
        
        return response.text
    except Exception as e:
        cprint(f"   ❌ OCR 失敗: {e}", "red")
        return None
    
def clean_json_text(text):
    """
    專門用來清洗 LLM 吐回來的 JSON 字串。
    去除 Markdown 標記 (```json ... ```) 和多餘空白。
    """
    # 1. 移除 ```json 和 ``` 標記
    text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```", "", text)
    
    # 2. 有時候 LLM 會在 JSON 前後加廢話，嘗試抓出 { ... } 的部分
    # 簡單的正則表達式尋找最外層的 {}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
        
    return text.strip()

def safe_generate_json(model, prompt, retries=3, delay=20, default_output=None):
    """
    這就是你的「防呆防護罩」。
    
    Args:
        model: Gemini model 物件
        prompt: 提示詞
        retries: 重試次數 (預設 3 次)
        delay: 每次重試中間休息幾秒 (預設 2 秒)
        default_output: 如果全失敗，要回傳什麼預設值 (避免 Crash)
    
    Returns:
        dict: 解析好的 JSON 資料
    """
    for attempt in range(retries):
        try:
            # 1. 發送請求
            response = model.generate_content(prompt)
            
            # 2. 清洗文字
            cleaned_text = clean_json_text(response.text)
            
            # 3. 嘗試解析 JSON
            data = json.loads(cleaned_text)
            return data

        except json.JSONDecodeError as e:
            cprint(f"⚠️ [Attempt {attempt+1}/{retries}] JSON 解析失敗: {e}", "yellow")
            # 這裡可以加一段邏輯：如果解析失敗，再次丟給 LLM 叫它修正格式 (Auto-Repair)
            # 但為了簡單，我們先重試就好
            
        except exceptions.ResourceExhausted:
            cprint(f"⚠️ [Attempt {attempt+1}/{retries}] Rate Limit (429). Cooling down...", "yellow")
            time.sleep(delay * 2 * (attempt + 1)) # 指數退避，越等越久
            continue

        except Exception as e:
            cprint(f"⚠️ [Attempt {attempt+1}/{retries}] API Error: {e}", "yellow")
            
        # 失敗後休息一下再試
        time.sleep(delay)

    # 如果重試次數用完還是失敗
    cprint(f"❌ API Call Failed after {retries} attempts.", "red")
    return default_output if default_output is not None else {}