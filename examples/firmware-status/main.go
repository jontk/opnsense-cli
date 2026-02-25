// firmware-status checks the OPNsense firmware update status.
//
// Usage:
//
//	OPNSENSE_URL=https://192.168.1.1 \
//	OPNSENSE_KEY=your-api-key \
//	OPNSENSE_SECRET=your-api-secret \
//	go run ./examples/firmware-status
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/jontk/opnsense-cli/opnsense"
	"github.com/jontk/opnsense-cli/opnsense/firmware"
)

func main() {
	url := requireEnv("OPNSENSE_URL")
	key := requireEnv("OPNSENSE_KEY")
	secret := requireEnv("OPNSENSE_SECRET")

	client := opnsense.NewClient(url, key, secret,
		opnsense.WithInsecureTLS(), // common for self-signed certs
	)
	fw := firmware.NewClient(client)
	ctx := context.Background()

	// Get current firmware info
	infoRaw, err := fw.FirmwareInfo(ctx)
	if err != nil {
		log.Fatalf("firmware info: %v", err)
	}
	info, _ := infoRaw.(map[string]any)

	if productVersion, ok := info["product_version"].(string); ok {
		fmt.Printf("Current version : %s\n", productVersion)
	}
	if productName, ok := info["product_name"].(string); ok {
		fmt.Printf("Product         : %s\n", productName)
	}
	if arch, ok := info["product_arch"].(string); ok {
		fmt.Printf("Architecture    : %s\n", arch)
	}

	// Check for available updates
	fmt.Println("\nChecking for updates...")
	statusRaw, err := fw.FirmwareStatus(ctx, nil)
	if err != nil {
		log.Fatalf("firmware status: %v", err)
	}
	status, _ := statusRaw.(map[string]any)

	if statusStr, ok := status["status"].(string); ok {
		fmt.Printf("Update status   : %s\n", statusStr)
	}
	if upToDate, ok := status["product_version"].(string); ok {
		fmt.Printf("Latest version  : %s\n", upToDate)
	}

	// List available package updates if any
	if updates, ok := status["updates"].(float64); ok && updates > 0 {
		fmt.Printf("\n%d package update(s) available\n", int(updates))
	} else {
		fmt.Println("\nSystem is up to date.")
	}
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		log.Fatalf("required environment variable %s is not set", key)
	}
	return v
}
