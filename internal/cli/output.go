package cli

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"text/tabwriter"

	"gopkg.in/yaml.v3"
)

// Column describes how to extract a value from a row for table display.
type Column struct {
	Header  string
	Extract func(row any) string
}

// Printer formats and writes output in table, JSON, or YAML.
type Printer struct {
	format string
	w      io.Writer
}

// NewPrinter creates a Printer using the output format from cfg.
func NewPrinter(cfg *Config) *Printer {
	return &Printer{format: cfg.Output, w: os.Stdout}
}

// PrintTable writes rows as a tab-separated table with headers.
func (p *Printer) PrintTable(rows []any, cols []Column) error {
	switch p.format {
	case "json":
		return p.PrintJSON(rows)
	case "yaml":
		return p.PrintYAML(rows)
	}
	tw := tabwriter.NewWriter(p.w, 0, 0, 2, ' ', 0)
	headers := make([]string, len(cols))
	for i, c := range cols {
		headers[i] = c.Header
	}
	fmt.Fprintln(tw, strings.Join(headers, "\t"))
	for _, row := range rows {
		vals := make([]string, len(cols))
		for i, c := range cols {
			vals[i] = c.Extract(row)
		}
		fmt.Fprintln(tw, strings.Join(vals, "\t"))
	}
	return tw.Flush()
}

// PrintItem writes a single item as a two-column key/value table.
func (p *Printer) PrintItem(item any, cols []Column) error {
	switch p.format {
	case "json":
		return p.PrintJSON(item)
	case "yaml":
		return p.PrintYAML(item)
	}
	tw := tabwriter.NewWriter(p.w, 0, 0, 2, ' ', 0)
	for _, c := range cols {
		fmt.Fprintf(tw, "%s\t%s\n", c.Header, c.Extract(item))
	}
	return tw.Flush()
}

// PrintJSON marshals v as indented JSON.
func (p *Printer) PrintJSON(v any) error {
	enc := json.NewEncoder(p.w)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

// PrintYAML marshals v as YAML.
func (p *Printer) PrintYAML(v any) error {
	return yaml.NewEncoder(p.w).Encode(v)
}

// PrintGenericResponse prints a GenericResponse as JSON regardless of format,
// or as a simple status line in table mode.
func (p *Printer) PrintGenericResponse(v any) error {
	switch p.format {
	case "json":
		return p.PrintJSON(v)
	case "yaml":
		return p.PrintYAML(v)
	}
	// Table mode: marshal and print compactly
	b, err := json.Marshal(v)
	if err != nil {
		return err
	}
	fmt.Fprintln(p.w, string(b))
	return nil
}
