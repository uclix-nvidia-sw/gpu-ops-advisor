package migrations

import _ "embed"

//go:embed 004_incident.sql
var Incident string

//go:embed 005_incident_episodes.sql
var IncidentEpisodes string
