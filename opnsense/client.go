package opnsense

import (
	"crypto/tls"
	"net/http"
	"strings"
	"time"
)

// Client is the base HTTP client for the OPNsense API.
type Client struct {
	baseURL    string
	apiKey     string
	apiSecret  string
	httpClient *http.Client
}

// NewClient creates a new OPNsense API client.
func NewClient(baseURL, apiKey, apiSecret string, opts ...Option) *Client {
	baseURL = strings.TrimRight(baseURL, "/")

	c := &Client{
		baseURL:   baseURL,
		apiKey:    apiKey,
		apiSecret: apiSecret,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}

	for _, opt := range opts {
		opt(c)
	}

	return c
}

// BaseURL returns the configured base URL.
func (c *Client) BaseURL() string {
	return c.baseURL
}

// HTTPClient returns the underlying http.Client.
func (c *Client) HTTPClient() *http.Client {
	return c.httpClient
}

// SetHTTPClient replaces the underlying http.Client. Use WithHTTPClient option
// at construction time if possible.
func (c *Client) SetHTTPClient(hc *http.Client) {
	c.httpClient = hc
}

// Option configures a Client.
type Option func(*Client)

// WithHTTPClient sets a custom http.Client.
func WithHTTPClient(hc *http.Client) Option {
	return func(c *Client) {
		c.httpClient = hc
	}
}

// WithInsecureTLS disables TLS certificate verification.
func WithInsecureTLS() Option {
	return func(c *Client) {
		transport := http.DefaultTransport.(*http.Transport).Clone()
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} //nolint:gosec
		c.httpClient.Transport = transport
	}
}

// WithTimeout sets the HTTP client timeout.
func WithTimeout(d time.Duration) Option {
	return func(c *Client) {
		c.httpClient.Timeout = d
	}
}
