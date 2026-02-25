package cli

import (
	"github.com/jontk/opnsense-cli/opnsense"
	"github.com/spf13/cobra"
)

// NewClientFromCmd builds an opnsense.Client from resolved config flags.
func NewClientFromCmd(cmd *cobra.Command) (*opnsense.Client, *Config, error) {
	cfg, err := ConfigFromCmd(cmd)
	if err != nil {
		return nil, nil, err
	}

	opts := []opnsense.Option{
		opnsense.WithTimeout(cfg.Timeout),
	}
	if cfg.Insecure {
		opts = append(opts, opnsense.WithInsecureTLS())
	}

	c := opnsense.NewClient(cfg.URL, cfg.APIKey, cfg.APISecret, opts...)
	return c, cfg, nil
}
