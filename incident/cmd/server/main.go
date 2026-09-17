package main

import (
	"context"
	"errors"
	"github.com/jackc/pgx/v5/pgxpool"
	"gpu-ops-advisor/incident/service"
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
		slog.Error("incident stopped", "error", e)
		os.Exit(1)
	}
}
func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	cfg, e := service.LoadConfig()
	if e != nil {
		return e
	}
	address, e := service.Address()
	if e != nil {
		return e
	}
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		return errors.New("DATABASE_URL required")
	}
	pc, e := pgxpool.ParseConfig(dsn)
	if e != nil {
		return e
	}
	pc.MaxConns = 12
	pc.ConnConfig.ConnectTimeout = 5 * time.Second
	db, e := pgxpool.NewWithConfig(ctx, pc)
	if e != nil {
		return e
	}
	defer db.Close()
	handler, e := service.New(db, cfg)
	if e != nil {
		return e
	}
	startup, cancel := context.WithTimeout(ctx, 30*time.Second)
	e = handler.Prepare(startup, os.Getenv("INCIDENT_APPLY_CONFIG") == "true")
	cancel()
	if e != nil {
		return e
	}
	server := &http.Server{Addr: address, Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 25 * time.Second, WriteTimeout: 25 * time.Second, IdleTimeout: 60 * time.Second}
	go handler.Run(ctx)
	errc := make(chan error, 1)
	go func() { errc <- server.ListenAndServe() }()
	slog.Info("incident ready", "address", address, "grafana_source", cfg.Source)
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
