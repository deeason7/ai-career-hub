"""Fix RLS policy to use PUBLIC instead of hardcoded 'postgres' role.

Revision ID: 003_fix_rls_policies
Revises: 002_add_deadline_to_jobs
Create Date: 2026-03-30

Supabase-specific: replaces the policy created in 001 with one that grants
access to PUBLIC (any connecting role) instead of only the 'postgres' role.
On RDS this is a no-op since the 001 policy already uses PUBLIC.
"""
from alembic import op

revision = "003_fix_rls_policies"
down_revision = "002_add_deadline_to_jobs"
branch_labels = None
depends_on = None

TABLES = ["users", "resumes", "cover_letters", "job_applications"]


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'DROP POLICY IF EXISTS "backend_full_access" ON public."{table}"')
        op.execute(f"""
            CREATE POLICY "backend_full_access" ON public."{table}"
            AS PERMISSIVE FOR ALL TO PUBLIC
            USING (true) WITH CHECK (true)
        """)
        op.execute(f"""
            DO $$ BEGIN
                REVOKE ALL ON public."{table}" FROM anon;
            EXCEPTION WHEN undefined_object THEN NULL;
            END $$
        """)
        op.execute(f"""
            DO $$ BEGIN
                REVOKE ALL ON public."{table}" FROM authenticated;
            EXCEPTION WHEN undefined_object THEN NULL;
            END $$
        """)

    # Supabase Advisor: silence RLS warning on alembic_version
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE POLICY "migration_runner_access" ON public.alembic_version
            AS PERMISSIVE FOR ALL TO PUBLIC
            USING (true) WITH CHECK (true);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "migration_runner_access" ON public.alembic_version')
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)
    for table in TABLES:
        op.execute(f'DROP POLICY IF EXISTS "backend_full_access" ON public."{table}"')
