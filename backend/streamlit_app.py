import sys
import asyncio
import streamlit as st
import time

# Ensure the backend directory is in the path
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from llm.gemini import GeminiProvider
from agents.orchestrator import ResearchOrchestrator, OrchestratorRequest

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

# Async wrapper for orchestrator
async def run_orchestrator(prompt: str, api_key: str):
    llm = GeminiProvider(api_key=api_key) if api_key else None
    orchestrator = ResearchOrchestrator(llm=llm)
    req = OrchestratorRequest(text=prompt)
    
    # We will use st.status to show progress
    with st.status("🧠 AI Agents are researching...", expanded=True) as status:
        async for state in orchestrator.run(req):
            if state.progress_logs:
                # Get the latest log
                latest_log = state.progress_logs[-1]
                st.write(f"✅ {latest_log.message}")
        
        status.update(label="Research Complete!", state="complete", expanded=False)
    
    return state

if st.button("Search", type="primary") and query:
    # Run the asyncio event loop
    state = asyncio.run(run_orchestrator(query, st.session_state.gemini_api_key))
    
    # --- Display Results ---
    if state.error:
        st.error(f"An error occurred: {state.error}")
    else:
        st.success(f"Found {len(state.results)} perfect matches for you!")
        
        # Display Requirements
        with st.expander("📝 Extracted Requirements"):
            for req in state.requirements:
                st.write(f"- **{req.key.title()}**: {req.operator} {req.value} *(Priority: {req.priority.value})*")
        
        st.divider()
        
        # Display Products in Columns
        if state.results:
            cols = st.columns(len(state.results))
            for i, result in enumerate(state.results):
                with cols[i]:
                    st.subheader(result.product.name)
                    st.write(f"**Score:** {result.score_out_of_10}/10")
                    
                    st.write("### Specs")
                    for k, v in result.product.specs.items():
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
