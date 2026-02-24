package opnsense

import (
	"context"
	"errors"
	"testing"
)

type testItem struct {
	Name string `json:"name"`
}

func makeSearch(pages [][]testItem, total int) SearchFunc[testItem] {
	return func(_ context.Context, page, rowCount int) (*SearchResult[testItem], error) {
		if page < 1 || page > len(pages) {
			return &SearchResult[testItem]{Total: total}, nil
		}
		return &SearchResult[testItem]{
			Rows:     pages[page-1],
			RowCount: rowCount,
			Total:    total,
			Current:  page,
		}, nil
	}
}

func TestPager_singlePage(t *testing.T) {
	items := []testItem{{Name: "a"}, {Name: "b"}}
	p := NewPager(10, makeSearch([][]testItem{items}, 2))

	if !p.Next(context.Background()) {
		t.Fatal("Next() = false on first call, want true")
	}
	if got := len(p.Items()); got != 2 {
		t.Errorf("Items() len = %d, want 2", got)
	}
	if p.Total() != 2 {
		t.Errorf("Total() = %d, want 2", p.Total())
	}
	if p.Next(context.Background()) {
		t.Error("Next() = true on second call, want false (single page)")
	}
	if p.Err() != nil {
		t.Errorf("Err() = %v, want nil", p.Err())
	}
}

func TestPager_multiplePages(t *testing.T) {
	pages := [][]testItem{
		{{Name: "a"}, {Name: "b"}},
		{{Name: "c"}, {Name: "d"}},
		{{Name: "e"}},
	}
	p := NewPager(2, makeSearch(pages, 5))

	var all []testItem
	for p.Next(context.Background()) {
		all = append(all, p.Items()...)
	}
	if p.Err() != nil {
		t.Fatalf("Err() = %v, want nil", p.Err())
	}
	if len(all) != 5 {
		t.Errorf("collected %d items, want 5", len(all))
	}
}

func TestPager_emptyResult(t *testing.T) {
	p := NewPager(10, makeSearch([][]testItem{{}}, 0))

	if p.Next(context.Background()) {
		t.Error("Next() = true for empty result, want false")
	}
	if p.Err() != nil {
		t.Errorf("Err() = %v, want nil", p.Err())
	}
}

func TestPager_searchError(t *testing.T) {
	errBoom := errors.New("boom")
	search := func(_ context.Context, page, rowCount int) (*SearchResult[testItem], error) {
		return nil, errBoom
	}

	p := NewPager(10, search)
	if p.Next(context.Background()) {
		t.Error("Next() = true after error, want false")
	}
	if !errors.Is(p.Err(), errBoom) {
		t.Errorf("Err() = %v, want %v", p.Err(), errBoom)
	}
	// Subsequent calls should also return false
	if p.Next(context.Background()) {
		t.Error("Next() = true on retry after error, want false")
	}
}

func TestPager_errorOnSecondPage(t *testing.T) {
	errBoom := errors.New("page 2 error")
	calls := 0
	search := func(_ context.Context, page, rowCount int) (*SearchResult[testItem], error) {
		calls++
		if page == 2 {
			return nil, errBoom
		}
		return &SearchResult[testItem]{
			Rows:  []testItem{{Name: "a"}},
			Total: 10,
		}, nil
	}

	p := NewPager(1, search)
	if !p.Next(context.Background()) {
		t.Fatal("Next() = false on first page, want true")
	}
	if p.Next(context.Background()) {
		t.Error("Next() = true on errored second page, want false")
	}
	if !errors.Is(p.Err(), errBoom) {
		t.Errorf("Err() = %v, want %v", p.Err(), errBoom)
	}
}

func TestCollect(t *testing.T) {
	pages := [][]testItem{
		{{Name: "a"}, {Name: "b"}},
		{{Name: "c"}},
	}
	all, err := Collect(context.Background(), 2, makeSearch(pages, 3))
	if err != nil {
		t.Fatalf("Collect() error = %v", err)
	}
	if len(all) != 3 {
		t.Errorf("Collect() returned %d items, want 3", len(all))
	}
}

func TestCollect_error(t *testing.T) {
	errBoom := errors.New("boom")
	search := func(_ context.Context, page, rowCount int) (*SearchResult[testItem], error) {
		return nil, errBoom
	}

	_, err := Collect(context.Background(), 10, search)
	if !errors.Is(err, errBoom) {
		t.Errorf("Collect() error = %v, want %v", err, errBoom)
	}
}

func TestPager_contextCancellation(t *testing.T) {
	search := func(ctx context.Context, page, rowCount int) (*SearchResult[testItem], error) {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		return &SearchResult[testItem]{
			Rows:  []testItem{{Name: "a"}},
			Total: 100,
		}, nil
	}

	ctx, cancel := context.WithCancel(context.Background())
	p := NewPager(1, search)

	if !p.Next(ctx) {
		t.Fatal("Next() = false on first call, want true")
	}

	cancel()
	if p.Next(ctx) {
		t.Error("Next() = true after cancel, want false")
	}
	if !errors.Is(p.Err(), context.Canceled) {
		t.Errorf("Err() = %v, want %v", p.Err(), context.Canceled)
	}
}
