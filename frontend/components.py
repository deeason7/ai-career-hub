"""Shared UI primitives used across all page modules."""

import streamlit as st


def show_error(msg: str) -> None:
    st.error(f"❌ {msg}")


def show_success(msg: str) -> None:
    st.success(f"✅ {msg}")
