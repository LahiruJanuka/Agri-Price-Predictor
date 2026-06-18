# 🌾 Govi Gnana (ගොවි ඥාන)

AI-powered crop price forecasting and market insights platform for Sri Lankan agricultural markets.

**Live Demo:** https://govi-gnana.streamlit.app/

---

## Overview

Govi Gnana (ගොවි ඥාන) is a multi-agent AI application that analyzes historical agricultural market prices and generates crop price forecasts and market insights for Sri Lanka.

The project combines automated data collection, PDF data extraction, time-series analysis, and AI agents orchestrated with LangGraph to help users better understand agricultural market trends.

The inspiration behind this project comes from my hometown, Dambulla, where agriculture and wholesale markets play a significant role in everyday life. After learning about AI Agents and LangGraph, I wanted to apply these technologies to a real-world problem that directly connects to the agricultural community.

---

## Features

* 📈 Crop price forecasting
* 🤖 Multi-agent AI workflow using LangGraph
* 📊 Historical trend analysis and visualization
* 🔄 Automated daily data collection
* 📄 PDF table extraction and processing
* 🌐 Interactive Streamlit dashboard
* ⚡ Fast AI inference using Groq
* 🚀 Fully automated deployment pipeline

---

## Data Source

This project uses publicly available market price reports published by the Central Bank of Sri Lanka (CBSL).

Source:
https://www.cbsl.gov.lk/en/statistics/economic-indicators/price-report

The reports contain wholesale and retail commodity prices collected from major economic centers across Sri Lanka.

---

## Tech Stack

### AI & Agents

* LangGraph
* Groq API
* GPT-OSS-120B

### Data Processing

* Pandas
* NumPy

### Data Collection

* BeautifulSoup
* Requests
* Camelot

### Visualization

* Plotly

### Frontend

* Streamlit

### Automation & DevOps

* GitHub Actions
* Streamlit Community Cloud

---

## System Workflow

```text
CBSL Price Reports
        │
        ▼
 Automated Scraper
 (BeautifulSoup)
        │
        ▼
 PDF Download
        │
        ▼
 Table Extraction
   (Camelot)
        │
        ▼
 Data Cleaning
   (Pandas)
        │
        ▼
 Historical Dataset
        │
        ▼
 LangGraph Multi-Agent Pipeline
        │
 ┌──────┼────────┐
 ▼      ▼        ▼
Data  Analysis  Prediction
Agent  Agent     Agent
 └──────┼────────┘
        ▼
 Market Insights
 & Forecasts
        │
        ▼
 Streamlit Dashboard
```

---

## Automation Pipeline

The entire data ingestion process is automated.

1. GitHub Actions runs on a schedule.
2. Latest CBSL reports are downloaded automatically.
3. PDF tables are extracted and converted into structured datasets.
4. Processed data is committed back to the repository.
5. Streamlit Community Cloud automatically redeploys the application.

This enables continuous updates without manual intervention.

---

## What I Learned

Building this project helped me gain practical experience in:

* Multi-agent AI system design with LangGraph
* Agent orchestration and state management
* Real-world PDF data extraction challenges
* Automated data engineering workflows
* CI/CD automation with GitHub Actions
* Cloud deployment using Streamlit
* Building end-to-end AI applications

---

## Installation

Clone the repository:

```bash
git clone https://github.com/LahiruJanuka/Agri-Price-Predictor.git
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the environment:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure environment variables:

```env
GROQ_API_KEY=your_api_key
```

Run the application:

```bash
streamlit run app.py
```

---

## Project Status

This project is currently being developed as a personal educational project focused on learning:

* AI Agents
* LangGraph
* Data Engineering
* Automation
* Production-ready AI workflows

Forecasts and insights should be considered experimental and are not intended for commercial or financial decision-making.

---

## Feedback

Suggestions, issues, and contributions are welcome.

If you find the project useful or have ideas for improvement, feel free to open an issue or submit a pull request.

---

