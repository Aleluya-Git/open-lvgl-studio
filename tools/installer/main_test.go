package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestExtractStripsRoot(t *testing.T) {
	dir := t.TempDir()
	n, err := extract(payload, dir)
	if err != nil || n < 50 {
		t.Fatalf("extract: %d %v", n, err)
	}
	for _, f := range []string{"main.py", "requirements.txt", "olvgl/__init__.py", "run.bat"} {
		if _, err := os.Stat(filepath.Join(dir, f)); err != nil {
			t.Errorf("falta %s", f)
		}
	}
}

func TestGoodVersion(t *testing.T) {
	if goodVersion(3, 10) || !goodVersion(3, 11) || !goodVersion(3, 13) || !goodVersion(4, 0) {
		t.Fatal("versiones")
	}
}
