"use client";

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/client";
import { statuses } from "../lib/contracts";
import type { JobApplication, JobFields, JobStatus, Viewer } from "../lib/contracts";
import ApiRecovery from "./api-recovery";

type Session = { state: "loading" | "guest" | "unavailable" } | { state: "signed-in"; viewer: Viewer };

const PAGE_SIZE = 25;

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

function isUnavailable(error: unknown) {
  return error instanceof ApiError && error.status === 503;
}

async function getSession(): Promise<Session> {
  try {
    const viewer = await api<Viewer>("session/me");
    return { state: "signed-in", viewer };
  } catch (error) {
    return { state: error instanceof ApiError && error.status === 401 ? "guest" : "unavailable" };
  }
}

export default function Workspace() {
  const [session, setSession] = useState<Session>({ state: "loading" });
  const [authError, setAuthError] = useState("");
  const [busy, setBusy] = useState(false);
  const [authRecovery, setAuthRecovery] = useState<"sign-in" | "sign-out" | null>(null);
  const [autoResume, setAutoResume] = useState(true);
  const expireSession = useCallback(() => setSession({ state: "guest" }), []);

  useEffect(() => {
    let active = true;
    void getSession().then((result) => { if (active) setSession(result); });
    return () => { active = false; };
  }, []);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const data = new URLSearchParams({
      username: String(fields.get("email")).trim(),
      password: String(fields.get("password")),
    });
    setBusy(true);
    setAuthError("");
    setAutoResume(true);
    try {
      await api("session/login", { method: "POST", body: data }, false);
      setSession(await getSession());
    } catch (error) {
      if (isUnavailable(error)) setAuthRecovery("sign-in");
      else setAuthError(error instanceof ApiError && error.status === 401
        ? "Incorrect email or password."
        : errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    setBusy(true);
    setAuthError("");
    try {
      await api("session/logout", { method: "POST" }, false);
      setSession({ state: "guest" });
    } catch (error) {
      if (isUnavailable(error)) setAuthRecovery("sign-out");
      else setAuthError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const retrySession = useCallback(() => {
    setAutoResume(false);
    setSession({ state: "loading" });
    void getSession().then(setSession);
  }, []);

  const afterAuthRecovery = useCallback(() => {
    if (authRecovery === "sign-in") {
      setAuthError("The API is ready. Select Sign in to try again.");
    } else {
      retrySession();
    }
    setAuthRecovery(null);
  }, [authRecovery, retrySession]);

  return (
    <>
      <header className="site-header">
        <div className="shell bar">
          <a className="brand" href="/" aria-label="Career Hub home"><span aria-hidden="true" className="brand-mark">CH</span> Career Hub</a>
          {session.state === "signed-in" && (
            <div className="account">
              <span>{session.viewer.full_name || session.viewer.email}</span>
              <button className="secondary" type="button" onClick={signOut} disabled={busy || authRecovery !== null}>Sign out</button>
            </div>
          )}
        </div>
      </header>
      <main className="shell content">
        {session.state === "signed-in" ? (
          <>
            {authError && <p role="alert" className="error">{authError}</p>}
            {authRecovery === "sign-out" && <ApiRecovery onReady={afterAuthRecovery} />}
            <Tracker onExpired={expireSession} />
          </>
        ) : session.state === "guest" ? (
          <section className="sign-in">
            <div className="intro">
              <h1>Track your job search</h1>
              <p>Keep your applications, deadlines, and next steps in one place.</p>
            </div>
            <form className="panel form" onSubmit={signIn}>
              <h2>Sign in</h2>
              <label>Email <input name="email" type="email" autoComplete="username" maxLength={255} required /></label>
              <label>Password <input name="password" type="password" autoComplete="current-password" required /></label>
              {authError && <p className="error" role="alert">{authError}</p>}
              {authRecovery === "sign-in" && <ApiRecovery onReady={afterAuthRecovery} />}
              <button className="primary" disabled={busy || authRecovery !== null}>{busy ? "Signing in…" : "Sign in"}</button>
            </form>
          </section>
        ) : (
          <section className="panel status-panel" aria-live="polite">
            <h1>{session.state === "loading" ? "Loading Career Hub…" : "Career Hub is temporarily unavailable"}</h1>
            {session.state === "unavailable" && <ApiRecovery onReady={retrySession} autoStart={autoResume} />}
          </section>
        )}
      </main>
    </>
  );
}

function Tracker({ onExpired }: { onExpired: () => void }) {
  const [jobs, setJobs] = useState<JobApplication[]>();
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState<JobStatus | "">("");
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<JobApplication | "new" | null>(null);
  const [busy, setBusy] = useState(false);
  const [listError, setListError] = useState("");
  const [actionError, setActionError] = useState("");
  const [readRecovery, setReadRecovery] = useState(false);
  const [verifyWrite, setVerifyWrite] = useState(false);
  const [autoCheck, setAutoCheck] = useState(false);

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ skip: String(page * PAGE_SIZE), limit: String(PAGE_SIZE) });
    if (filter) query.set("status_filter", filter);

    void api<JobApplication[]>("jobs?" + query).then((data) => {
      if (!active) return;
      setJobs(data);
      setVerifyWrite(false);
      if (data.length === 0 && page > 0) {
        setJobs(undefined);
        setPage((value) => value - 1);
      }
    }).catch((error) => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 401) onExpired();
      else {
        setReadRecovery(isUnavailable(error));
        setListError(errorMessage(error));
      }
    });
    return () => { active = false; };
  }, [page, filter, revision, onExpired]);

  const reload = useCallback(() => {
    setListError("");
    setReadRecovery(false);
    setRevision((value) => value + 1);
  }, []);

  const afterTrackerRecovery = useCallback(() => {
    if (verifyWrite) {
      setFilter("");
      setPage(0);
      setJobs(undefined);
    }
    setAutoCheck(false);
    reload();
  }, [reload, verifyWrite]);

  function handleWriteFailure(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      onExpired();
    } else if (isUnavailable(error)) {
      setVerifyWrite(true);
      setReadRecovery(true);
      setAutoCheck(true);
      setActionError("We couldn't confirm this change. Review the refreshed applications before trying again.");
    } else {
      setActionError(errorMessage(error));
    }
  }

  function changePage(next: number) {
    setJobs(undefined);
    setListError("");
    setPage(next);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing || verifyWrite || readRecovery || !jobs) return;
    const fields = new FormData(event.currentTarget);
    const company = String(fields.get("company")).trim();
    const role = String(fields.get("role")).trim();
    const jobUrl = String(fields.get("job_url")).trim();
    if (!company || !role) {
      setActionError("Enter a company and role.");
      return;
    }
    if (jobUrl && !/^https?:\/\//i.test(jobUrl)) {
      setActionError("Enter a job URL starting with https:// or http://.");
      return;
    }
    const job: JobFields = {
      company,
      role,
      status: fields.get("status") as JobStatus,
      job_url: jobUrl || null,
      deadline: String(fields.get("deadline")) || null,
      notes: String(fields.get("notes")).trim() || null,
    };
    const creating = editing === "new";
    const payload = job.status === "applied" && (creating || !editing.applied_at)
      ? { ...job, applied_at: new Date().toISOString() }
      : job;
    setBusy(true);
    setActionError("");
    try {
      await api(creating ? "jobs" : "jobs/" + editing.id, {
        method: creating ? "POST" : "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      setEditing(null);
      if (creating && (page > 0 || (filter && filter !== job.status))) {
        setFilter("");
        changePage(0);
      }
      reload();
    } catch (error) {
      handleWriteFailure(error);
    } finally {
      setBusy(false);
    }
  }

  async function remove(job: JobApplication) {
    if (verifyWrite || readRecovery) return;
    if (!window.confirm("Delete the " + job.role + " application at " + job.company + "?")) return;
    setBusy(true);
    setActionError("");
    try {
      await api("jobs/" + job.id, { method: "DELETE" });
      if (editing !== "new" && editing?.id === job.id) setEditing(null);
      reload();
    } catch (error) {
      handleWriteFailure(error);
    } finally {
      setBusy(false);
    }
  }

  const selected = editing === "new" ? undefined : editing ?? undefined;
  const writesDisabled = busy || verifyWrite || readRecovery || !jobs;

  return (
    <section aria-labelledby="tracker-title">
      <div className="section-header">
        <h1 id="tracker-title">Job tracker</h1>
        <button type="button" className="primary" disabled={writesDisabled || editing === "new"} onClick={() => { setEditing("new"); setActionError(""); }}>
          Add application
        </button>
      </div>
      {editing && (
        <form className="panel editor" key={selected?.id ?? "new"} onSubmit={save}>
          <h2>{selected ? "Edit application" : "New application"}</h2>
          <div className="fields">
            <label>Company <input name="company" defaultValue={selected?.company} maxLength={255} required /></label>
            <label>Role <input name="role" defaultValue={selected?.role} maxLength={255} required /></label>
            <label>Status <select name="status" defaultValue={selected?.status ?? "wishlist"}>
              {statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select></label>
            <label>Deadline <input name="deadline" type="date" defaultValue={selected?.deadline ?? ""} /></label>
            <label className="full">Job URL <input name="job_url" type="url" defaultValue={selected?.job_url ?? ""} maxLength={500} /></label>
            <label className="full">Notes <textarea name="notes" rows={3} defaultValue={selected?.notes ?? ""} /></label>
          </div>
          {actionError && <p className="error" role="alert">{actionError}</p>}
          <div className="actions">
            <button className="primary" disabled={writesDisabled}>{busy ? "Saving…" : "Save application"}</button>
            <button className="secondary" type="button" disabled={busy} onClick={() => { setEditing(null); setActionError(""); }}>Cancel</button>
          </div>
        </form>
      )}
      {!editing && actionError && <p className="error" role="alert">{actionError}</p>}
      {readRecovery && <ApiRecovery onReady={afterTrackerRecovery} autoStart={autoCheck} />}
      <div className="panel tracker-list">
        <div className="list-header">
          <h2>Applications</h2>
          <label className="filter">Status <select value={filter} disabled={busy || verifyWrite || readRecovery} onChange={(event) => {
            setFilter(event.target.value as JobStatus | "");
            changePage(0);
          }}>
            <option value="">All statuses</option>
            {statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        </div>
        {listError ? <div className="list-empty" role="alert"><p>{listError}</p>{!readRecovery && <button type="button" className="secondary" onClick={reload}>Try again</button>}</div>
          : jobs?.length ? (
            <ul className="job-list">
              {jobs.map((job) => (
                <li className="job-row" key={job.id}>
                  <div className="job-title"><h3>{job.role}</h3><p>{job.company}</p></div>
                  <span className="status-label">{statuses.find(([value]) => value === job.status)?.[1] ?? job.status}</span>
                  <span className="deadline">{job.deadline ? <time dateTime={job.deadline}>{job.deadline}</time> : "No deadline"}</span>
                  <div className="row-actions">
                    <button type="button" disabled={writesDisabled} onClick={() => { setEditing(job); setActionError(""); }} aria-label={"Edit " + job.role}>Edit</button>
                    <button type="button" className="delete" disabled={writesDisabled} onClick={() => remove(job)} aria-label={"Delete " + job.role}>Delete</button>
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="list-empty" role="status">{jobs ? (filter ? "No applications with this status." : "No applications yet.") : "Loading applications…"}</p>}
        {(page > 0 || jobs?.length === PAGE_SIZE) && (
          <div className="pagination">
            <button className="secondary" type="button" disabled={page === 0 || !jobs || busy || verifyWrite || readRecovery} onClick={() => changePage(page - 1)}>Previous</button>
            <span>Page {page + 1}</span>
            <button className="secondary" type="button" disabled={jobs?.length !== PAGE_SIZE || busy || verifyWrite || readRecovery} onClick={() => changePage(page + 1)}>Next</button>
          </div>
        )}
      </div>
    </section>
  );
}
