# MarketLens 4C

This is a simple Streamlit dashboard to experiment with market research data.

## Features
* Upload a CSV file or use the sample dataset `sample_data.csv`.
* Explore four perspectives: Category, Company, Competitor, and Consumer.
* Basic charts and tables using Streamlit.
* Optional web search powered by the DuckDuckGo API.
* When selecting a company, the app automatically retrieves a summary from Wikipedia and lists related links.

## Running
Install the requirements and launch the app **using Streamlit**. Running the
file directly with `python` will raise an error. Execute the command from the
repository root so the sample dataset can be found:
```bash
pip install streamlit pandas requests
streamlit run marketlens_app.py
```

Use the sidebar to upload your own CSV file or search the web for additional
data points using DuckDuckGo.
