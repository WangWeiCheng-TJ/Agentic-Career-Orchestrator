# 概念代碼
class ROIAgent:
    def evaluate(self, user_profile, jd_data, external_intel):
        """
        輸入：你的底線、JD詳情、外部情報(薪水/論文)
        輸出：決策 (MUST_APPLY, BACKUP, IGNORE)
        """
        # ... Prompt Logic ...
        # 1. 檢查 Hard Constraints (地點、簽證) -> 不過直接 Kill
        # 2. 檢查 Soft Constraints (薪水) -> 太低降級為 Backup 或 Ignore
        # 3. 檢查 Tech Fit (ArXiv) -> 有發論文加分 -> Must Apply
        return decision_json