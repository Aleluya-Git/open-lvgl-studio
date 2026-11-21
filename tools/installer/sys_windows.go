//go:build windows

package main

import (
	"os/exec"
	"syscall"
)

var kernel32 = syscall.NewLazyDLL("kernel32.dll")

// setupConsole: la consola en UTF-8 para que se vean las tildes.
func setupConsole() {
	kernel32.NewProc("SetConsoleOutputCP").Call(65001)
	kernel32.NewProc("SetConsoleCP").Call(65001)
}

// hideWindow evita que se abra una ventana negra por cada orden auxiliar.
func hideWindow(c *exec.Cmd) {
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
}

func openURL(u string) {
	c := exec.Command("rundll32", "url.dll,FileProtocolHandler", u)
	c.Start()
}
