package cli

import (
	"testing"
	"time"

	"github.com/spf13/cobra"
)

func TestConfigFromCmd_flagsOverEnv(t *testing.T) {
	t.Setenv("OPNSENSE_URL", "http://from-env")
	t.Setenv("OPNSENSE_KEY", "env-key")
	t.Setenv("OPNSENSE_SECRET", "env-secret")

	cmd := &cobra.Command{}
	cmd.PersistentFlags().String("url", "", "")
	cmd.PersistentFlags().String("api-key", "", "")
	cmd.PersistentFlags().String("api-secret", "", "")
	cmd.PersistentFlags().StringP("output", "o", "table", "")
	cmd.PersistentFlags().Bool("insecure", false, "")
	cmd.PersistentFlags().Duration("timeout", 30*time.Second, "")

	// Explicitly set flags override env vars
	if err := cmd.ParseFlags([]string{"--url=http://from-flag", "--api-key=flag-key", "--api-secret=flag-secret"}); err != nil {
		t.Fatal(err)
	}

	cfg, err := ConfigFromCmd(cmd)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.URL != "http://from-flag" {
		t.Errorf("expected http://from-flag, got %s", cfg.URL)
	}
	if cfg.APIKey != "flag-key" {
		t.Errorf("expected flag-key, got %s", cfg.APIKey)
	}
}

func TestConfigFromCmd_envFallback(t *testing.T) {
	t.Setenv("OPNSENSE_URL", "http://env-url")
	t.Setenv("OPNSENSE_KEY", "env-key")
	t.Setenv("OPNSENSE_SECRET", "env-secret")

	cmd := &cobra.Command{}
	cmd.PersistentFlags().String("url", "", "")
	cmd.PersistentFlags().String("api-key", "", "")
	cmd.PersistentFlags().String("api-secret", "", "")
	cmd.PersistentFlags().StringP("output", "o", "table", "")
	cmd.PersistentFlags().Bool("insecure", false, "")
	cmd.PersistentFlags().Duration("timeout", 30*time.Second, "")

	cfg, err := ConfigFromCmd(cmd)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.URL != "http://env-url" {
		t.Errorf("expected http://env-url, got %s", cfg.URL)
	}
	if cfg.APIKey != "env-key" {
		t.Errorf("expected env-key, got %s", cfg.APIKey)
	}
}

func TestConfigFromCmd_missingRequired(t *testing.T) {
	t.Setenv("OPNSENSE_URL", "")
	t.Setenv("OPNSENSE_KEY", "")
	t.Setenv("OPNSENSE_SECRET", "")

	cmd := &cobra.Command{}
	cmd.PersistentFlags().String("url", "", "")
	cmd.PersistentFlags().String("api-key", "", "")
	cmd.PersistentFlags().String("api-secret", "", "")
	cmd.PersistentFlags().StringP("output", "o", "table", "")
	cmd.PersistentFlags().Bool("insecure", false, "")
	cmd.PersistentFlags().Duration("timeout", 30*time.Second, "")

	_, err := ConfigFromCmd(cmd)
	if err == nil {
		t.Error("expected error for missing required fields, got nil")
	}
}

func TestConfigFromCmd_defaults(t *testing.T) {
	t.Setenv("OPNSENSE_URL", "http://test")
	t.Setenv("OPNSENSE_KEY", "key")
	t.Setenv("OPNSENSE_SECRET", "secret")

	cmd := &cobra.Command{}
	cmd.PersistentFlags().String("url", "", "")
	cmd.PersistentFlags().String("api-key", "", "")
	cmd.PersistentFlags().String("api-secret", "", "")
	cmd.PersistentFlags().StringP("output", "o", "table", "")
	cmd.PersistentFlags().Bool("insecure", false, "")
	cmd.PersistentFlags().Duration("timeout", 30*time.Second, "")

	cfg, err := ConfigFromCmd(cmd)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.Output != "table" {
		t.Errorf("expected default output 'table', got %s", cfg.Output)
	}
	if cfg.Insecure {
		t.Error("expected insecure=false by default")
	}
	if cfg.Timeout != 30*time.Second {
		t.Errorf("expected 30s timeout, got %v", cfg.Timeout)
	}
}
