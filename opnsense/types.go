package opnsense

// GenericResponse represents a common OPNsense API response.
type GenericResponse struct {
	Result      string            `json:"result,omitempty"`
	UUID        string            `json:"uuid,omitempty"`
	Validations map[string]string `json:"validations,omitempty"`
}

// SearchResult is a generic paginated search response.
type SearchResult[T any] struct {
	Rows     []T `json:"rows"`
	RowCount int `json:"rowCount"`
	Total    int `json:"total"`
	Current  int `json:"current"`
}

// StatusResponse represents a simple status response.
type StatusResponse struct {
	Status string `json:"status"`
}
