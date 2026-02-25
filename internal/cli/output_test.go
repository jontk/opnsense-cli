package cli

import (
	"bytes"
	"strings"
	"testing"
)

func TestPrinterPrintTable_table(t *testing.T) {
	rows := []any{"Alice", "Bob"}
	cols := []Column{
		{Header: "NAME", Extract: func(row any) string { return row.(string) }},
	}
	cfg := &Config{Output: "table"}
	p := &Printer{format: cfg.Output, w: &bytes.Buffer{}}
	buf := &bytes.Buffer{}
	p.w = buf
	if err := p.PrintTable(rows, cols); err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, "NAME") {
		t.Errorf("expected NAME header, got: %s", out)
	}
	if !strings.Contains(out, "Alice") || !strings.Contains(out, "Bob") {
		t.Errorf("expected row values, got: %s", out)
	}
}

func TestPrinterPrintTable_json(t *testing.T) {
	rows := []any{map[string]string{"k": "v"}}
	cols := []Column{
		{Header: "K", Extract: func(row any) string { return "v" }},
	}
	cfg := &Config{Output: "json"}
	buf := &bytes.Buffer{}
	p := &Printer{format: cfg.Output, w: buf}
	if err := p.PrintTable(rows, cols); err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, `"k"`) || !strings.Contains(out, `"v"`) {
		t.Errorf("expected JSON output, got: %s", out)
	}
}

func TestPrinterPrintTable_yaml(t *testing.T) {
	rows := []any{map[string]string{"key": "val"}}
	cols := []Column{
		{Header: "KEY", Extract: func(row any) string { return "val" }},
	}
	buf := &bytes.Buffer{}
	p := &Printer{format: "yaml", w: buf}
	if err := p.PrintTable(rows, cols); err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, "key") || !strings.Contains(out, "val") {
		t.Errorf("expected YAML output, got: %s", out)
	}
}

func TestPrinterPrintJSON(t *testing.T) {
	buf := &bytes.Buffer{}
	p := &Printer{format: "json", w: buf}
	if err := p.PrintJSON(map[string]int{"a": 1}); err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, `"a"`) || !strings.Contains(out, "1") {
		t.Errorf("expected JSON, got: %s", out)
	}
}

func TestPrinterPrintGenericResponse_table(t *testing.T) {
	buf := &bytes.Buffer{}
	p := &Printer{format: "table", w: buf}
	if err := p.PrintGenericResponse(map[string]string{"result": "saved"}); err != nil {
		t.Fatal(err)
	}
	out := buf.String()
	if !strings.Contains(out, "saved") {
		t.Errorf("expected 'saved', got: %s", out)
	}
}
