# Local LLM Decision Orchestrator: Job Hunting Season

> **Status:** MVP Validated (Local Execution) <br>
> **Role:** Research Pilot for [Physically-Aware Synthetic Surveillance Data]

## 🎯 Motivation
The primary motivation behind this project is to address the inefficiency of manually filtering noise from job descriptions in the job market.

In job hunting, one must sift through hundreds of job descriptions to find the few that match complex constraints (e.g., visa rules, tech stack compatibility, remote work policies). Traditional keyword search fails to capture these semantic nuances. For example, a position that requires computer vision experience could drown in the title "Machine Learning Engineer".

This project was built to validate that a **Local LLM Agent** can serve as an intelligent filter and planner, solving this "needle in a haystack" problem while preserving data privacy.

Crucially, this project also serves as the pilot for a research project: **Real-World Data-Driven Synthetic Surveillance Dataset Generation Pipeline**.<br>
By treating video generation models and task-specific LoRAs as "Agents," the future research aims to leverage this same agentic workflow to significantly improve efficiency and reduce computational costs in synthetic data generation.

## 📖 Introduction
This project implements a privacy-first **Local LLM Agent** designed to leverage extensive user context to identify job descriptions that best fit my expertise.

The agents are designed to analyze my full background, not just technical skills but also long-term financial plans and hard constraints like visa sponsorship. They evaluate whether a JD truly meets my needs and extract the most relevant information, enabling me to further evaluate the position and tailor my resume and cover letter accordingly.


## 🏗️ System Architecture

```mermaid
graph TD
    User[User / Researcher] -->|1. Input JD Batch| Agent["Local LLM Agent<br/>(Llama-3 / Mistral)"]
    
    %% 資料庫與設定
    subgraph "Knowledge Base"
        ConstraintDB[("User Profile DB<br/>(Visa, Tax, salary)")]
        MasterCV[("Master CV Database<br/>(Projects & Skills)")]
    end

    %% 第一階段：過濾
    subgraph "Phase 1: Semantic Filtering (Hard Filters)"
        Agent <-->|Query Constraints| ConstraintDB
        Agent -->|Analyze| JDs[("Raw JD Files")]
        Agent -->|Reasoning| Decision{Pass Constraints?}
        Decision -- No --> Trash[Discard]
    end

    %% 第二階段：分析與建議
    subgraph "Phase 2: Contextual Analysis (Soft Matching)"
        Decision -- Yes --> Analyzer[Analysis Skill]
        Analyzer <-->|RAG Retrieval| Database <br>("Research Experience, Projects, Publications")
        Analyzer -->|Map Experience| Context[Structured Insight]
    end

    %% 第三階段：輸出
    subgraph "Phase 3: Output & Review"
        Context -->|Drafting| Writer[Content Generator]
        Writer -->|Output| Report["Analysis Report &<br/>Suggestions"]
        Report -->|Final Check| Human[User Review & Tailor Resume/CV]
    end

    style Agent fill:#e1f5fe,stroke:#01579b,stroke-width:2px,color:#000
    style ConstraintDB fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,color:#000
    style MasterCV fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,color:#000
    style Human fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000
```

## 🚀 Key Features
1.  **Semantic Filtering:**
    * Instead of traditional keyword matching, the agent "reads" JDs to understand nuances (e.g., rejecting positions requiring specific visa sponsorships or deprecated legacy tech).
2.  **Context-Aware Planning (RAG):**
    * Dynamically retrieves the most relevant project experiences from a personal database based on the specific requirements of the target position.
3.  **Local Execution:**
    * Runs entirely on local consumer hardware (NVIDIA Laptop GPU), ensuring sensitive personal data (CVs, personal constraints) never leaves the machine.

## 🛠️ Tech Stack
* **Orchestration:** Python, LangChain / AutoGen
* **Inference Engine:** Ollama / vLLM (Quantized Models)
* **Vector Store:** ChromaDB (for Context Retrieval)
* **Hardware:** Tested on NVIDIA Laptop GPU (RTX 4060)

---
*This project is part of a broader research initiative on Agentic AI workflows for Data Synthesis.*