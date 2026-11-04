# AI Study Buddy

Streamlit app: sign up / log in, upload notes (PDF, DOCX, PPTX, TXT), AI study chat,
MCQ quizzes with scores, and summaries.

## Run locally
```
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then add your key
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repository (`.gitignore` already keeps secrets and the database out).
2. Go to share.streamlit.io -> Create app -> choose the repo, branch `main`, main file `app.py`.
3. Advanced settings -> Secrets: paste `ANTHROPIC_API_KEY = "your-key"`.
4. Deploy.

## Important
Streamlit Cloud storage is temporary: the SQLite file (users, documents) resets when the
app restarts or redeploys. For permanent data, move the database to Supabase/Postgres or Turso.
