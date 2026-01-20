import os
import json
import hashlib
from termcolor import colored

# 設定 Cache 存檔路徑
CACHE_DIR = "/app/data/cache/council_responses"
os.makedirs(CACHE_DIR, exist_ok=True)

class CouncilCache:
    def __init__(self):
        self.cache_dir = CACHE_DIR

    def _get_hash(self, text):
        """產生內容的唯一指紋 (MD5)"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _get_cache_path(self, jd_text, expert_id, mode):
        """
        Cache Key = Hash(JD) + ExpertID + Mode
        檔名範例: E2_SKILL_7a8b9c...json
        """
        jd_hash = self._get_hash(jd_text)
        filename = f"{expert_id}_{mode}_{jd_hash}.json"
        return os.path.join(self.cache_dir, filename)

    def get(self, jd_text, expert_id, mode):
        """嘗試從記憶讀取"""
        path = self._get_cache_path(jd_text, expert_id, mode)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data
            except:
                return None # 檔案壞掉就當沒看到
        return None

    def save(self, jd_text, expert_id, mode, response_data):
        """存入記憶"""
        path = self._get_cache_path(jd_text, expert_id, mode)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(response_data, f, ensure_ascii=False, indent=2)

# 實例化一個全域物件方便匯入
council_memory = CouncilCache()