package opnsense

import (
	"encoding/json"
	"testing"
)

func TestOPNBool_MarshalJSON(t *testing.T) {
	tests := []struct {
		name string
		val  OPNBool
		want string
	}{
		{"true marshals to 1", OPNBool(true), `"1"`},
		{"false marshals to 0", OPNBool(false), `"0"`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := json.Marshal(tt.val)
			if err != nil {
				t.Fatalf("MarshalJSON() error: %v", err)
			}
			if string(got) != tt.want {
				t.Errorf("MarshalJSON() = %s, want %s", got, tt.want)
			}
		})
	}
}

func TestOPNBool_UnmarshalJSON(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  bool
	}{
		{"string 1", `"1"`, true},
		{"string 0", `"0"`, false},
		{"string true", `"true"`, true},
		{"string TRUE", `"TRUE"`, true},
		{"string True", `"True"`, true},
		{"string yes", `"yes"`, true},
		{"string YES", `"YES"`, true},
		{"string Yes", `"Yes"`, true},
		{"string false", `"false"`, false},
		{"string no", `"no"`, false},
		{"empty string", `""`, false},
		{"string random", `"random"`, false},
		{"native bool true", `true`, true},
		{"native bool false", `false`, false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var b OPNBool
			err := json.Unmarshal([]byte(tt.input), &b)
			if err != nil {
				t.Fatalf("UnmarshalJSON(%s) error: %v", tt.input, err)
			}
			if bool(b) != tt.want {
				t.Errorf("UnmarshalJSON(%s) = %v, want %v", tt.input, bool(b), tt.want)
			}
		})
	}
}

func TestOPNBool_Bool(t *testing.T) {
	trueVal := OPNBool(true)
	if trueVal.Bool() != true {
		t.Error("Bool() = false, want true")
	}
	falseVal := OPNBool(false)
	if falseVal.Bool() != false {
		t.Error("Bool() = true, want false")
	}
}

func TestOPNBool_roundTrip(t *testing.T) {
	// Marshal then unmarshal should preserve value
	for _, orig := range []OPNBool{true, false} {
		data, err := json.Marshal(orig)
		if err != nil {
			t.Fatalf("Marshal(%v) error: %v", orig, err)
		}
		var got OPNBool
		if err := json.Unmarshal(data, &got); err != nil {
			t.Fatalf("Unmarshal(%s) error: %v", data, err)
		}
		if got != orig {
			t.Errorf("round-trip: got %v, want %v", got, orig)
		}
	}
}

func TestOPNBool_inStruct(t *testing.T) {
	type config struct {
		Enabled OPNBool `json:"enabled"`
	}

	// Unmarshal from OPNsense-style JSON
	input := `{"enabled":"1"}`
	var c config
	if err := json.Unmarshal([]byte(input), &c); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}
	if !c.Enabled.Bool() {
		t.Error("Enabled = false, want true")
	}

	// Marshal back to OPNsense-style JSON
	data, err := json.Marshal(c)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}
	want := `{"enabled":"1"}`
	if string(data) != want {
		t.Errorf("Marshal = %s, want %s", data, want)
	}
}

func TestOPNInt_MarshalJSON(t *testing.T) {
	tests := []struct {
		name string
		val  OPNInt
		want string
	}{
		{"80 marshals to string", OPNInt(80), `"80"`},
		{"0 marshals to string", OPNInt(0), `"0"`},
		{"negative marshals to string", OPNInt(-1), `"-1"`},
		{"large number", OPNInt(65535), `"65535"`},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := json.Marshal(tt.val)
			if err != nil {
				t.Fatalf("MarshalJSON() error: %v", err)
			}
			if string(got) != tt.want {
				t.Errorf("MarshalJSON() = %s, want %s", got, tt.want)
			}
		})
	}
}

