package main

import (
	"context"
	"flag"
	"fmt"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/job-controller/controller"
	"os"
	"time"
)

func main() {
	id := flag.String("job", "", "job UUID")
	attempt := flag.Int("attempt", 0, "attempt number")
	evidence := flag.String("evidence", "", "independently verified remote termination evidence (required)")
	flag.Parse()
	if e := release(*id, *attempt, *evidence); e != nil {
		fmt.Fprintln(os.Stderr, e)
		os.Exit(1)
	}
	fmt.Println("quarantined reservation released; audit evidence recorded")
}
func release(id string, n int, evidence string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	cfg, e := controller.LoadConfig()
	if e != nil {
		return e
	}
	if os.Getenv("DATABASE_URL") == "" {
		return fmt.Errorf("DATABASE_URL required")
	}
	db, e := pgxpool.New(ctx, os.Getenv("DATABASE_URL"))
	if e != nil {
		return e
	}
	defer db.Close()
	jc, e := controller.New(db, cfg)
	if e != nil {
		return e
	}
	return jc.ReleaseQuarantine(ctx, id, n, evidence)
}
