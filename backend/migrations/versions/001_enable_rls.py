"""Enable Row Level Security — Supabase-specific, no-op on standard PostgreSQL.

Revision ID: 001_enable_rls
Revises: 000_initial_schema
Create Date: 2026-03-27

This migration was written for Supabase, which exposes tables via PostgREST
and uses `anon`/`authenticated` roles. On standard PostgreSQL (e.g. RDS),
those roles don't exist and RLS provides no protection benefit since there's
no external query interface bypassing the application layer.

The SQL is wrapped in DO blocks so it runs safely on both platforms.
"""
from alembic import op

revision = "001_enable_rls"
down_revision = "000_initial_schema"
branch_labels = None
depends_on = None

TABLES = ["users", "resumes", "cover_letters", "job_applications"]


def upgrade() -> None:
    for table in TABLES:
        # Enable RLS — safe on all PostgreSQL variants
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')

        op.execute(f"""
            CREATE POLICY "backend_full_access" ON public."{table}"
            AS PERMISSIVE FOR ALL TO PUBLIC
            USING (true) WITH CHECK (true)
        """)

        # Revoke from Supabase PostgREST roles if they exist — no-op on RDS
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


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'DROP POLICY IF EXISTS "backend_full_access" ON public."{table}"')
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
