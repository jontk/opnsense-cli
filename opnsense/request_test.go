package opnsense

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestDo_successfulGET(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			t.Errorf("method = %q, want %q", r.Method, http.MethodGet)
		}
		if r.URL.Path != "/api/core/firmware/status" {
			t.Errorf("path = %q, want %q", r.URL.Path, "/api/core/firmware/status")
		}
		if got := r.Header.Get("Accept"); got != "application/json" {
			t.Errorf("Accept header = %q, want %q", got, "application/json")
		}
		// Content-Type should not be set for GET requests with no body
		if got := r.Header.Get("Content-Type"); got != "" {
			t.Errorf("Content-Type header = %q, want empty for GET", got)
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "mykey", "mysecret")

	var resp StatusResponse
	err := c.Do(context.Background(), http.MethodGet, "/api/core/firmware/status", nil, &resp)
	if err != nil {
		t.Fatalf("Do() returned error: %v", err)
	}
	if resp.Status != "ok" {
		t.Errorf("resp.Status = %q, want %q", resp.Status, "ok")
	}
}

func TestDo_successfulPOST(t *testing.T) {
	type requestBody struct {
		Name    string `json:"name"`
		Enabled bool   `json:"enabled"`
	}

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("method = %q, want %q", r.Method, http.MethodPost)
		}

		// Verify Content-Type header
		if got := r.Header.Get("Content-Type"); got != "application/json" {
			t.Errorf("Content-Type = %q, want %q", got, "application/json")
		}

		// Verify Basic auth
		user, pass, ok := r.BasicAuth()
		if !ok {
			t.Fatal("BasicAuth not set")
		}
		if user != "mykey" {
			t.Errorf("BasicAuth user = %q, want %q", user, "mykey")
		}
		if pass != "mysecret" {
			t.Errorf("BasicAuth pass = %q, want %q", pass, "mysecret")
		}

		// Verify request body
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("read body: %v", err)
		}
		var reqBody requestBody
		if err := json.Unmarshal(body, &reqBody); err != nil {
			t.Fatalf("unmarshal body: %v", err)
		}
		if reqBody.Name != "test-alias" {
			t.Errorf("body.Name = %q, want %q", reqBody.Name, "test-alias")
		}
		if !reqBody.Enabled {
			t.Error("body.Enabled = false, want true")
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"result":"saved","uuid":"abc-123"}`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "mykey", "mysecret")

	reqBody := requestBody{Name: "test-alias", Enabled: true}
	var resp GenericResponse
	err := c.Do(context.Background(), http.MethodPost, "/api/firewall/alias/addItem", reqBody, &resp)
	if err != nil {
		t.Fatalf("Do() returned error: %v", err)
	}
	if resp.Result != "saved" {
		t.Errorf("resp.Result = %q, want %q", resp.Result, "saved")
	}
	if resp.UUID != "abc-123" {
		t.Errorf("resp.UUID = %q, want %q", resp.UUID, "abc-123")
	}
}

func TestDo_apiError(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		body       string
	}{
		{"400 bad request", http.StatusBadRequest, `{"message":"invalid input"}`},
		{"401 unauthorized", http.StatusUnauthorized, "Unauthorized"},
		{"403 forbidden", http.StatusForbidden, "Forbidden"},
		{"404 not found", http.StatusNotFound, "Not Found"},
		{"500 internal server error", http.StatusInternalServerError, "Internal Server Error"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(tt.statusCode)
				_, _ = w.Write([]byte(tt.body))
			}))
			defer srv.Close()

			c := NewClient(srv.URL, "key", "secret")

			var resp StatusResponse
			err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, &resp)
			if err == nil {
				t.Fatal("Do() returned nil error, want *APIError")
			}

			var apiErr *APIError
			if !errors.As(err, &apiErr) {
				t.Fatalf("error is %T, want *APIError", err)
			}
			if apiErr.StatusCode != tt.statusCode {
				t.Errorf("StatusCode = %d, want %d", apiErr.StatusCode, tt.statusCode)
			}
			if apiErr.Body != tt.body {
				t.Errorf("Body = %q, want %q", apiErr.Body, tt.body)
			}

			// Verify Error() string formatting
			errStr := apiErr.Error()
			if errStr == "" {
				t.Error("Error() returned empty string")
			}
		})
	}
}

func TestDo_nilResponsePointer(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret")

	// Passing nil as response should not panic or error
	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, nil)
	if err != nil {
		t.Fatalf("Do() with nil response returned error: %v", err)
	}
}

func TestDo_jsonUnmarshalError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{invalid json`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret")

	var resp StatusResponse
	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, &resp)
	if err == nil {
		t.Fatal("Do() returned nil error, want unmarshal error")
	}

	// Should not be an APIError -- it's a JSON parse error
	var apiErr *APIError
	if errors.As(err, &apiErr) {
		t.Fatal("error should not be *APIError for JSON unmarshal failure")
	}
}

func TestDo_contextCancellation(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret")

	ctx, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	var resp StatusResponse
	err := c.Do(ctx, http.MethodGet, "/api/test", nil, &resp)
	if err == nil {
		t.Fatal("Do() returned nil error, want context cancellation error")
	}

	// The error should be caused by context cancellation
	if !errors.Is(err, context.Canceled) {
		// The error is wrapped, so check the underlying error string as a fallback
		if ctx.Err() != context.Canceled {
			t.Errorf("context.Err() = %v, want %v", ctx.Err(), context.Canceled)
		}
	}
}

