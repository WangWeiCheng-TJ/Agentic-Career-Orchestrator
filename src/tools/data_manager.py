import os
import glob
import json
import re
from termcolor import cprint

class JobDataManager:
    def __init__(self, data_dir):
        """
        :param data_dir: P3 處理完的資料夾路徑 (e.g., /app/data/processed/pending_council)
        """
        self.data_dir = data_dir
        self.id_map = {}
        self.is_indexed = False

    def _build_index(self):
        """掃描資料夾，建立 ID -> FilePath 的對照表"""
        if self.is_indexed: return

        # cprint(f"📇 Indexing Job Dossiers in {self.data_dir}...", "cyan")
        all_files = glob.glob(os.path.join(self.data_dir, "*.json"))
        
        count = 0
        for fpath in all_files:
            try:
                # 為了效能，我們只讀取並解析 JSON，不做複雜運算
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # 1. 抓取 P1 產生的標準 ID
                job_id = data.get('id')
                
                # 2. 建立索引
                if job_id:
                    self.id_map[job_id] = fpath
                    count += 1
                
                # (Optional) 也可以同時用 company_role 當作副索引，如果你需要的話
                
            except Exception:
                continue
        
        self.is_indexed = True
        # cprint(f"✅ Indexed {count} dossiers.", "green")

    def get_file_path(self, job_id):
        """
        根據 ID 獲取檔案路徑 (含模糊比對邏輯)
        """
        self._build_index()

        # 1. 精確比對 (Exact Match)
        if job_id in self.id_map:
            return self.id_map[job_id]

        # 2. 模糊比對 (Fuzzy Match for Trailing Underscores/Suffixes)
        # 解決 P4 可能產生的 "job_123_" vs P3 "job_123" 問題
        clean_target = job_id.strip('_')
        
        for stored_id, path in self.id_map.items():
            if stored_id.strip('_') == clean_target:
                return path
            
            # 3. 甚至更寬鬆：只要 ID 包含在對方裡面 (針對檔名截斷問題)
            if clean_target in stored_id or stored_id in clean_target:
                return path

        return None

    def load_job_data(self, job_id):
        """直接回傳 JSON Data"""
        fpath = self.get_file_path(job_id)
        if not fpath: return None
        
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            cprint(f"❌ Error reading {fpath}: {e}", "red")
            return None