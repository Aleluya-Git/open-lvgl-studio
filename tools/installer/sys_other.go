//go:build !windows

package main

import "os/exec"

// Sólo para compilar y probar en otros sistemas: el instalador es para Windows.
func setupConsole()          {}
func hideWindow(c *exec.Cmd) {}
func openURL(u string)       {}