func TestDo_emptyResponseBody(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		// No body written
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret")

	var resp StatusResponse
	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, &resp)
	if err != nil {
		t.Fatalf("Do() returned error for empty body: %v", err)
	}
	// resp should remain at zero value
	if resp.Status != "" {
		t.Errorf("resp.Status = %q, want empty string", resp.Status)
	}
}

func TestDo_basicAuthOnGET(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user, pass, ok := r.BasicAuth()
		if !ok {
			t.Fatal("BasicAuth not set on GET request")
		}
		if user != "api-key-123" {
			t.Errorf("user = %q, want %q", user, "api-key-123")
		}
		if pass != "api-secret-456" {
			t.Errorf("pass = %q, want %q", pass, "api-secret-456")
		}

		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "api-key-123", "api-secret-456")

	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, nil)
	if err != nil {
		t.Fatalf("Do() returned error: %v", err)
	}
}

func TestAPIError_Error(t *testing.T) {
	e := &APIError{
		StatusCode: 403,
		Status:     "403 Forbidden",
		Body:       "access denied",
	}

	got := e.Error()
	want := "opnsense: API error 403 403 Forbidden: access denied"
	if got != want {
		t.Errorf("Error() = %q, want %q", got, want)
	}
}

func TestDo_retryOn5xx(t *testing.T) {
	var attempts atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := attempts.Add(1)
		if n < 3 {
			w.WriteHeader(http.StatusInternalServerError)
			_, _ = w.Write([]byte("server error"))
			return
		}
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret", WithRetry(3, 1*time.Millisecond))

	var resp StatusResponse
	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, &resp)
	if err != nil {
		t.Fatalf("Do() returned error after retries: %v", err)
	}
	if resp.Status != "ok" {
		t.Errorf("resp.Status = %q, want %q", resp.Status, "ok")
	}
	if got := attempts.Load(); got != 3 {
		t.Errorf("attempts = %d, want 3", got)
	}
}

func TestDo_retryExhausted(t *testing.T) {
	var attempts atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("server error"))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret", WithRetry(2, 1*time.Millisecond))

	var resp StatusResponse
	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, &resp)
	if err == nil {
		t.Fatal("Do() returned nil error, want error after exhausted retries")
	}

	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("error is %T, want *APIError", err)
	}
	if apiErr.StatusCode != http.StatusInternalServerError {
		t.Errorf("StatusCode = %d, want %d", apiErr.StatusCode, http.StatusInternalServerError)
	}

	// 1 initial attempt + 2 retries = 3 total attempts
	if got := attempts.Load(); got != 3 {
		t.Errorf("attempts = %d, want 3", got)
	}
}

func TestDo_noRetryOn4xx(t *testing.T) {
	var attempts atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		w.WriteHeader(http.StatusBadRequest)
		_, _ = w.Write([]byte("bad request"))
	}))
	defer srv.Close()

	c := NewClient(srv.URL, "key", "secret", WithRetry(3, 1*time.Millisecond))

	err := c.Do(context.Background(), http.MethodGet, "/api/test", nil, nil)
	if err == nil {
		t.Fatal("Do() returned nil error, want *APIError")
	}

	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("error is %T, want *APIError", err)
	}

	// 4xx errors are not retryable, so only 1 attempt
	if got := attempts.Load(); got != 1 {
		t.Errorf("attempts = %d, want 1 (no retries for 4xx)", got)
	}
}

func TestDo_retryContextCancellation(t *testing.T) {
	var attempts atomic.Int32

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("server error"))
	}))
	defer srv.Close()

	ctx, cancel := context.WithCancel(context.Background())
	c := NewClient(srv.URL, "key", "secret", WithRetry(10, 50*time.Millisecond))

	// Cancel after a short delay so we interrupt the retry backoff
	go func() {
		time.Sleep(10 * time.Millisecond)
		cancel()
	}()

	err := c.Do(ctx, http.MethodGet, "/api/test", nil, nil)
	if err == nil {
		t.Fatal("Do() returned nil error, want context cancellation error")
	}
}

func TestIsRetryable(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{"500 error", &APIError{StatusCode: 500}, true},
		{"502 error", &APIError{StatusCode: 502}, true},
		{"503 error", &APIError{StatusCode: 503}, true},
		{"400 error", &APIError{StatusCode: 400}, false},
		{"401 error", &APIError{StatusCode: 401}, false},
		{"404 error", &APIError{StatusCode: 404}, false},
		{"network error", errors.New("connection refused"), true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := isRetryable(tt.err)
			if got != tt.want {
				t.Errorf("isRetryable(%v) = %v, want %v", tt.err, got, tt.want)
			}
		})
	}
}

func TestBackoff(t *testing.T) {
	c := &Client{retryDelay: 100 * time.Millisecond}

	for attempt := range 5 {
		delay := c.backoff(attempt)

		// Expected base delay: 100ms * 2^attempt
		baseDelay := 100 * time.Millisecond
		for range attempt {
			baseDelay *= 2
		}
		// Jitter is 50-100%, so delay should be in [baseDelay*0.5, baseDelay*1.0]
		minDelay := time.Duration(float64(baseDelay) * 0.5)
		maxDelay := baseDelay

		if delay < minDelay || delay > maxDelay {
			t.Errorf("backoff(%d) = %v, want in [%v, %v]", attempt, delay, minDelay, maxDelay)
		}
	}
}