func TestOPNInt_UnmarshalJSON(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  int
	}{
		{"string 80", `"80"`, 80},
		{"string 0", `"0"`, 0},
		{"string negative", `"-1"`, -1},
		{"empty string", `""`, 0},
		{"string with spaces", `" 443 "`, 443},
		{"native int 80", `80`, 80},
		{"native int 0", `0`, 0},
		{"native int negative", `-1`, -1},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var n OPNInt
			err := json.Unmarshal([]byte(tt.input), &n)
			if err != nil {
				t.Fatalf("UnmarshalJSON(%s) error: %v", tt.input, err)
			}
			if int(n) != tt.want {
				t.Errorf("UnmarshalJSON(%s) = %d, want %d", tt.input, int(n), tt.want)
			}
		})
	}
}

func TestOPNInt_UnmarshalJSON_invalidString(t *testing.T) {
	var n OPNInt
	err := json.Unmarshal([]byte(`"not-a-number"`), &n)
	if err == nil {
		t.Fatal("UnmarshalJSON(\"not-a-number\") returned nil error, want error")
	}
}

func TestOPNInt_Int(t *testing.T) {
	n := OPNInt(42)
	if n.Int() != 42 {
		t.Errorf("Int() = %d, want 42", n.Int())
	}
}

func TestOPNInt_roundTrip(t *testing.T) {
	for _, orig := range []OPNInt{0, 1, 80, 443, -1, 65535} {
		data, err := json.Marshal(orig)
		if err != nil {
			t.Fatalf("Marshal(%d) error: %v", orig, err)
		}
		var got OPNInt
		if err := json.Unmarshal(data, &got); err != nil {
			t.Fatalf("Unmarshal(%s) error: %v", data, err)
		}
		if got != orig {
			t.Errorf("round-trip: got %d, want %d", got, orig)
		}
	}
}

func TestOPNInt_inStruct(t *testing.T) {
	type config struct {
		Port OPNInt `json:"port"`
	}

	input := `{"port":"8080"}`
	var c config
	if err := json.Unmarshal([]byte(input), &c); err != nil {
		t.Fatalf("Unmarshal error: %v", err)
	}
	if c.Port.Int() != 8080 {
		t.Errorf("Port = %d, want 8080", c.Port.Int())
	}

	data, err := json.Marshal(c)
	if err != nil {
		t.Fatalf("Marshal error: %v", err)
	}
	want := `{"port":"8080"}`
	if string(data) != want {
		t.Errorf("Marshal = %s, want %s", data, want)
	}
}

func TestBoolPtr(t *testing.T) {
	tests := []struct {
		name string
		val  bool
		want OPNBool
	}{
		{"true", true, OPNBool(true)},
		{"false", false, OPNBool(false)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := BoolPtr(tt.val)
			if got == nil {
				t.Fatal("BoolPtr() returned nil")
			}
			if *got != tt.want {
				t.Errorf("*BoolPtr(%v) = %v, want %v", tt.val, *got, tt.want)
			}
		})
	}
}

func TestIntPtr(t *testing.T) {
	tests := []struct {
		name string
		val  int
		want OPNInt
	}{
		{"zero", 0, OPNInt(0)},
		{"positive", 80, OPNInt(80)},
		{"negative", -1, OPNInt(-1)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := IntPtr(tt.val)
			if got == nil {
				t.Fatal("IntPtr() returned nil")
			}
			if *got != tt.want {
				t.Errorf("*IntPtr(%d) = %d, want %d", tt.val, *got, tt.want)
			}
		})
	}
}

func TestBoolPtr_uniquePointers(t *testing.T) {
	p1 := BoolPtr(true)
	p2 := BoolPtr(true)
	if p1 == p2 {
		t.Error("BoolPtr should return unique pointers for each call")
	}
}

func TestIntPtr_uniquePointers(t *testing.T) {
	p1 := IntPtr(42)
	p2 := IntPtr(42)
	if p1 == p2 {
		t.Error("IntPtr should return unique pointers for each call")
	}
}
