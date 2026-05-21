"""Auth page — login and register tabs."""

from datetime import datetime, timedelta

import requests
import streamlit as st

from api_client import API_URL, api, detail, safe_json
from components import show_error, show_success


def page_auth(cookie_manager) -> None:
    """Render the login/register page. Receives cookie_manager from app.py."""
    st.title("🚀 AI Career Hub")
    st.markdown(
        "An AI-powered platform for job seekers — multi-resume management, "
        "RAG cover letters, ATS scoring, and more."
    )
    tab_login, tab_register = st.tabs(["🔐 Login", "📝 Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary"):
                resp = requests.post(
                    f"{API_URL}/auth/login",
                    data={"username": email, "password": password},
                )
                if resp.status_code == 200:
                    data = safe_json(resp, {})
                    st.session_state.token = data.get("access_token")
                    if not st.session_state.token:
                        show_error("Login failed: no token received.")
                        return
                    cookie_manager.set(
                        "auth_token",
                        st.session_state.token,
                        expires_at=datetime.now() + timedelta(hours=1),
                    )
                    me = safe_json(api("get", "/auth/me"), {})
                    st.session_state.user = me
                    show_success("Logged in!")
                    st.rerun()
                elif resp.status_code == 503:
                    st.warning(
                        "⏳ **Database is still warming up** — this is normal after a cold start.\n\n"
                        "Please wait **~30 seconds** and try again."
                    )
                elif resp.status_code == 429:
                    show_error("Too many login attempts. Please wait 1 minute and try again.")
                else:
                    show_error(detail(resp, "Login failed."))

    with tab_register:
        with st.form("register_form"):
            name = st.text_input("Full Name")
            r_email = st.text_input("Email")
            r_password = st.text_input("Password", type="password")
            if st.form_submit_button("Create Account", type="primary"):
                resp = requests.post(
                    f"{API_URL}/auth/register",
                    json={"email": r_email, "full_name": name, "password": r_password},
                )
                if resp.status_code == 201:
                    show_success("Account created! Please log in.")
                elif resp.status_code == 503:
                    st.warning(
                        "⏳ **Database is still warming up** — this is normal after a cold start.\n\n"
                        "Please wait **~30 seconds** and try again."
                    )
                elif resp.status_code == 429:
                    show_error(
                        "Too many registration attempts. Please wait 1 minute and try again."
                    )
                else:
                    show_error(detail(resp, "Registration failed."))
