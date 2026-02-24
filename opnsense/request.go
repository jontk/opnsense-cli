package opnsense

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math/rand/v2"
	"net/http"
	"time"
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

// Do executes an API request. If WithRetry was configured, transient errors
// (5xx responses and network errors) are retried with exponential backoff.
//
//   - method: HTTP method (GET, POST, etc.)
//   - path: API path (e.g. /api/firewall/alias/addItem)
//   - body: request body to JSON-encode (nil for GET requests)
//   - resp: pointer to decode JSON response into (can be nil to discard)
func (c *Client) Do(ctx context.Context, method, path string, body, resp any) error {
	// Pre-marshal body so it can be re-read on retry.
	var bodyData []byte
	if body != nil {
		var err error
		bodyData, err = json.Marshal(body)
		if err != nil {
			return fmt.Errorf("opnsense: marshal request body: %w", err)
		}
	}

	var lastErr error
	attempts := 1 + c.maxRetries
	for attempt := range attempts {
		lastErr = c.do(ctx, method, path, bodyData, resp)
		if lastErr == nil {
			return nil
		}
		if attempt == attempts-1 {
			break
		}
		if !isRetryable(lastErr) {
			return lastErr
		}
		delay := c.backoff(attempt)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(delay):
		}
	}
	return lastErr
}

func (c *Client) do(ctx context.Context, method, path string, bodyData []byte, resp any) error {
	url := c.baseURL + path

	var bodyReader io.Reader
	if bodyData != nil {
		bodyReader = bytes.NewReader(bodyData)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, bodyReader)
	if err != nil {
		return fmt.Errorf("opnsense: create request: %w", err)
	}

	req.SetBasicAuth(c.apiKey, c.apiSecret)

	if bodyData != nil {
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

// isRetryable returns true for transient errors: 5xx API errors and network errors.
func isRetryable(err error) bool {
	if apiErr, ok := err.(*APIError); ok {
		return apiErr.StatusCode >= 500
	}
	// Network errors (wrapped by Do) are retryable
	return true
}

// backoff returns the delay for the given attempt (0-indexed) using exponential
// backoff with jitter: base * 2^attempt * (0.5 + rand(0, 0.5)).
func (c *Client) backoff(attempt int) time.Duration {
	delay := c.retryDelay
	for range attempt {
		delay *= 2
	}
	// Add jitter: 50-100% of the computed delay
	jitter := 0.5 + rand.Float64()*0.5
	return time.Duration(float64(delay) * jitter)
}
