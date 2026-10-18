CREATE INDEX core_thread_recent ON core_entities
  (owner,(data->>'thread_id'),((data->>'at_ms')::bigint) DESC,created_at DESC,id DESC)
  WHERE kind='message' AND status='active';
