package opnsense

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// APIError represents an error response from the OPNsense API.
type APIError struct {
	StatusCode int
	Status     string
	Body       string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("opnsense: API error %d %s: %s", e.StatusCode, e.Status, e.Body)
}

// Do executes an API request.
//
//   - method: HTTP method (GET, POST, etc.)
//   - path: API path (e.g. /api/firewall/alias/addItem)
//   - body: request body to JSON-encode (nil for GET requests)
//   - resp: pointer to decode JSON response into (can be nil to discard)
func (c *Client) Do(ctx context.Context, method, path string, body, resp any) error {
	url := c.baseURL + path

	var bodyReader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("opnsense: marshal request body: %w", err)
		}
		bodyReader = bytes.NewReader(data)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, bodyReader)
	if err != nil {
		return fmt.Errorf("opnsense: create request: %w", err)
	}

	// Basic auth with API key/secret
	req.SetBasicAuth(c.apiKey, c.apiSecret)

	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	req.Header.Set("Accept", "application/json")

	httpResp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("opnsense: execute request: %w", err)
	}
	defer httpResp.Body.Close()

	respBody, err := io.ReadAll(httpResp.Body)
	if err != nil {
		return fmt.Errorf("opnsense: read response body: %w", err)
	}

	if httpResp.StatusCode < 200 || httpResp.StatusCode >= 300 {
		return &APIError{
			StatusCode: httpResp.StatusCode,
			Status:     httpResp.Status,
			Body:       string(respBody),
		}
	}

	if resp != nil && len(respBody) > 0 {
		if err := json.Unmarshal(respBody, resp); err != nil {
			return fmt.Errorf("opnsense: unmarshal response: %w", err)
		}
	}

	return nil
}
