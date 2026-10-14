# Market Research AI Lab

7-agent market research Streamlit demo using Google Gemini.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Render

Deploy branch `market-research-ai-lab` as Python web service (Singapore/free). Build: `pip install -r requirements.txt`. Start: `streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT --server.headless=true`. Set `APP_PASSWORD` and `GEMINI_API_KEY` in Render Environment, never in repo. Use a *new* API key if an earlier key was disclosed.

Google Search grounding may incur charges. Verify source metadata and numbers against original documents. The app provides desk research, not a human primary survey.
