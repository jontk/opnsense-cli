package cli

import (
	"fmt"

	"github.com/spf13/cobra"
)

// Version is set via -ldflags at build time.
var Version = "dev"

func init() {
	Root.AddCommand(&cobra.Command{
		Use:   "version",
		Short: "Print the opn version",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Fprintln(cmd.OutOrStdout(), "opn", Version)
		},
	})
}
