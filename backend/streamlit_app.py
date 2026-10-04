"""Secondary UI using the same server provider and typed comparison models."""
import asyncio
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from agents.requirement import RequirementAgent
from agents.orchestrator import run_pipeline
from llm.gemini import get_llm_provider
from llm.base import LLMError

st.set_page_config(page_title="BuyWise AI", page_icon="🛍️", layout="wide")
st.title("BuyWise AI")
st.subheader("Evidence-backed shopping comparisons")
with st.sidebar:
    st.header("Settings")
    # Credentials belong to the server, not shared process env mutated by users.
    st.info("Gemini uses the server's GEMINI_API_KEY setting.")
    if not os.getenv("GEMINI_API_KEY"):
        st.warning("No server key configured. Results are canned demo data.")

query = st.text_input("What are you looking for?", placeholder="A laptop under $1,000 with 32GB RAM for Linux")

async def _do_research(prompt):
    agent = RequirementAgent(llm=get_llm_provider())
    try:
        requirements = await agent.run(prompt)
    except LLMError:
        requirements = await agent.run_mock(prompt)
    finally:
        if hasattr(agent.llm, "aclose"):
            await agent.llm.aclose()
    if requirements.category == "unsupported":
        return requirements, None
    comparison = await run_pipeline(requirements.request_id, requirements.requirements, raw_text=prompt)
    return requirements, comparison

if st.button("Search", type="primary"):
    if not 10 <= len(query.strip()) <= 1000:
        st.warning("Describe your needs in 10–1000 characters.")
    else:
        try:
            with st.spinner("Researching products..."):
                st.session_state['result'] = asyncio.run(_do_research(query.strip()))
        except Exception:
            st.error("Research unavailable. Check server logs or retry.")

if 'result' in st.session_state:
    requirements, comparison = st.session_state['result']
    for notice in requirements.notices:
        st.warning(notice)
    if comparison is None:
        for question in requirements.missing_info:
            st.warning(question)
    else:
        for notice in comparison.notices:
            st.warning(notice)
        st.success(f"Compared {len(comparison.products)} candidates.")
        with st.expander("Requirements used in this comparison"):
            for req in comparison.requirements:
                st.write(f"{req.key}: {req.operator} {req.value} ({req.priority.value})")
        if comparison.products:
            for column, product in zip(st.columns(len(comparison.products)), comparison.products):
                with column:
                    st.subheader(product.name)
                    st.write(product.score)
                    st.caption(f"Must-haves: {product.must_have_status}")
                    if product.price_info and product.price_info.amount is not None:
                        st.write(f"Listed price: {product.price_info.amount:g} {product.price_info.currency}")
                    else:
                        st.write("Price unknown")
                    st.write("### Specifications")
                    for spec in product.specs:
                        st.write(f"{spec.key}: {spec.value} ({spec.status.value})")
                    st.write("### Strengths and limits")
                    for text in product.pros:
                        st.write(f"✓ {text}")
                    for text in product.limitations:
                        st.write(f"• {text}")
        for tradeoff in comparison.tradeoffs:
            st.info(tradeoff)
        st.caption("Prices and availability change. Verify retailer terms before purchase.")
