# ⚡ Ohio Energy Tracker

An autonomous data pipeline and interactive dashboard for tracking retail natural gas and electricity rates across Ohio. This project scrapes the official **Energy Choice Ohio** "Apples to Apples" marketplace daily to surface the most competitive, consumer-friendly plans.

### 📊 Live Dashboards
*   **[Electric Dashboard](https://humphreysb.github.io/gasAndElectricTicker/electric_dashboard.html)**
*   **[Gas Dashboard](https://humphreysb.github.io/gasAndElectricTicker/gas_dashboard.html)**

---

### 🚀 Key Features
*   **Daily Market Scraping:** Automatically fetches the latest rates for all major Ohio utilities (AEP, Duke, AES, FirstEnergy, Columbia Gas, etc.).
*   **Smart Filtering:** Unlike the raw marketplace, we filter for "Fair Terms" by default:
    *   **Fixed Rates Only:** No variable-rate surprises.
    *   **Zero Cancellation Fees:** Freedom to switch if a better rate appears.
    *   **No Monthly Fees:** Transparent "base" pricing.
    *   **6+ Month Terms:** Minimum stability for consumer protection.
    *   **No Intro/Promo Rates:** True long-term pricing, not bait-and-switch offers.
*   **Historical Analysis:** Over 5 years of historical utility benchmarks (PTC/SCO) to help you time your switch.
*   **Savings Calculator:** Plug in your current bill to see exactly how much you would save by switching to today's market leader.
*   **BBB Integration:** Built-in Better Business Bureau ratings to help you choose reputable suppliers.

### 🛠 Tech Stack
*   **Python:** The engine for scraping and data processing.
*   **Pandas & Parquet:** High-performance data storage and manipulation.
*   **Plotly:** Interactive, mobile-responsive data visualizations.
*   **GitHub Actions:** Automated daily execution and deployment to GitHub Pages.

### 📈 How it Works
1.  `energy_scraper.py` runs daily, fetching raw HTML from the PUCO marketplace.
2.  Data is cleaned, normalized, and appended to `allData.parquet`.
3.  `build_dashboard.py` processes the multi-year dataset and generates static HTML dashboards with interactive Plotly charts.
4.  GitHub Pages hosts the resulting dashboard for public access.

---
*Disclaimer: This tool is for informational purposes. Always verify rates on the official provider website before signing a contract.*
