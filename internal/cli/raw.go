package cli

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/spf13/cobra"
)

func init() {
	rawCmd := &cobra.Command{
		Use:   "raw <METHOD> <PATH>",
		Short: "Send a raw API request",
		Long: `Send a raw HTTP request to the OPNsense API and print the JSON response.

Examples:
  opn raw GET /api/firewall/alias/searchItem
  opn raw POST /api/firewall/alias/addItem --data '{"alias":{"name":"test"}}'
  echo '{"alias":{"name":"test"}}' | opn raw POST /api/firewall/alias/addItem --data -`,
		Args:    cobra.ExactArgs(2),
		RunE:    runRaw,
		Example: `  opn raw GET /api/core/firmware/info`,
	}
	rawCmd.Flags().String("data", "", "JSON body for POST requests (use '-' to read from stdin)")
	Root.AddCommand(rawCmd)
}

func runRaw(cmd *cobra.Command, args []string) error {
	method := strings.ToUpper(args[0])
	path := args[1]

	c, cfg, err := NewClientFromCmd(cmd)
	if err != nil {
		return err
	}

	var body any
	dataFlag, _ := cmd.Flags().GetString("data")
	if dataFlag != "" {
		raw := dataFlag
		if raw == "-" {
			b, err := io.ReadAll(os.Stdin)
			if err != nil {
				return fmt.Errorf("reading stdin: %w", err)
			}
			raw = string(b)
		}
		if err := json.Unmarshal([]byte(raw), &body); err != nil {
			return fmt.Errorf("parsing --data JSON: %w", err)
		}
	}

	var resp map[string]any
	if err := c.Do(cmd.Context(), method, path, body, &resp); err != nil {
		return err
	}

	printer := NewPrinter(cfg)
	return printer.PrintJSON(resp)
}
