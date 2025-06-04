# MarketLens 4C

This is a simple Streamlit dashboard to experiment with market research data.

## Features
* Upload a CSV file or use the sample dataset `sample_data.csv`.
* Explore four perspectives: Category, Company, Competitor, and Consumer.
* Basic charts and tables using Streamlit.
* Optional web search powered by the DuckDuckGo API.

## Running
Install the requirements and launch the app. The command must be run with
`streamlit` so that page configuration works correctly:
```bash
pip install streamlit pandas requests
streamlit run marketlens_app.py
```

Use the sidebar to upload your own CSV file or search the web for additional
data points using DuckDuckGo.
