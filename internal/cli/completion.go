package cli

import (
	"github.com/spf13/cobra"
)

func init() {
	Root.AddCommand(&cobra.Command{
		Use:   "completion [bash|zsh|fish|powershell]",
		Short: "Generate shell completion script",
		Long: `Generate a shell completion script for opn.

To load completions:

Bash:
  $ source <(opn completion bash)

Zsh:
  $ opn completion zsh > "${fpath[1]}/_opn"

Fish:
  $ opn completion fish | source

Powershell:
  PS> opn completion powershell | Out-String | Invoke-Expression
`,
		ValidArgs:             []string{"bash", "zsh", "fish", "powershell"},
		Args:                  cobra.ExactArgs(1),
		DisableFlagsInUseLine: true,
		RunE: func(cmd *cobra.Command, args []string) error {
			switch args[0] {
			case "bash":
				return Root.GenBashCompletion(cmd.OutOrStdout())
			case "zsh":
				return Root.GenZshCompletion(cmd.OutOrStdout())
			case "fish":
				return Root.GenFishCompletion(cmd.OutOrStdout(), true)
			case "powershell":
				return Root.GenPowerShellCompletionWithDesc(cmd.OutOrStdout())
			}
			return nil
		},
	})
}
