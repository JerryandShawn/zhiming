-- One separately configured central schema serves every business/evaluation database.
CREATE TABLE core_model_accounts (
  account_id text PRIMARY KEY,
  ledger_identity uuid NOT NULL UNIQUE,
  location_id text NOT NULL CHECK(location_id ~ '^[0-9a-f]{64}$'),
  stop_kind text,
  stopped_at timestamptz,
  resume_at timestamptz,
  last_clock_at timestamptz,
  next_batch_not_before timestamptz,
  clear_authorization text
);
CREATE TABLE core_model_batches (
  account_id text NOT NULL REFERENCES core_model_accounts(account_id),
  batch_id text NOT NULL,
  scenario_ids text[] NOT NULL CHECK(cardinality(scenario_ids) BETWEEN 1 AND 10),
  fingerprint text NOT NULL,
  authorization_id text NOT NULL,
  expires_at timestamptz NOT NULL,
  status text NOT NULL CHECK(status IN ('active','completed')),
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  recovery_authorization text,
  PRIMARY KEY(account_id,batch_id)
);
CREATE UNIQUE INDEX core_model_one_active_batch ON core_model_batches(account_id) WHERE status='active';
CREATE TABLE core_model_authorizations (
  account_id text NOT NULL,
  authorization_id text NOT NULL,
  batch_id text,
  kind text NOT NULL DEFAULT 'batch' CHECK(kind IN ('batch','clear_stop','recovery')),
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(account_id,authorization_id),
  FOREIGN KEY(account_id,batch_id) REFERENCES core_model_batches(account_id,batch_id),
  CHECK((kind='clear_stop' AND batch_id IS NULL) OR (kind IN ('batch','recovery') AND batch_id IS NOT NULL))
);
CREATE TABLE core_model_usage (
  id bigserial PRIMARY KEY,
  account_id text NOT NULL REFERENCES core_model_accounts(account_id),
  attempt_id text NOT NULL,
  at timestamptz NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  role text NOT NULL CHECK(role IN ('primary','critic','fast','vision','evaluation','background')),
  lane text NOT NULL CHECK(lane IN ('interactive','background','eval','probe')),
  bucket text NOT NULL CHECK(bucket IN ('interactive','critic','background')),
  run_id text,
  batch_id text,
  scenario_id text,
  status text NOT NULL DEFAULT 'reserved',
  input_tokens bigint CHECK(input_tokens>=0),
  cache_read_tokens bigint CHECK(cache_read_tokens>=0),
  cache_write_tokens bigint CHECK(cache_write_tokens>=0),
  output_tokens bigint CHECK(output_tokens>=0),
  latency_ms double precision CHECK(latency_ms>=0),
  finished_at timestamptz,
  UNIQUE(account_id,attempt_id),
  FOREIGN KEY(account_id,batch_id) REFERENCES core_model_batches(account_id,batch_id)
);
CREATE INDEX core_model_window ON core_model_usage(account_id,at);
CREATE INDEX core_model_batch_attempts ON core_model_usage(account_id,batch_id) WHERE finished_at IS NULL;
