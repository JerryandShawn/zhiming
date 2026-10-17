-- Prepare v4 storage without changing v3's application-level call budget.
DO $$
DECLARE old_constraint record;
BEGIN
  FOR old_constraint IN
    SELECT conname FROM pg_constraint
    WHERE conrelid='core_runs'::regclass AND contype='c'
      AND pg_get_constraintdef(oid) LIKE '%calls <= call_limit%'
  LOOP
    EXECUTE format('ALTER TABLE core_runs DROP CONSTRAINT %I',old_constraint.conname);
  END LOOP;
END $$;
ALTER TABLE core_runs ADD CONSTRAINT core_runs_calls_nonnegative CHECK(calls>=0);
ALTER TABLE core_runs ADD COLUMN kind text NOT NULL DEFAULT 'turn' CHECK(kind IN ('turn','reflection','followup','brief','report','subagent','reading'));
ALTER TABLE core_runs ADD COLUMN lane text NOT NULL DEFAULT 'interactive' CHECK(lane IN ('interactive','background'));
ALTER TABLE core_runs ADD COLUMN runtime text NOT NULL DEFAULT 'v3' CHECK(runtime IN ('v3','v4'));
ALTER TABLE core_runs ADD COLUMN thread_id text;
ALTER TABLE core_runs ADD COLUMN iterations integer NOT NULL DEFAULT 0 CHECK(iterations>=0);
ALTER TABLE core_runs ADD COLUMN usage jsonb NOT NULL DEFAULT '{}';
ALTER TABLE core_runs ADD COLUMN cancel_requested_at timestamptz;
ALTER TABLE core_runs ADD COLUMN deadline_at timestamptz;
ALTER TABLE core_runs ADD COLUMN parent_run_id text REFERENCES core_runs(id);
CREATE UNIQUE INDEX core_run_owner_identity ON core_runs(owner,id);
CREATE INDEX core_run_lane_queue ON core_runs(lane,status,created_at) WHERE status IN ('queued','running');
CREATE INDEX core_run_thread_recent ON core_runs(owner,thread_id,created_at DESC);
CREATE TABLE core_run_steps(
  owner text NOT NULL, run_id text NOT NULL, epoch integer NOT NULL DEFAULT 0,
  seq integer NOT NULL, kind text NOT NULL, name text NOT NULL DEFAULT '',
  status text NOT NULL, input_fp text NOT NULL, output jsonb, usage jsonb NOT NULL DEFAULT '{}',
  error_code text, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
  PRIMARY KEY(run_id,epoch,seq), FOREIGN KEY(owner,run_id) REFERENCES core_runs(owner,id) ON DELETE CASCADE
);
CREATE TABLE core_run_events(
  owner text NOT NULL, run_id text NOT NULL, seq bigint NOT NULL,
  kind text NOT NULL, payload jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,seq), FOREIGN KEY(owner,run_id) REFERENCES core_runs(owner,id) ON DELETE CASCADE
);
CREATE INDEX core_run_event_expiry ON core_run_events(created_at);
