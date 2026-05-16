"""Job application tracker page."""

import streamlit as st

from api_client import api, detail, safe_json
from components import show_error, show_success

STATUS_EMOJIS = {
    "wishlist": "💭",
    "applied": "📤",
    "phone_screen": "📞",
    "interview": "🎯",
    "offer": "🎉",
    "rejected": "❌",
    "accepted": "✅",
}

_STATUS_ORDER = ["wishlist", "applied", "phone_screen", "interview", "offer", "accepted"]


def _deadline_badge(deadline_str: str | None) -> str:
    if not deadline_str:
        return ""
    from datetime import date
    try:
        dl = date.fromisoformat(deadline_str)
    except ValueError:
        return ""
    days = (dl - date.today()).days
    if days < 0:
        return f"  🔴 **Overdue** ({abs(days)}d ago)"
    elif days == 0:
        return "  🔴 **Due Today!**"
    elif days == 1:
        return "  🟡 **Due Tomorrow**"
    elif days <= 7:
        return f"  🟠 **Due in {days}d**"
    else:
        return f"  🗓️ Due {dl.strftime('%b %d')}"


def _next_status(current: str) -> str | None:
    try:
        idx = _STATUS_ORDER.index(current)
        return _STATUS_ORDER[idx + 1] if idx + 1 < len(_STATUS_ORDER) else None
    except ValueError:
        return None


def page_job_tracker() -> None:
    st.title("📊 Job Application Tracker")

    with st.expander("➕ Add New Application"):
        with st.form("add_job_form"):
            col1, col2 = st.columns(2)
            company = col1.text_input("Company")
            role = col2.text_input("Role / Title")
            status = st.selectbox("Status", list(STATUS_EMOJIS.keys()))
            job_url = st.text_input("Job URL (optional)")
            deadline = st.date_input("Application Deadline (optional)", value=None)
            notes = st.text_area("Notes", height=80)
            if st.form_submit_button("Add Application", type="primary"):
                resp = api(
                    "post", "/jobs/",
                    json={
                        "company": company, "role": role, "status": status,
                        "job_url": job_url or None, "notes": notes or None,
                        "deadline": deadline.isoformat() if deadline else None,
                    },
                )
                if resp.status_code == 201:
                    show_success("Application added!")
                    st.rerun()
                else:
                    show_error(detail(resp, "Failed to add."))

    stats = safe_json(api("get", "/jobs/stats"), {})
    if isinstance(stats, dict) and "by_status" in stats:
        st.subheader(f"📈 Pipeline — {stats['total']} Applications")
        cols = st.columns(7)
        for col, (s, count) in zip(cols, stats["by_status"].items()):
            col.metric(f"{STATUS_EMOJIS.get(s, '')} {s.replace('_', ' ').title()}", count)

    st.divider()
    filter_status = st.selectbox("Filter by Status", ["All"] + list(STATUS_EMOJIS.keys()))
    params = {} if filter_status == "All" else {"status_filter": filter_status}
    apps_resp = api("get", "/jobs/", params=params)
    apps = apps_resp.json() if apps_resp.status_code == 200 else []

    if not apps:
        st.info("No applications yet. Add one above!")
        return

    for app in apps:
        emoji = STATUS_EMOJIS.get(app["status"], "")
        badge = _deadline_badge(app.get("deadline"))
        is_auto = app.get("source") == "auto"
        auto_tag = "  🤖 Auto" if is_auto else ""
        with st.expander(
            f"{emoji} **{app['company']}** — {app['role']}  |  `{app['status']}`{badge}{auto_tag}"
        ):
            col1, col2 = st.columns([3, 1])
            with col1:
                if is_auto:
                    st.caption("🤖 Auto-created when your cover letter was generated.")
                st.markdown(f"**Applied:** {app.get('applied_at', 'N/A')}")
                if app.get("deadline"):
                    st.markdown(f"**Deadline:** `{app['deadline']}`{_deadline_badge(app['deadline'])}")
                if app.get("job_url"):
                    st.markdown(f"**URL:** [{app['job_url']}]({app['job_url']})")
                if app.get("cover_letter_id"):
                    st.markdown(
                        f"**Cover Letter:** linked — "
                        f"[View in Cover Letter tab](#) _(ID: {str(app['cover_letter_id'])[:8]}…)_"
                    )
                if app.get("notes"):
                    st.markdown(f"**Notes:** {app['notes']}")
                next_st = _next_status(app["status"])
                if next_st and app["status"] != "rejected":
                    next_label = f"{STATUS_EMOJIS.get(next_st, '')} Advance → {next_st.replace('_', ' ').title()}"
                    if st.button(next_label, key=f"promote_{app['id']}"):
                        api("patch", f"/jobs/{app['id']}", json={"status": next_st})
                        st.rerun()
            with col2:
                new_status = st.selectbox(
                    "Update Status", list(STATUS_EMOJIS.keys()),
                    index=list(STATUS_EMOJIS.keys()).index(app["status"]),
                    key=f"status_{app['id']}",
                )
                new_deadline = st.date_input(
                    "Deadline", value=None, key=f"dl_{app['id']}",
                    help="Leave empty to keep existing deadline",
                )
                if st.button("Save", key=f"save_{app['id']}"):
                    patch = {"status": new_status}
                    if new_deadline:
                        patch["deadline"] = new_deadline.isoformat()
                    api("patch", f"/jobs/{app['id']}", json=patch)
                    st.rerun()
                if st.button("🗑️ Delete", key=f"del_{app['id']}"):
                    api("delete", f"/jobs/{app['id']}")
                    st.rerun()
