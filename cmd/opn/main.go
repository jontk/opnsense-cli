package main

import (
	"github.com/jontk/opnsense-cli/internal/cli"
	// Blank import triggers init() in each generated module file, registering
	// all module commands to cli.Root.
	_ "github.com/jontk/opnsense-cli/internal/cli/gen"
)

func main() {
	cli.Execute()
}
