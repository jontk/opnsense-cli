package opnsense

import (
	"encoding/json"
	"strconv"
	"strings"
)

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

// OPNBool is a boolean that marshals to/from OPNsense's "0"/"1" string format.
type OPNBool bool

// MarshalJSON encodes the boolean as "1" or "0".
func (b OPNBool) MarshalJSON() ([]byte, error) {
	if b {
		return []byte(`"1"`), nil
	}
	return []byte(`"0"`), nil
}

// UnmarshalJSON decodes "1", "true", "yes" as true; everything else as false.
func (b *OPNBool) UnmarshalJSON(data []byte) error {
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		// Try native bool as fallback
		var native bool
		if err2 := json.Unmarshal(data, &native); err2 != nil {
			return err
		}
		*b = OPNBool(native)
		return nil
	}
	s = strings.TrimSpace(s)
	*b = OPNBool(s == "1" || strings.EqualFold(s, "true") || strings.EqualFold(s, "yes"))
	return nil
}

// Bool returns the underlying bool value.
func (b OPNBool) Bool() bool { return bool(b) }

// OPNInt is an integer that marshals to/from OPNsense's string format.
type OPNInt int

// MarshalJSON encodes the integer as a string (e.g., 80 → "80").
func (n OPNInt) MarshalJSON() ([]byte, error) {
	return json.Marshal(strconv.Itoa(int(n)))
}

// UnmarshalJSON decodes a string-encoded integer (e.g., "80" → 80).
func (n *OPNInt) UnmarshalJSON(data []byte) error {
	var s string
	if err := json.Unmarshal(data, &s); err != nil {
		// Try native number as fallback
		var native int
		if err2 := json.Unmarshal(data, &native); err2 != nil {
			return err
		}
		*n = OPNInt(native)
		return nil
	}
	s = strings.TrimSpace(s)
	if s == "" {
		*n = 0
		return nil
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return err
	}
	*n = OPNInt(v)
	return nil
}

// Int returns the underlying int value.
func (n OPNInt) Int() int { return int(n) }

// BoolPtr returns a pointer to an OPNBool. Useful for optional fields.
func BoolPtr(v bool) *OPNBool {
	b := OPNBool(v)
	return &b
}

// IntPtr returns a pointer to an OPNInt. Useful for optional fields.
func IntPtr(v int) *OPNInt {
	n := OPNInt(v)
	return &n
}
