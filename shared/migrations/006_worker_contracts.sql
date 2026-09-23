-- Additive JC upgrade. Do not rewrite jobs, input snapshots or hashes.
ALTER TABLE workers ADD COLUMN IF NOT EXISTS supported_contract_versions jsonb NOT NULL DEFAULT '["1.3"]'
 CHECK (jsonb_typeof(supported_contract_versions)='array'
   AND jsonb_array_length(supported_contract_versions)>0
   AND supported_contract_versions <@ '["1.3","1.4"]'::jsonb
   AND (kind='rca' OR supported_contract_versions='["1.3"]'::jsonb));
INSERT INTO jc_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
