ALTER TABLE core_entities ADD COLUMN search tsvector
  GENERATED ALWAYS AS (to_tsvector('simple'::regconfig,coalesce(data->>'search_tokens',''))) STORED;
CREATE INDEX core_entity_search ON core_entities USING GIN(search) WHERE status='active';
CREATE TABLE core_embeddings(
  owner text NOT NULL, kind text NOT NULL, entity_id text NOT NULL, chunk integer NOT NULL,
  model text NOT NULL, vec real[] NOT NULL, content_fp text NOT NULL,
  PRIMARY KEY(owner,kind,entity_id,chunk,model),
  FOREIGN KEY(owner,kind,entity_id) REFERENCES core_entities(owner,kind,id) ON DELETE CASCADE
);
CREATE FUNCTION clear_retired_embeddings() RETURNS trigger LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
  IF NEW.status='deleted' OR NEW.data='{}'::jsonb THEN
    DELETE FROM core_embeddings WHERE owner=NEW.owner AND kind=NEW.kind AND entity_id=NEW.id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER core_embedding_retirement AFTER UPDATE OF status,data ON core_entities
  FOR EACH ROW EXECUTE FUNCTION clear_retired_embeddings();
