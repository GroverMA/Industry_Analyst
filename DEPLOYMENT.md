# Streamlit Community Cloud Deployment

## Deployment coordinates

- Repository: `GroverMA/industry-analyst-os`
- Branch: `main`
- Entrypoint: `app.py`
- Recommended Python version: `3.12`
- Hosting: Streamlit Community Cloud

## Why this repository is isolated

The application directory is its own Git repository. Files in the surrounding
`PhD Application 2` directory are not part of this repository and must never be
staged or uploaded with the application.

## Secrets

Real HKGAI credentials must not be committed to GitHub. During deployment,
open **Advanced settings → Secrets** and paste the same key names shown in
`.streamlit/secrets.example.toml`, replacing only the placeholder values.

Required secret values:

- `HKGAI_MODEL_API_KEY`
- `HKGAI_APP_NAME`
- `HKGAI_APP_KEY`

The public service URLs and timeout values are included in the example so the
deployed configuration remains explicit and reproducible.

## Community Cloud steps

1. Open `https://share.streamlit.io/` and authenticate with the GitHub account
   that owns the repository.
2. Select **Create app** and **Yup, I have an app**.
3. Choose repository `GroverMA/industry-analyst-os`, branch `main`, and file
   path `app.py`.
4. Open **Advanced settings**.
5. Select Python `3.12`.
6. Paste the secrets with real values.
7. Deploy and wait for the health check to finish.

## Post-deployment smoke test

1. Load the case demonstration and confirm the Project Home renders.
2. Create one unrelated-industry General Research project to prove the product
   is not hard-coded to molecular diagnostics.
3. Run **AI分析研究需求并生成市场描述** to verify Modelhub.
4. Confirm Gate 0 and execute one web-research task to verify Agenthub search
   and crawl.
5. Reload the page and confirm the app still starts cleanly.

## Update behavior

Streamlit Community Cloud watches the selected GitHub branch. A later push to
`main` triggers an application update; dependency changes in
`requirements.txt` trigger a full dependency rebuild.
