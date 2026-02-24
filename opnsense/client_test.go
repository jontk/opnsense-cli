package opnsense

import (
	"crypto/tls"
	"net/http"
	"testing"
	"time"
)

func TestNewClient_defaults(t *testing.T) {
	c := NewClient("https://fw.example.com", "key", "secret")

	if got := c.BaseURL(); got != "https://fw.example.com" {
		t.Errorf("BaseURL() = %q, want %q", got, "https://fw.example.com")
	}
	if c.apiKey != "key" {
		t.Errorf("apiKey = %q, want %q", c.apiKey, "key")
	}
	if c.apiSecret != "secret" {
		t.Errorf("apiSecret = %q, want %q", c.apiSecret, "secret")
	}
	if c.HTTPClient() == nil {
		t.Fatal("HTTPClient() returned nil")
	}
	if got := c.HTTPClient().Timeout; got != 30*time.Second {
		t.Errorf("default Timeout = %v, want %v", got, 30*time.Second)
	}
}

func TestNewClient_trailingSlash(t *testing.T) {
	tests := []struct {
		name    string
		baseURL string
		want    string
	}{
		{"no trailing slash", "https://fw.example.com", "https://fw.example.com"},
		{"single trailing slash", "https://fw.example.com/", "https://fw.example.com"},
		{"multiple trailing slashes", "https://fw.example.com///", "https://fw.example.com"},
		{"with path and trailing slash", "https://fw.example.com/api/", "https://fw.example.com/api"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := NewClient(tt.baseURL, "key", "secret")
			if got := c.BaseURL(); got != tt.want {
				t.Errorf("BaseURL() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestWithInsecureTLS(t *testing.T) {
	c := NewClient("https://fw.example.com", "key", "secret", WithInsecureTLS())

	transport, ok := c.HTTPClient().Transport.(*http.Transport)
	if !ok {
		t.Fatal("Transport is not *http.Transport")
	}
	if transport.TLSClientConfig == nil {
		t.Fatal("TLSClientConfig is nil")
	}
	if !transport.TLSClientConfig.InsecureSkipVerify {
		t.Error("InsecureSkipVerify = false, want true")
	}
}

func TestWithTimeout(t *testing.T) {
	c := NewClient("https://fw.example.com", "key", "secret", WithTimeout(60*time.Second))

	if got := c.HTTPClient().Timeout; got != 60*time.Second {
		t.Errorf("Timeout = %v, want %v", got, 60*time.Second)
	}
}

func TestWithHTTPClient(t *testing.T) {
	custom := &http.Client{Timeout: 99 * time.Second}
	c := NewClient("https://fw.example.com", "key", "secret", WithHTTPClient(custom))

	if c.HTTPClient() != custom {
		t.Error("HTTPClient() does not return the custom client")
	}
	if got := c.HTTPClient().Timeout; got != 99*time.Second {
		t.Errorf("Timeout = %v, want %v", got, 99*time.Second)
	}
}

func TestWithMultipleOptions(t *testing.T) {
	c := NewClient(
		"https://fw.example.com/",
		"key",
		"secret",
		WithTimeout(10*time.Second),
		WithInsecureTLS(),
	)

	if got := c.BaseURL(); got != "https://fw.example.com" {
		t.Errorf("BaseURL() = %q, want %q", got, "https://fw.example.com")
	}
	if got := c.HTTPClient().Timeout; got != 10*time.Second {
		t.Errorf("Timeout = %v, want %v", got, 10*time.Second)
	}
	transport, ok := c.HTTPClient().Transport.(*http.Transport)
	if !ok {
		t.Fatal("Transport is not *http.Transport")
	}
	if !transport.TLSClientConfig.InsecureSkipVerify {
		t.Error("InsecureSkipVerify = false, want true")
	}
}

func TestSetHTTPClient(t *testing.T) {
	c := NewClient("https://fw.example.com", "key", "secret")
	original := c.HTTPClient()

	custom := &http.Client{
		Timeout: 120 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true}, //nolint:gosec
		},
	}
	c.SetHTTPClient(custom)

	if c.HTTPClient() == original {
		t.Error("HTTPClient() still returns the original client after SetHTTPClient")
	}
	if c.HTTPClient() != custom {
		t.Error("HTTPClient() does not return the custom client")
	}
	if got := c.HTTPClient().Timeout; got != 120*time.Second {
		t.Errorf("Timeout = %v, want %v", got, 120*time.Second)
	}
}

func TestNewClient_defaultRetry(t *testing.T) {
	c := NewClient("https://fw.example.com", "key", "secret")
	if c.maxRetries != 0 {
		t.Errorf("default maxRetries = %d, want 0", c.maxRetries)
	}
	if c.retryDelay != 0 {
		t.Errorf("default retryDelay = %v, want 0", c.retryDelay)
	}
}

func TestWithRetry(t *testing.T) {
	c := NewClient("https://fw.example.com", "key", "secret",
		WithRetry(3, 500*time.Millisecond))

	if c.maxRetries != 3 {
		t.Errorf("maxRetries = %d, want 3", c.maxRetries)
	}
	if c.retryDelay != 500*time.Millisecond {
		t.Errorf("retryDelay = %v, want %v", c.retryDelay, 500*time.Millisecond)
	}
}
