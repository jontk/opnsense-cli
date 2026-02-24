# opnsense-cli

Go client library for the [OPNsense](https://opnsense.org/) API. Auto-generated from the official documentation with typed structs for 892 CRUD endpoints across 96 modules.

## Install

```sh
go get github.com/jontk/opnsense-cli
```

## Usage

```go
package main

import (
	"context"
	"fmt"
	"log"

	"github.com/jontk/opnsense-cli/opnsense"
	"github.com/jontk/opnsense-cli/opnsense/firewall"
)

func main() {
	// Create a base client
	client := opnsense.NewClient(
		"https://192.168.1.1",
		"your-api-key",
		"your-api-secret",
		opnsense.WithInsecureTLS(),
	)

	// Create a module client
	fw := firewall.NewClient(client)
	ctx := context.Background()

	// Create a firewall alias (typed request body)
	resp, err := fw.AliasAddItem(ctx, &firewall.Alias{
		Enabled:     "1",
		Name:        "my_servers",
		Type:        "host",
		Content:     "10.0.0.1\n10.0.0.2",
		Description: "My servers",
	})
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Created:", resp.UUID)

	// Get an alias by UUID (typed response)
	alias, err := fw.AliasGetItem(ctx, resp.UUID)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println("Name:", alias.Name)

	// Delete an alias
	_, err = fw.AliasDelItem(ctx, resp.UUID)
	if err != nil {
		log.Fatal(err)
	}
}
```

### Client options

```go
opnsense.NewClient(url, key, secret,
	opnsense.WithInsecureTLS(),                       // skip TLS verification
	opnsense.WithTimeout(60 * time.Second),           // custom timeout
	opnsense.WithRetry(3, 500 * time.Millisecond),   // retry 5xx/network errors
	opnsense.WithHTTPClient(customClient),            // bring your own http.Client
)
```

### Untyped endpoints

Endpoints without a matching model type use `map[string]any`:

```go
result, err := fw.AliasGetTableSize(ctx)
// result is map[string]any
```

## Modules

Each OPNsense API module is a separate Go package under `opnsense/`:

| Core | Plugins |
|------|---------|
| auth, captiveportal, core, cron | acmeclient, beats, bind, caddy |
| dhcrelay, diagnostics, dnsmasq | cicap, clamav, crowdsec, dnscryptproxy |
| firewall, firmware, ids | dyndns, freeradius, haproxy |
| interfaces, ipsec, kea | lldpd, maltrail, monit, netbird |
| monit, openvpn, routing | nginx, postfix, proxy, quagga |
| syslog, trafficshaper, trust | radsecproxy, tailscale, telegraf |
| unbound, wireguard | tor, vnstat, wol, zerotier |

See [`opnsense/`](opnsense/) for all 96 packages.

## Code generation

The SDK is generated from OPNsense's HTML API documentation and XML model files via a Python pipeline.

### Prerequisites

```sh
make venv   # creates .venv with dependencies
```

### Full pipeline

```sh
make all    # crawl → generate → fmt → build
```

Or run stages individually:

```sh
make crawl      # scrape HTML docs + XML models into docs/
make generate   # parse docs, emit Go code
make fmt        # gofmt the generated code
make build      # go build ./opnsense/...
```

## Project structure

```
opnsense/
  client.go          # hand-written: HTTP client, auth, options
  request.go         # hand-written: Do() method, JSON marshaling
  types.go           # hand-written: GenericResponse, SearchResult[T]
  api/api.go         # hand-written: top-level API package
  firewall/           # generated module package
    firewall.go       #   endpoint methods (typed + untyped)
    types.go          #   model structs + response wrappers
  ...                 # 96 module packages total

generate/             # Python code generator
  __main__.py         #   pipeline orchestration
  model/ir.py         #   intermediate representation
  parser/             #   markdown + XML parsers, endpoint resolver
  emitter/            #   Go code emitter
  templates/          #   Jinja2 templates

crawl_api_docs.py     # documentation scraper
```
