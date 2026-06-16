"""Job application tracker page."""

from datetime import UTC, datetime

import streamlit as st

from api_client import api, detail, safe_json
from ui import empty_state, nav_to, page_header, show_error, show_success, status_icon

# UI order for the add-form and filter; promotion follows _STATUS_ORDER below.
_STATUSES = ["wishlist", "applied", "phone_screen", "interview", "offer", "rejected", "accepted"]

_STATUS_ORDER = [
    "wishlist",
    "applied",
    "phone_screen",
    "interview",
    "offer",
    "accepted",
]


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


def _applied_stamp(app: dict, new_status: str) -> dict:
    """PATCH body for a status change; stamps applied_at the first time a job hits applied."""
    patch: dict = {"status": new_status}
    if new_status == "applied" and not app.get("applied_at"):
        patch["applied_at"] = datetime.now(UTC).isoformat()
    return patch


def page_job_tracker() -> None:
    page_header("📊", "Tracker")

    with st.expander("➕ Add New Application"):
        with st.form("add_job_form"):
            col1, col2 = st.columns(2)
            company = col1.text_input("Company")
            role = col2.text_input("Role / Title")
            status = st.selectbox("Status", _STATUSES)
            job_url = st.text_input("Job URL (optional)")
            deadline = st.date_input("Application Deadline (optional)", value=None)
            notes = st.text_area("Notes", height=80)
            if st.form_submit_button("Add Application", type="primary"):
                resp = api(
                    "post",
                    "/jobs/",
                    json={
                        "company": company,
                        "role": role,
                        "status": status,
                        "job_url": job_url or None,
                        "notes": notes or None,
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
        # cols is fixed at 7; tolerate a server payload with fewer statuses.
        for col, (s, count) in zip(cols, stats["by_status"].items(), strict=False):
            col.metric(f"{status_icon(s)} {s.replace('_', ' ').title()}", count)

    st.divider()
    filter_status = st.selectbox("Filter by Status", ["All"] + _STATUSES)
    params = {} if filter_status == "All" else {"status_filter": filter_status}
    apps_resp = api("get", "/jobs/", params=params)
    apps = safe_json(apps_resp, []) if apps_resp.status_code == 200 else []

    if not apps:
        if empty_state(
            "📊",
            "No applications tracked yet",
            "Run Quick Apply or generate a cover letter and the job lands here "
            "automatically — or add one with the form above.",
            cta="Run Quick Apply",
        ):
            nav_to("agent")
        return

    for app in apps:
        emoji = status_icon(app["status"])
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
                if app.get("applied_at"):
                    st.markdown(f"**Applied:** {str(app['applied_at'])[:10]}")
                if app.get("deadline"):
                    st.markdown(
                        f"**Deadline:** `{app['deadline']}`{_deadline_badge(app['deadline'])}"
                    )
                if app.get("job_url"):
                    st.markdown(f"**URL:** [{app['job_url']}]({app['job_url']})")
                if app.get("cover_letter_id"):
                    if st.button("✉️ View cover letter", key=f"view_cl_{app['id']}"):
                        st.session_state["active_cl_id"] = app["cover_letter_id"]
                        nav_to("cover_letter")
                if app.get("notes"):
                    st.markdown(f"**Notes:** {app['notes']}")
                next_st = _next_status(app["status"])
                if next_st and app["status"] != "rejected":
                    next_label = (
                        f"{status_icon(next_st)} Advance → {next_st.replace('_', ' ').title()}"
                    )
                    if st.button(next_label, key=f"promote_{app['id']}"):
                        resp = api("patch", f"/jobs/{app['id']}", json=_applied_stamp(app, next_st))
                        if resp.status_code == 200:
                            st.rerun()
                        else:
                            show_error(detail(resp, "Could not update status."))
            with col2:
                new_status = st.selectbox(
                    "Update Status",
                    _STATUSES,
                    index=_STATUSES.index(app["status"]) if app["status"] in _STATUSES else 0,
                    key=f"status_{app['id']}",
                )
                new_deadline = st.date_input(
                    "Deadline",
                    value=None,
                    key=f"dl_{app['id']}",
                    help="Leave empty to keep existing deadline",
                )
                if st.button("Save", key=f"save_{app['id']}"):
                    patch = _applied_stamp(app, new_status)
                    if new_deadline:
                        patch["deadline"] = new_deadline.isoformat()
                    resp = api("patch", f"/jobs/{app['id']}", json=patch)
                    if resp.status_code == 200:
                        st.rerun()
                    else:
                        show_error(detail(resp, "Could not save changes."))
                if st.button("🗑️ Delete", key=f"del_{app['id']}"):
                    resp = api("delete", f"/jobs/{app['id']}")
                    if resp.status_code == 204:
                        st.rerun()
                    else:
                        show_error(detail(resp, "Could not delete."))
