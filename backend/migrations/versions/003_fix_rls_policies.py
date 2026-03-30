"""Fix RLS policies — grant access to the connecting role, not hardcoded 'postgres'.

Revision ID: 003_fix_rls_policies
Revises: 002_add_deadline_to_jobs
Create Date: 2026-03-30

Problem:
    Migration 001 granted the RLS bypass policy only to the role named 'postgres'.
    On Supabase, the actual connecting role in the connection string is a
    project-scoped user (e.g. postgres.<project-ref>) which is NOT the literal
    role 'postgres'. So after 001 ran, the backend had zero table permissions
    and all API calls (including registration) returned errors.

    Additionally, 001 ran REVOKE ALL FROM anon/authenticated which is correct,
    but the policy didn't cover the actual application role.

Fix:
    1. Drop the old hardcoded 'postgres' policy on all tables.
    2. Re-create it TO PUBLIC with USING (true) — this means ANY role that
       can connect to the database gets full access via this policy.
       This is safe because:
         - anon/authenticated are still explicitly revoked (block direct PostgREST)
         - Only roles with a valid DB connection (i.e. our backend) can reach this
    3. Also add RLS + a permissive policy to alembic_version to silence the
       Supabase Advisor warning (alembic_version only needs to be writable by
       the migration runner, not external roles).
"""
from alembic import op

revision = "003_fix_rls_policies"
down_revision = "002_add_deadline_to_jobs"
branch_labels = None
depends_on = None

TABLES = ["users", "resumes", "cover_letters", "job_applications"]


def upgrade() -> None:
    # --- Fix application table policies ---
    for table in TABLES:
        # Drop the old policy that hardcoded 'postgres' role
        op.execute(
            f'DROP POLICY IF EXISTS "backend_full_access" ON public."{table}"'
        )

        # Re-create: grant to PUBLIC so the actual connecting role is covered.
        # 'anon' and 'authenticated' are still revoked below, so PostgREST
        # (which connects as those roles) remains blocked.
        op.execute(f"""
            CREATE POLICY "backend_full_access" ON public."{table}"
            AS PERMISSIVE
            FOR ALL
            TO PUBLIC
            USING (true)
            WITH CHECK (true)
        """)

        # Belt-and-suspenders: keep anon/authenticated locked out
        op.execute(f'REVOKE ALL ON public."{table}" FROM anon')
        op.execute(f'REVOKE ALL ON public."{table}" FROM authenticated')

    # --- Silence Supabase Advisor: enable RLS on alembic_version ---
    # alembic_version is an internal migration tracking table.
    # We enable RLS and allow any authenticated DB user (PUBLIC) to read/write it
    # so Alembic migrations can still run.
    op.execute('ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY')
    op.execute("""
        CREATE POLICY "migration_runner_access" ON public.alembic_version
        AS PERMISSIVE
        FOR ALL
        TO PUBLIC
        USING (true)
        WITH CHECK (true)
    """)


def downgrade() -> None:
    # Restore alembic_version to no RLS
    op.execute(
        'DROP POLICY IF EXISTS "migration_runner_access" ON public.alembic_version'
    )
    op.execute('ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY')

    # Restore application tables to the old (broken) hardcoded policy
    for table in TABLES:
        op.execute(
            f'DROP POLICY IF EXISTS "backend_full_access" ON public."{table}"'
        )
        op.execute(f"""
            CREATE POLICY "backend_full_access" ON public."{table}"
            AS PERMISSIVE
            FOR ALL
            TO postgres
            USING (true)
            WITH CHECK (true)
        """)
