# src/tools/arxiv_tool.py
# src/tools/arxiv_tool.py
import arxiv

class ArxivTool:
    def __init__(self):
        self.client = arxiv.Client()

    def search_papers(self, company: str, keywords: list) -> str:
        """
        搜尋特定公司 + 關鍵字的論文。
        keywords: ['LLM', 'Agents', 'Synthetic Data']
        """
        if not keywords:
            search_query = f'all:"{company}"'
        else:
            # 構造 Query: all:"Google" AND (all:"LLM" OR all:"Agents")
            # 注意：ArXiv 的搜尋語法比較嚴格，要用括號包好
            or_part = " OR ".join([f'all:"{k}"' for k in keywords])
            search_query = f'all:"{company}" AND ({or_part})'

        print(f"🔎 ArXiv Tool Searching Query: {search_query}")

        search = arxiv.Search(
            query=search_query,
            max_results=3,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )

        results = []
        try:
            for r in self.client.results(search):
                # 清理換行，保持整潔
                summary = r.summary.replace("\n", " ")[:200] + "..."
                results.append(
                    f"- **{r.title}** ({r.published.strftime('%Y-%m')})\n"
                    f"  Link: {r.pdf_url}\n"
                    f"  Summary: {summary}"
                )
        except Exception as e:
            return f"ArXiv search error: {e}"

        if not results:
            return f"No recent papers found for {company} with keywords {keywords}."

        return "\n".join(results)

# 簡單測試用
if __name__ == "__main__":
    tool = ArxivTool()
    # 測試搜尋 Google 的 Gemini 相關論文
    print(tool.search_papers('all:"Google DeepMind" AND "LLM"'))