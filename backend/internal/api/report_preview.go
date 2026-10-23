package api

// Project only published, stored prose; large aggregate rows never cross the DB boundary.
const reportPreviewSQL = `CASE WHEN c.kind='report' AND c.body#>>'{quality,report_format}'='report-aggregate-v1' THEN (
 WITH narrative AS (
  SELECT value,ordinality AS position
  FROM jsonb_array_elements(CASE WHEN jsonb_typeof(c.body->'narrative')='array' THEN c.body->'narrative' ELSE '[]'::jsonb END) WITH ORDINALITY
 ), summaries AS (
  SELECT position,value->>'topic_id' AS topic_id,COALESCE(
   CASE WHEN jsonb_typeof(value->'summary_text')='string' THEN NULLIF(value->>'summary_text','') END,
   CASE WHEN jsonb_typeof(value->'text')='string' THEN NULLIF(value->>'text','') END,
   CASE WHEN jsonb_typeof(value->'observation')='string' THEN NULLIF(value->>'observation','') END) AS text
  FROM narrative
 ), limits AS (
  SELECT 0 AS source,position,value->>'interpretation_limit' AS text FROM narrative
  WHERE jsonb_typeof(value->'interpretation_limit')='string' AND value->>'interpretation_limit'<>''
  UNION ALL
  SELECT 1,ordinality,value#>>'{}' FROM jsonb_array_elements(
   CASE WHEN jsonb_typeof(c.body->'limitations')='array' THEN c.body->'limitations' ELSE '[]'::jsonb END) WITH ORDINALITY
  WHERE jsonb_typeof(value)='string' AND value#>>'{}'<>''
 ), missing AS (
  SELECT topic.ordinality AS topic_order,reason.ordinality AS reason_order,reason.value#>>'{}' AS text
  FROM jsonb_array_elements(CASE WHEN jsonb_typeof(c.body->'topics')='array' THEN c.body->'topics' ELSE '[]'::jsonb END) WITH ORDINALITY AS topic
  CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(topic.value->'missing_inputs')='array' THEN topic.value->'missing_inputs' ELSE '[]'::jsonb END) WITH ORDINALITY AS reason
  WHERE jsonb_typeof(reason.value)='string' AND reason.value#>>'{}'<>''
 )
 SELECT jsonb_build_object(
  'summaries',COALESCE((SELECT jsonb_agg(jsonb_build_object('topic_id',left(topic_id,80),'text',left(text,400)) ORDER BY position)
   FROM (SELECT * FROM summaries WHERE text IS NOT NULL ORDER BY position LIMIT 3) selected),'[]'::jsonb),
  'limitations',COALESCE((SELECT jsonb_agg(left(text,400) ORDER BY source,position)
   FROM (SELECT * FROM limits ORDER BY source,position LIMIT 3) selected),'[]'::jsonb),
  'missing_inputs',COALESCE((SELECT jsonb_agg(left(text,120) ORDER BY topic_order,reason_order)
   FROM (SELECT * FROM missing ORDER BY topic_order,reason_order LIMIT 6) selected),'[]'::jsonb),
  'method',CASE WHEN jsonb_typeof(c.body#>'{quality,report,method}')='string' THEN left(c.body#>>'{quality,report,method}',120) END,
  'narrative_status',CASE WHEN jsonb_typeof(c.body->'narrative_status')='string' THEN left(c.body->>'narrative_status',80) END,
  'truncated',(SELECT count(*)>3 OR COALESCE(bool_or(char_length(text)>400 OR char_length(topic_id)>80),false) FROM summaries WHERE text IS NOT NULL)
   OR (SELECT count(*)>3 OR COALESCE(bool_or(char_length(text)>400),false) FROM limits)
   OR (SELECT count(*)>6 OR COALESCE(bool_or(char_length(text)>120),false) FROM missing)
   OR COALESCE(char_length(c.body#>>'{quality,report,method}')>120,false)
   OR COALESCE(char_length(c.body->>'narrative_status')>80,false)
 )
) ELSE NULL END`
