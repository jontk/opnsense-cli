// list-aliases connects to OPNsense and prints all firewall aliases.
//
// Usage:
//
//	OPNSENSE_URL=https://192.168.1.1 \
//	OPNSENSE_KEY=your-api-key \
//	OPNSENSE_SECRET=your-api-secret \
//	go run ./examples/list-aliases
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/jontk/opnsense-cli/opnsense"
	"github.com/jontk/opnsense-cli/opnsense/firewall"
)

func main() {
	url := requireEnv("OPNSENSE_URL")
	key := requireEnv("OPNSENSE_KEY")
	secret := requireEnv("OPNSENSE_SECRET")

	client := opnsense.NewClient(url, key, secret,
		opnsense.WithInsecureTLS(), // common for self-signed certs
	)
	fw := firewall.NewClient(client)
	ctx := context.Background()

	aliases, err := opnsense.Collect(ctx, 100, func(ctx context.Context, page, rowCount int) (*opnsense.SearchResult[firewall.Alias], error) {
		return fw.AliasSearchItem(ctx, map[string]any{
			"current":  page,
			"rowCount": rowCount,
		})
	})
	if err != nil {
		log.Fatalf("search aliases: %v", err)
	}

	fmt.Printf("%-30s %-10s %-10s %s\n", "NAME", "TYPE", "ENABLED", "DESCRIPTION")
	fmt.Printf("%-30s %-10s %-10s %s\n", "----", "----", "-------", "-----------")
	for _, a := range aliases {
		enabled := "no"
		if a.Enabled.Bool() {
			enabled = "yes"
		}
		fmt.Printf("%-30s %-10s %-10s %s\n", a.Name, a.Type, enabled, a.Description)
	}
	fmt.Printf("\n%d aliases total\n", len(aliases))
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		log.Fatalf("required environment variable %s is not set", key)
	}
	return v
}
