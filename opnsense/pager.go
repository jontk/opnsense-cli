package opnsense

import "context"

// SearchFunc is the signature for a paginated search call. It receives a page
// number (1-indexed) and a row count, and returns the corresponding page of
// results.
type SearchFunc[T any] func(ctx context.Context, page, rowCount int) (*SearchResult[T], error)

// Pager iterates over paginated search results one page at a time.
//
// Usage:
//
//	pager := opnsense.NewPager(50, func(ctx context.Context, page, rowCount int) (*opnsense.SearchResult[firewall.Alias], error) {
//	    return fw.AliasSearchItem(ctx, map[string]any{"current": page, "rowCount": rowCount})
//	})
//	for pager.Next(ctx) {
//	    for _, alias := range pager.Items() {
//	        fmt.Println(alias.Name)
//	    }
//	}
//	if err := pager.Err(); err != nil {
//	    log.Fatal(err)
//	}
type Pager[T any] struct {
	search   SearchFunc[T]
	rowCount int
	page     int
	items    []T
	total    int
	done     bool
	err      error
}

// NewPager creates a Pager that fetches rowCount items per page using the
// provided search function.
func NewPager[T any](rowCount int, search SearchFunc[T]) *Pager[T] {
	return &Pager[T]{
		search:   search,
		rowCount: rowCount,
	}
}

// Next fetches the next page of results. It returns true if there are items
// to process, false when all pages have been consumed or an error occurred.
func (p *Pager[T]) Next(ctx context.Context) bool {
	if p.done || p.err != nil {
		return false
	}

	p.page++
	result, err := p.search(ctx, p.page, p.rowCount)
	if err != nil {
		p.err = err
		return false
	}

	p.items = result.Rows
	p.total = result.Total

	if len(result.Rows) == 0 || p.page*p.rowCount >= result.Total {
		p.done = true
	}

	return len(result.Rows) > 0
}

// Items returns the items from the most recently fetched page.
func (p *Pager[T]) Items() []T {
	return p.items
}

// Total returns the total number of items reported by the API. Only valid
// after the first call to Next.
func (p *Pager[T]) Total() int {
	return p.total
}

// Err returns the first error encountered during pagination, if any.
func (p *Pager[T]) Err() error {
	return p.err
}

// Collect fetches all pages and returns every item. This is a convenience
// method for cases where all results fit comfortably in memory.
func Collect[T any](ctx context.Context, rowCount int, search SearchFunc[T]) ([]T, error) {
	p := NewPager(rowCount, search)
	var all []T
	for p.Next(ctx) {
		all = append(all, p.Items()...)
	}
	if p.Err() != nil {
		return nil, p.Err()
	}
	return all, nil
}
