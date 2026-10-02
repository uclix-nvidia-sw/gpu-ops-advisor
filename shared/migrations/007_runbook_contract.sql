-- New RCA input support only. Existing jobs, snapshots and hashes stay immutable.
-- 006's multi-column inline CHECK is named workers_check by PostgreSQL.
ALTER TABLE workers DROP CONSTRAINT IF EXISTS workers_check;
ALTER TABLE workers DROP CONSTRAINT IF EXISTS workers_supported_contract_versions_check;
ALTER TABLE workers ADD CONSTRAINT workers_supported_contract_versions_check
 CHECK (jsonb_typeof(supported_contract_versions)='array'
   AND jsonb_array_length(supported_contract_versions)>0
   AND supported_contract_versions <@ '["1.3","1.4","1.5"]'::jsonb
   AND (kind='rca' OR supported_contract_versions='["1.3"]'::jsonb));
INSERT INTO jc_migrations(version) VALUES(3) ON CONFLICT DO NOTHING;
