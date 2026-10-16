-- Version 2 separates a stale graph recomputation from stable business effects.
ALTER TABLE core_runs ADD COLUMN IF NOT EXISTS retry_epoch integer NOT NULL DEFAULT 0;
