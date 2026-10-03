import sys
import asyncio
import streamlit as st
import os
import uuid

# Ensure the backend directory is in the path
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from agents.requirement import RequirementAgent
from agents.orchestrator import run_pipeline
from llm.gemini import GeminiProvider, MockLLMProvider

st.set_page_config(page_title="BuyWise AI", page_icon="🛍️", layout="wide")

st.title("🛍️ BuyWise AI")
st.subheader("Your AI-powered shopping assistant")

# Initialize session state
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = ""

# Sidebar for API Key
with st.sidebar:
    st.header("⚙️ Settings")
    st.session_state.gemini_api_key = st.text_input(
        "Gemini API Key", 
        type="password", 
        value=st.session_state.gemini_api_key,
        help="Get your free key at aistudio.google.com"
    )
    if not st.session_state.gemini_api_key:
        st.warning("⚠️ Enter your Gemini API key to use live AI. Otherwise, it will use mock data.")

# Main search bar
query = st.text_input(
    "What are you looking for?", 
    placeholder="e.g., I need a laptop under $1,000 for cybersecurity. I use Linux and run multiple VMs. I want at least 32GB RAM."
)

async def _do_research(prompt: str, api_key: str):
    # Set environment variable so get_llm_provider() in orchestrator.py picks it up
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key
    elif "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]

    llm = GeminiProvider(api_key=api_key) if api_key else MockLLMProvider()
    
    with st.status("🧠 Understanding requirements...", expanded=True) as status:
        req_agent = RequirementAgent(llm=llm)
        try:
            req_res = await req_agent.run(prompt)
        except Exception:
            # Fallback to mock if LLM fails (e.g. no key)
            from agents.requirement import _DEMO_REQUIREMENTS
            from models.request import RequirementAnalysisResponse
            req_res = RequirementAnalysisResponse(
                category="laptop",
                requirements=_DEMO_REQUIREMENTS,
                request_id=str(uuid.uuid4())
            )
            
        st.write("✅ Requirements Extracted")
        
        # This callback receives the SSE dictionary
        async def on_progress(event):
            st.write(f"✅ {event['message']}")
            
        status.update(label="🔍 Researching products...", state="running")
        
        comparison = await run_pipeline(
            request_id=req_res.request_id,
            requirements=req_res.requirements,
            raw_text=prompt,
            progress_callback=on_progress
        )
        
        status.update(label="Research Complete!", state="complete", expanded=False)
        
    return req_res, comparison

if st.button("Search", type="primary") and query:
    try:
        req_res, comparison = asyncio.run(_do_research(query, st.session_state.gemini_api_key))
        
        st.success(f"Found {len(comparison.products)} perfect matches for you!")
        
        with st.expander("📝 Extracted Requirements"):
            for req in req_res.requirements:
                st.write(f"- **{req.key.title()}**: {req.operator} {req.value} *(Priority: {req.priority.value})*")
        
        st.divider()
        
        if comparison.products:
            cols = st.columns(len(comparison.products))
            for i, result in enumerate(comparison.products):
                with cols[i]:
                    st.subheader(result.product.name)
                    st.write(f"**Score:** {result.score_out_of_10}/10")
                    
                    st.write("### Specs")
                    for k, v in result.product.specs.items():
                        if v:
                            st.write(f"- **{k.replace('_', ' ').title()}**: {v}")
                    
                    st.write("### AI Analysis")
                    st.info(result.summary)
                    
                    st.write("### Pros & Cons")
                    for pro in result.pros:
                        st.write(f"✅ {pro}")
                    for con in result.cons:
                        st.write(f"❌ {con}")
        else:
            st.warning("No products found matching those strict requirements.")
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
