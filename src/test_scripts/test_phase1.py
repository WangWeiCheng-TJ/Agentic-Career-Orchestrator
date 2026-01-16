from ..tools.mock_tools import ToolRegistry

def test_intelligence_gathering():
    # 模擬從 JD 解析出來的資料
    test_cases = [
        {
            "role": "Senior Research Scientist", 
            "company": "Google DeepMind", 
            "location": "London"
        },
        {
            "role": "Backend Engineer", 
            "company": "Generic Bank Corp", 
            "location": "New York"
        }
    ]

    registry = ToolRegistry()

    print("=== Testing Phase 1: Tool Use ===\n")

    for i, case in enumerate(test_cases):
        print(f"--- Case {i+1}: {case['company']} ---")
        
        # 這就是 Agent 之後會呼叫的方法
        report = registry.run_tools(case)
        
        print(report)
        print("\n")

if __name__ == "__main__":
    test_intelligence_gathering()