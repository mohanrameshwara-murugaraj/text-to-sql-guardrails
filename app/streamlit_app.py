"""Local Streamlit UI. Start API separately on localhost:8000."""
import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("TEXT_TO_SQL_API_URL", "http://127.0.0.1:8000/v1/query")

st.set_page_config(page_title="Safe Text-to-SQL", page_icon="🔎", layout="wide")
st.title("Safe Text-to-SQL")
st.caption("Local Ollama + DuckDB · SQL guardrails · heuristic answer checks")
st.info("This is a local educational demo. Validation scores are not probabilities of correctness.")

with st.form("query"):
    question = st.text_input("Ask a business question", placeholder="How many customers are in each region?", max_chars=500)
    submitted = st.form_submit_button("Generate and run SQL", type="primary")

if submitted:
    if len(question.strip()) < 3:
        st.warning("Enter a question of at least three characters.")
    else:
        try:
            with st.spinner("Generating SQL with Ollama and checking the result..."):
                response = requests.post(API_URL, json={"question": question}, timeout=120)
                response.raise_for_status()
                payload = response.json()
        except requests.RequestException as exc:
            st.error("Cannot reach the local API. Check that uvicorn is running on 127.0.0.1:8000.")
            st.caption(type(exc).__name__)
        except ValueError:
            st.error("The API returned invalid JSON.")
        else:
            st.subheader("Response")
            status = payload.get("status", "unknown")
            st.write(f"**Status:** {status}")
            st.write(payload.get("message", ""))
            if payload.get("options"):
                st.write("**Clarification options:**", payload["options"])
            if payload.get("sql"):
                st.subheader("Generated SQL")
                st.code(payload["sql"], language="sql")
            if payload.get("explanation"):
                st.write("**LLM explanation:**", payload["explanation"])
            result = payload.get("result")
            if result:
                st.subheader("Query results")
                st.dataframe(pd.DataFrame(result["rows"], columns=result["columns"]), use_container_width=True)
                st.caption(f"{result['row_count']} rows · {result['execution_ms']} ms (local execution)")
            validation = payload.get("validation")
            if validation:
                st.subheader("Validation signals")
                st.write(f"**Status:** {validation['status']}")
                if validation.get("score") is not None:
                    st.metric("Heuristic score (not a correctness probability)", f"{validation['score']}/100")
                for check in validation.get("checks", []):
                    signal = "PASS" if check["passed"] is True else "FAIL" if check["passed"] is False else "UNKNOWN"
                    st.write(f"**{signal} — {check['name']}:** {check['description']}")
                for warning in validation.get("warnings", []):
                    st.warning(warning)
            if status == "executed":
                st.caption("Executed under the local SQL policy. Business correctness is not independently guaranteed.")
