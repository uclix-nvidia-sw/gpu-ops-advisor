package controller

import . "gpu-ops-advisor/shared/contract"

func supportedContract(kind, version string) bool {
	return (kind == "rca" || kind == "report") && (version == "1.3" || kind == "rca" && (version == "1.4" || version == "1.5"))
}

// Only absence is legacy; explicit null, empty and unknown versions are errors.
func inputContract(kind string, versions Object) (string, error) {
	version := "1.3"
	if _, exists := versions["input_contract"]; exists {
		version = String(versions, "input_contract")
	}
	if !supportedContract(kind, version) {
		return "", Invalid("versions.input_contract")
	}
	return version, nil
}

// Keep the SQL fallback identical to inputContract without rewriting old jobs.
const jobContractSQL = `(CASE WHEN j.versions ? 'input_contract' THEN j.versions->>'input_contract' ELSE '1.3' END)`

func candidateContractMatches(job, candidate Object) bool {
	kind := String(job, "kind")
	versions, _ := job["versions"].(map[string]any)
	want, err := inputContract(kind, versions)
	if err != nil {
		return false
	}
	body, ok := candidate["body"].(map[string]any)
	if !ok {
		return false
	}
	resultVersions, ok := body["versions"].(map[string]any)
	if _, exists := body["versions"]; exists && !ok {
		return false
	}
	got, err := inputContract(kind, resultVersions)
	return err == nil && got == want
}
