package main

import (
	"context"
	"gpu-ops-advisor/backend/internal/api"
	"gpu-ops-advisor/backend/internal/config"
	"gpu-ops-advisor/backend/internal/store"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
	_ "time/tzdata"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if e := run(); e != nil {
		slog.Error("server stopped", "error", e)
		os.Exit(1)
	}
}
func run() error {
	c, e := config.Load()
	if e != nil {
		return e
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	db, e := store.Open(ctx, c.DatabaseURL)
	if e != nil {
		return e
	}
	defer db.Pool.Close()
	if c.Migrate {
		if e = db.Migrate(ctx); e != nil {
			return e
		}
	}
	if c.Seed {
		if e = db.Seed(ctx); e != nil {
			return e
		}
	}
	if e = db.EnsureDefaults(ctx); e != nil {
		return e
	}
	handler := api.New(db, c)
	handler.RunScheduler(ctx)
	srv := &http.Server{Addr: c.Address, Handler: handler, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 130 * time.Second, IdleTimeout: 60 * time.Second, MaxHeaderBytes: 16 * 1024}
	errc := make(chan error, 1)
	go func() {
		slog.Info("backend listening", "address", c.Address, "authentication", "disabled")
		errc <- srv.ListenAndServe()
	}()
	select {
	case e = <-errc:
		if e == http.ErrServerClosed {
			return nil
		}
		return e
	case <-ctx.Done():
		shutdown, stop := context.WithTimeout(context.Background(), 10*time.Second)
		defer stop()
		return srv.Shutdown(shutdown)
	}
}
