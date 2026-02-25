package cli

import (
	"os"

	"github.com/spf13/cobra"
)

// Root is the top-level cobra command. Generated module files register themselves
// to this command via init() in the gen sub-package.
var Root = &cobra.Command{
	Use:          "opn",
	Short:        "OPNsense CLI — manage your firewall from the command line",
	SilenceUsage: true,
}

func init() {
	Root.PersistentFlags().String("url", "", "OPNsense base URL (env: OPNSENSE_URL)")
	Root.PersistentFlags().String("api-key", "", "API key (env: OPNSENSE_KEY)")
	Root.PersistentFlags().String("api-secret", "", "API secret (env: OPNSENSE_SECRET)")
	Root.PersistentFlags().StringP("output", "o", "table", "Output format: table, json, yaml")
	Root.PersistentFlags().Bool("insecure", false, "Skip TLS certificate verification")
	Root.PersistentFlags().Duration("timeout", 30e9, "HTTP request timeout")
}

// Execute runs the root command.
func Execute() {
	if err := Root.Execute(); err != nil {
		os.Exit(1)
	}
}
