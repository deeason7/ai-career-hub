"""Enable Row Level Security (RLS) on all public tables.

Revision ID: 001_enable_rls
Revises: (none — first migration)
Create Date: 2026-03-27

Why:
    Supabase exposes the `public` schema via PostgREST. Without RLS,
    anyone with the project's anon key can read/write all data directly,
    bypassing our FastAPI authentication entirely.

Fix:
    1. Enable RLS on every application table.
    2. Add an OWNER / service-role bypass policy so our backend's
       Postgres role (which connects via the direct connection string)
       still has full access.
    3. Block all access from the `anon` and `authenticated` roles —
       we never use Supabase's built-in auth; all auth is via FastAPI.
"""
from alembic import op

# revision identifiers, used by Alembic
revision = "001_enable_rls"
down_revision = None
branch_labels = None
depends_on = None

# Actual table names from SQLModel __tablename__ definitions
TABLES = ["users", "resumes", "cover_letters", "job_applications"]


def upgrade() -> None:
    for table in TABLES:
        # Enable RLS — drops the implicit "allow all" default
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')

        # Allow the backend's Postgres role (owner / superuser) full access.
        # Supabase's `service_role` key bypasses RLS by design, but explicitly
        # granting the table owner keeps things working if that ever changes.
        op.execute(f"""
            CREATE POLICY "backend_full_access" ON public."{table}"
            AS PERMISSIVE
            FOR ALL
            TO postgres        -- Supabase superuser / migration role
            USING (true)
            WITH CHECK (true)
        """)

        # Explicitly deny anon and authenticated roles — belt-and-suspenders.
        # PostgREST uses these roles; denying them means even a leaked anon key
        # cannot read any data directly from Supabase's REST API.
        op.execute(f'REVOKE ALL ON public."{table}" FROM anon')
        op.execute(f'REVOKE ALL ON public."{table}" FROM authenticated')


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'DROP POLICY IF EXISTS "backend_full_access" ON public."{table}"')
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
        # Restore default grants (Supabase default)
        op.execute(f'GRANT ALL ON public."{table}" TO anon')
        op.execute(f'GRANT ALL ON public."{table}" TO authenticated')
