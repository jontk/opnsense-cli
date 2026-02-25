package cli

import (
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"
)

// Config holds resolved connection settings.
type Config struct {
	URL       string
	APIKey    string
	APISecret string
	Output    string
	Insecure  bool
	Timeout   time.Duration
}

// ConfigFromCmd resolves connection settings using flag > env var > default priority.
func ConfigFromCmd(cmd *cobra.Command) (*Config, error) {
	url := flagOrEnv(cmd, "url", "OPNSENSE_URL")
	key := flagOrEnv(cmd, "api-key", "OPNSENSE_KEY")
	secret := flagOrEnv(cmd, "api-secret", "OPNSENSE_SECRET")

	if url == "" {
		return nil, fmt.Errorf("--url or OPNSENSE_URL is required")
	}
	if key == "" {
		return nil, fmt.Errorf("--api-key or OPNSENSE_KEY is required")
	}
	if secret == "" {
		return nil, fmt.Errorf("--api-secret or OPNSENSE_SECRET is required")
	}

	output, _ := cmd.Flags().GetString("output")
	insecure, _ := cmd.Flags().GetBool("insecure")
	timeout, _ := cmd.Flags().GetDuration("timeout")

	return &Config{
		URL:       url,
		APIKey:    key,
		APISecret: secret,
		Output:    output,
		Insecure:  insecure,
		Timeout:   timeout,
	}, nil
}

// flagOrEnv returns the flag value if explicitly set, otherwise the env var value.
func flagOrEnv(cmd *cobra.Command, flagName, envVar string) string {
	if f := cmd.Flags().Lookup(flagName); f != nil && f.Changed {
		return f.Value.String()
	}
	if f := cmd.InheritedFlags().Lookup(flagName); f != nil && f.Changed {
		return f.Value.String()
	}
	return os.Getenv(envVar)
}
