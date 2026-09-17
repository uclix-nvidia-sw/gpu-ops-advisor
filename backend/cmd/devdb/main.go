// devdb runs an isolated, real PostgreSQL instance for local development only.
package main

import (
	"log"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
)

func main() {
	root, _ := filepath.Abs(".local/postgres")
	db := embeddedpostgres.NewDatabase(embeddedpostgres.DefaultConfig().Version(embeddedpostgres.V16).Port(55432).Database("dsx").Username("dsx").Password("local-development-only").RuntimePath(filepath.Join(root, "runtime")).DataPath(filepath.Join(root, "data")).BinariesPath(filepath.Join(root, "bin")).CachePath(filepath.Join(root, "cache")))
	if err := db.Start(); err != nil {
		log.Fatal(err)
	}
	log.Print("local PostgreSQL ready on 127.0.0.1:55432; database=dsx")
	done := make(chan os.Signal, 1)
	signal.Notify(done, os.Interrupt, syscall.SIGTERM)
	<-done
	if err := db.Stop(); err != nil {
		log.Print(err)
	}
}
