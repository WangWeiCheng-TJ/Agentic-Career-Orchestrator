# Base Image: Python 3.10 Slim (輕量、穩定)
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統層級依賴 (如果未來需要編譯 C++ 擴充套件如 llama-cpp-python 可解開註解)
# RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# 複製依賴清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 這裡不 COPY src code，因為我們會用 Volume 掛載，方便開發時即時修改
# 僅在 Production Build 時才需要 COPY . .

# 設定環境變數，確保 Python 輸出不被緩衝 (即時看到 Log)
ENV PYTHONUNBUFFERED=1

# 預設執行指令 (保持容器運行，讓我們可以 exec 進去，或直接跑 main.py)
CMD ["python", "src/main.py"]