# MarketLens 4C

This is a simple Streamlit dashboard to experiment with market research data.

## Features
* Upload a CSV file or use the sample dataset `sample_data.csv`.
* Explore four perspectives: Category, Company, Competitor, and Consumer.
* Basic charts and tables using Streamlit.
* Sample dataset uses Vietnamese brand names with a `Group` column for segmentation.
* Filter data by group in the sidebar.
* Optional web search powered by the DuckDuckGo API.
* Google Custom Search integration when API credentials are provided.
* When selecting a company, the app automatically retrieves a summary from Wikipedia and lists related links from the web.
* Search results open in a new browser tab and appear in an expandable section on the dashboard.
* Charts and tables use columns for a more space-efficient layout.

## Running
Install the requirements and launch the app **using Streamlit**. Running the
file directly with `python` will raise an error. Execute the command from the
repository root so the sample dataset can be found:
```bash
pip install streamlit pandas requests
streamlit run marketlens_app.py
```

Use the sidebar to upload your own CSV file or initiate a web search. Matching
results will be displayed in an expandable section of the main page. To enable
Google search results, set the `GOOGLE_API_KEY` and `GOOGLE_CSE_ID` environment
variables with your Custom Search credentials before launching the app.
