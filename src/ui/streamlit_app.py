"""
DataGenie AI - Streamlit User Interface

Web-based interface for the BI assistant.
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from typing import Dict, Any, Optional

# Page Configuration
st.set_page_config(
    page_title="DataGenie AI",
    page_icon="🧞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
API_URL = "http://localhost:8000"

# Session State
if "query_history" not in st.session_state:
    st.session_state.query_history = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None

# Helper Functions
def check_api_health() -> Dict[str, Any]:
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"status": "unhealthy"}

def process_query(query: str, database: str, use_rag: bool) -> Optional[Dict]:
    try:
        response = requests.post(
            f"{API_URL}/query",
            json={"query": query, "database": database, "use_rag": use_rag},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        st.error(f"API Error: {response.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to API. Start the server with: uvicorn src.api.main:app --reload")
    except Exception as e:
        st.error(f"Error: {str(e)}")
    return None

def get_examples():
    try:
        response = requests.get(f"{API_URL}/examples", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {"examples": ["Show me total revenue", "Top 10 products by sales"]}

# Sidebar
with st.sidebar:
    st.title("🧞 DataGenie AI")
    st.markdown("---")
    
    st.header("⚙️ Settings")
    database = st.selectbox("Database", ["default", "sales_db", "marketing_db"])
    use_rag = st.checkbox("Use RAG Enhancement", value=True)
    
    st.markdown("---")
    
    st.header("🔌 API Status")
    health = check_api_health()
    if health.get("status") == "healthy":
        st.success("✅ Connected")
        llm_status = health.get("llm_status", {})
        ollama_ok = llm_status.get("ollama", {}).get("available", False)
        claude_ok = llm_status.get("claude", {}).get("available", False)
        st.write(f"Ollama: {'✅' if ollama_ok else '❌'} | Claude: {'✅' if claude_ok else '❌'}")
    else:
        st.error("❌ Disconnected")
    
    st.markdown("---")
    
    st.header("💡 Examples")
    examples = get_examples().get("examples", [])
    for ex in examples[:5]:
        if st.button(ex[:35] + "..." if len(ex) > 35 else ex, key=ex):
            st.session_state.query_input = ex

# Main Content
st.title("🧞 DataGenie AI - Intelligent BI Assistant")
st.markdown("Transform natural language into SQL queries")

# Query Input
col1, col2 = st.columns([5, 1])
with col1:
    query = st.text_input(
        "Ask a question about your data",
        value=st.session_state.get("query_input", ""),
        placeholder="e.g., Show me total revenue by region for last quarter"
    )
with col2:
    st.write("")
    submit = st.button("🚀 Generate", type="primary", use_container_width=True)

# Process Query
if submit and query:
    with st.spinner("🧠 Generating SQL..."):
        result = process_query(query, database, use_rag)
        if result:
            st.session_state.current_result = result
            st.session_state.query_history.append({
                "query": query,
                "sql": result["sql"],
                "confidence": result["confidence"]
            })

# Display Results
if st.session_state.current_result:
    result = st.session_state.current_result
    
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Confidence", f"{result['confidence']:.0%}")
    col2.metric("Intent", result['intent']['intent'].replace("_", " ").title())
    col3.metric("Complexity", result['complexity'].title())
    col4.metric("Cost", f"${result['cost_estimate']:.4f}")
    
    st.markdown("---")
    
    # Tabs
    tab1, tab2, tab3 = st.tabs(["📝 SQL", "🔍 Analysis", "📜 History"])
    
    with tab1:
        st.subheader("Generated SQL")
        st.code(result["sql"], language="sql")
        
        if result["validation_status"] == "valid":
            st.success("✅ SQL Validated")
        else:
            st.warning("⚠️ Validation Issues")
            for error in result.get("validation_errors", []):
                st.error(error)
        
        st.subheader("Explanation")
        st.info(result["explanation"])
        
        st.download_button("📋 Download SQL", result["sql"], "query.sql", "text/plain")
    
    with tab2:
        st.subheader("Extracted Entities")
        if result["entities"]:
            df = pd.DataFrame(result["entities"])
            st.dataframe(df[["text", "label", "confidence"]], use_container_width=True)
        else:
            st.info("No entities extracted")
        
        st.subheader("Intent Scores")
        scores = result["intent"].get("all_scores", {})
        if scores:
            df = pd.DataFrame([{"Intent": k, "Score": v} for k, v in scores.items()])
            fig = px.bar(df.sort_values("Score"), x="Score", y="Intent", orientation="h")
            st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("Query History")
        for item in reversed(st.session_state.query_history[-10:]):
            with st.expander(item['query'][:50]):
                st.code(item['sql'], language="sql")
        if st.button("Clear History"):
            st.session_state.query_history = []
            st.rerun()

# Footer
st.markdown("---")
st.caption("DataGenie AI - Powered by LangChain, Claude API & ChromaDB")
