"""
Azure OpenAI client factory — uses Managed Identity (or `az login` locally).
Required role on the AOAI resource: "Cognitive Services OpenAI User".
"""
from __future__ import annotations

import streamlit as st

from config import AZURE_CFG


@st.cache_resource(show_spinner=False)
def get_aoai_client():
    """
    Build a singleton Azure OpenAI client.
    Returns None if AOAI is not configured or auth fails — callers should guard.
    """
    if not AZURE_CFG.aoai_enabled:
        return None
    try:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        return AzureOpenAI(
            azure_endpoint=AZURE_CFG.aoai_endpoint,
            azure_ad_token_provider=token_provider,
            api_version=AZURE_CFG.aoai_api_version,
        )
    except Exception as exc:
        st.warning(f"Azure OpenAI init failed: {exc}")
        return None
