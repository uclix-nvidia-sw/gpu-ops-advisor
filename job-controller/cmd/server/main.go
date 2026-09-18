package main

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/job-controller/controller"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
	_ "time/tzdata"
)

func main() {
	if e := run(); e != nil {
		slog.Error("job controller stopped", "error", e)
		os.Exit(1)
	}
}
func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	cfg, e := controller.LoadConfig()
	if e != nil {
		return e
	}
	address, e := controller.ListenAddress()
	if e != nil {
		return e
	}
	if os.Getenv("DATABASE_URL") == "" {
		return errors.New("DATABASE_URL required")
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
	startup, cancel := context.WithTimeout(ctx, 30*time.Second)
	e = jc.Prepare(startup, os.Getenv("JC_APPLY_CONFIG") == "" || os.Getenv("JC_APPLY_CONFIG") == "true")
	cancel()
	if e != nil {
		return e
	}
	server := &http.Server{Addr: address, Handler: jc, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 20 * time.Second, IdleTimeout: 60 * time.Second}
	go jc.Run(ctx)
	errc := make(chan error, 1)
	go func() { errc <- server.ListenAndServe() }()
	slog.Info("job controller ready", "address", address, "config_revision", jc.Revision)
	select {
	case e = <-errc:
		if !errors.Is(e, http.ErrServerClosed) {
			return e
		}
	case <-ctx.Done():
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		return server.Shutdown(shutdown)
	}
	return nil
}
