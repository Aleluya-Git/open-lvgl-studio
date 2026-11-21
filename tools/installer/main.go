// Instalador de Open LVGL Studio para Windows.
//
// Un único .exe que lleva dentro el paquete de la aplicación (payload.zip, el
// mismo que genera tools/build_release.py). Instala para el usuario actual,
// sin permisos de administrador:
//
//  1. busca Python 3.11 o posterior (si no está, ofrece instalarlo con winget);
//  2. copia la aplicación en %LOCALAPPDATA%\Programs\Open LVGL Studio;
//  3. crea su entorno (.venv) e instala PySide6 y PyYAML;
//  4. crea los accesos directos (menú Inicio y escritorio) y la entrada de
//     «Aplicaciones instaladas» para desinstalarla.
//
// Opciones: /S (sin preguntas), /D=<carpeta> (carpeta de instalación),
// /uninstall (desinstalar; la usa la entrada de Aplicaciones instaladas).
//
// Se compila con: python tools/build_installer.py
package main

import (
	"archive/zip"
	"bufio"
	"bytes"
	_ "embed"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

//go:embed payload.zip
var payload []byte

//go:embed version.txt
var versionText string

const appName = "Open LVGL Studio"
const regKey = `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\OpenLVGLStudio`

var silent bool
var in = bufio.NewReader(os.Stdin)

func version() string { return strings.TrimSpace(versionText) }

func say(format string, a ...any) { fmt.Printf(format+"\n", a...) }

func ask(question, def string) string {
	if silent {
		return def
	}
	fmt.Printf("%s [%s]: ", question, def)
	line, _ := in.ReadString('\n')
	line = strings.TrimSpace(line)
	if line == "" {
		return def
	}
	return line
}

func yes(question string, def bool) bool {
	d := "S/n"
	if !def {
		d = "s/N"
	}
	a := strings.ToLower(ask(question, d))
	if a == strings.ToLower(d) {
		return def
	}
	return strings.HasPrefix(a, "s") || strings.HasPrefix(a, "y")
}

func pause() {
	if silent {
		return
	}
	fmt.Print("\nPulsa Intro para cerrar...")
	in.ReadString('\n')
}

func fail(err error) {
	say("\nERROR: %v", err)
	pause()
	os.Exit(1)
}

// ------------------------------------------------------------------ Python
var verRe = regexp.MustCompile(`(\d+)\.(\d+)`)

// pythonVersion ejecuta «exe args... -c» y devuelve (mayor, menor) o (0, 0).
func pythonVersion(cmd []string) (int, int) {
	args := append(append([]string{}, cmd[1:]...), "-c", "import sys;print('%d.%d' % sys.version_info[:2])")
	c := exec.Command(cmd[0], args...)
	hideWindow(c)
	out, err := c.Output()
	if err != nil {
		return 0, 0
	}
	m := verRe.FindStringSubmatch(string(out))
	if m == nil {
		return 0, 0
	}
	a, _ := strconv.Atoi(m[1])
	b, _ := strconv.Atoi(m[2])
	return a, b
}

func goodVersion(a, b int) bool { return a > 3 || (a == 3 && b >= 11) }

// findPython busca un Python 3.11+ (lanzador py, python del PATH o instalaciones habituales).
func findPython() []string {
	cands := [][]string{{"py", "-3.13"}, {"py", "-3.12"}, {"py", "-3.11"}, {"py", "-3"}, {"python"}, {"python3"}}
	local := os.Getenv("LOCALAPPDATA")
	for _, v := range []string{"313", "312", "311", "314"} {
		cands = append(cands, []string{filepath.Join(local, "Programs", "Python", "Python"+v, "python.exe")})
		cands = append(cands, []string{filepath.Join(os.Getenv("ProgramFiles"), "Python"+v, "python.exe")})
	}
	for _, c := range cands {
		if a, b := pythonVersion(c); goodVersion(a, b) {
			return c
		}
	}
	return nil
}

func ensurePython() []string {
	if py := findPython(); py != nil {
		a, b := pythonVersion(py)
		say("✓ Python %d.%d encontrado (%s)", a, b, strings.Join(py, " "))
		return py
	}
	say("No se ha encontrado Python 3.11 o posterior, que Open LVGL Studio necesita.")
	if _, err := exec.LookPath("winget"); err == nil && yes("¿Instalar Python 3.12 ahora con winget?", true) {
		c := exec.Command("winget", "install", "-e", "--id", "Python.Python.3.12", "--scope", "user",
			"--accept-package-agreements", "--accept-source-agreements")
		c.Stdout, c.Stderr = os.Stdout, os.Stderr
		if err := c.Run(); err != nil {
			say("winget no pudo instalar Python: %v", err)
		}
		if py := findPython(); py != nil {
			return py
		}
	}
	say("\nInstala Python desde https://www.python.org/downloads/ (marca «Add Python to PATH»)")
	say("y vuelve a ejecutar este instalador.")
	openURL("https://www.python.org/downloads/")
	pause()
	os.Exit(2)
	return nil
}

// ------------------------------------------------------------------ ficheros
// extract descomprime el paquete en dest quitando la carpeta raíz (OpenLVGLStudio-<versión>/).
func extract(data []byte, dest string) (int, error) {
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return 0, err
	}
	n := 0
	absDest, _ := filepath.Abs(dest)
	for _, f := range zr.File {
		name := f.Name
		if i := strings.Index(name, "/"); i >= 0 {
			name = name[i+1:]
		}
		if name == "" {
			continue
		}
		target := filepath.Join(absDest, filepath.FromSlash(name))
		if !strings.HasPrefix(target, absDest+string(os.PathSeparator)) {
			return n, fmt.Errorf("ruta no válida en el paquete: %s", f.Name)
		}
		if f.FileInfo().IsDir() || strings.HasSuffix(f.Name, "/") {
			os.MkdirAll(target, 0o755)
			continue
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return n, err
		}
		rc, err := f.Open()
		if err != nil {
			return n, err
		}
		out, err := os.Create(target)
		if err != nil {
			rc.Close()
			return n, err
		}
		_, err = io.Copy(out, rc)
		rc.Close()
		out.Close()
		if err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0o755)
}

func run(dir string, name string, args ...string) error {
	c := exec.Command(name, args...)
	c.Dir = dir
	c.Stdout, c.Stderr = os.Stdout, os.Stderr
	return c.Run()
}

func psQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", "''") + "'" }

func shortcut(lnk, target, args, workdir, icon string) error {
	script := fmt.Sprintf("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);$s.TargetPath=%s;"+
		"$s.Arguments=%s;$s.WorkingDirectory=%s;$s.IconLocation=%s;$s.Save()",
		psQuote(lnk), psQuote(target), psQuote(args), psQuote(workdir), psQuote(icon))
	c := exec.Command("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script)
	hideWindow(c)
	return c.Run()
}

func startMenuDir() string {
	return filepath.Join(os.Getenv("APPDATA"), "Microsoft", "Windows", "Start Menu", "Programs")
}

func desktopDir() string { return filepath.Join(os.Getenv("USERPROFILE"), "Desktop") }

func regAdd(name, typ, value string) {
	c := exec.Command("reg", "add", regKey, "/v", name, "/t", typ, "/d", value, "/f")
	hideWindow(c)
	c.Run()
}

// ------------------------------------------------------------------ instalar
func install(dir string) {
	say("\n%s %s — instalación", appName, version())
	say(strings.Repeat("=", 50))
	if !silent {
		dir = ask("Carpeta de instalación", dir)
	}
	py := ensurePython()

	say("\n[1/4] Copiando la aplicación en %s ...", dir)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		fail(err)
	}
	// una versión anterior: se quita su código (no el entorno .venv ni tus proyectos, que están en otra carpeta)
	for _, old := range []string{"olvgl", "plugins", "tools", "tests", "docs", "vscode-extension", "marketplace"} {
		os.RemoveAll(filepath.Join(dir, old))
	}
	n, err := extract(payload, dir)
	if err != nil {
		fail(err)
	}
	say("      %d ficheros", n)

	say("\n[2/4] Creando el entorno de Python (.venv) ...")
	venvPy := filepath.Join(dir, ".venv", "Scripts", "python.exe")
	if _, err := os.Stat(venvPy); err != nil {
		args := append(append([]string{}, py[1:]...), "-m", "venv", ".venv")
		if err := run(dir, py[0], args...); err != nil {
			fail(fmt.Errorf("no se pudo crear el entorno de Python: %v", err))
		}
	}

	say("\n[3/4] Instalando PySide6 y PyYAML (necesita Internet; puede tardar unos minutos) ...")
	run(dir, venvPy, "-m", "pip", "install", "--upgrade", "pip")
	if err := run(dir, venvPy, "-m", "pip", "install", "-r", "requirements.txt"); err != nil {
		fail(fmt.Errorf("pip no pudo instalar las dependencias: %v", err))
	}

	say("\n[4/4] Accesos directos y desinstalador ...")
	self, _ := os.Executable()
	uninst := filepath.Join(dir, "desinstalar.exe")
	if !strings.EqualFold(self, uninst) {
		if err := copyFile(self, uninst); err != nil {
			say("  aviso: no se pudo copiar el desinstalador: %v", err)
		}
	}
	pyw := filepath.Join(dir, ".venv", "Scripts", "pythonw.exe")
	mainPy := `"` + filepath.Join(dir, "main.py") + `"`
	icon := filepath.Join(dir, "olvgl", "resources", "app_icon.ico")
	links := []string{
		filepath.Join(startMenuDir(), appName+".lnk"),
		filepath.Join(desktopDir(), appName+".lnk"),
		filepath.Join(dir, appName+".lnk"),
	}
	for _, l := range links {
		if err := shortcut(l, pyw, mainPy, dir, icon); err != nil {
			say("  aviso: no se pudo crear %s", l)
		}
	}
	regAdd("DisplayName", "REG_SZ", appName)
	regAdd("DisplayVersion", "REG_SZ", version())
	regAdd("Publisher", "REG_SZ", "Open LVGL Studio")
	regAdd("InstallLocation", "REG_SZ", dir)
	regAdd("DisplayIcon", "REG_SZ", icon)
	regAdd("UninstallString", "REG_SZ", `"`+uninst+`" /uninstall`)
	regAdd("NoModify", "REG_DWORD", "1")
	regAdd("NoRepair", "REG_DWORD", "1")
	// la extensión de VS Code encuentra la aplicación con este fichero
	home := filepath.Join(os.Getenv("USERPROFILE"), ".olvgl")
	os.MkdirAll(home, 0o755)
	os.WriteFile(filepath.Join(home, "studio_path.txt"), []byte(dir+"\r\n"), 0o644)

	say("\n✓ %s %s instalado.", appName, version())
	say("  Ábrelo desde el menú Inicio o el escritorio («%s»).", appName)
	say("  Extensión de VS Code: ejecuta install_vscode.bat en %s", dir)
	if yes("\n¿Abrir Open LVGL Studio ahora?", true) {
		c := exec.Command(pyw, filepath.Join(dir, "main.py"))
		c.Dir = dir
		c.Start()
	}
}

// ------------------------------------------------------------------ desinstalar
func uninstall() {
	self, _ := os.Executable()
	dir := filepath.Dir(self)
	if _, err := os.Stat(filepath.Join(dir, "main.py")); err != nil {
		fail(errors.New("este programa no está dentro de una instalación de Open LVGL Studio"))
	}
	say("%s — desinstalar", appName)
	if !yes(fmt.Sprintf("¿Desinstalar %s de %s? (tus proyectos y ajustes no se borran)", appName, dir), true) {
		return
	}
	os.Remove(filepath.Join(startMenuDir(), appName+".lnk"))
	os.Remove(filepath.Join(desktopDir(), appName+".lnk"))
	c := exec.Command("reg", "delete", regKey, "/f")
	hideWindow(c)
	c.Run()
	os.Remove(filepath.Join(os.Getenv("USERPROFILE"), ".olvgl", "studio_path.txt"))
	// el propio desinstalador está dentro de la carpeta: se borra cuando termine
	script := fmt.Sprintf(`ping -n 3 127.0.0.1 >nul & rmdir /s /q "%s"`, dir)
	d := exec.Command("cmd", "/c", script)
	d.Dir = os.TempDir()
	hideWindow(d)
	d.Start()
	say("✓ Desinstalado.")
	if !silent {
		time.Sleep(1500 * time.Millisecond)
	}
}

func main() {
	setupConsole()
	dir := filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", appName)
	doUninstall := false
	for _, a := range os.Args[1:] {
		switch {
		case strings.EqualFold(a, "/S") || a == "--silent":
			silent = true
		case strings.HasPrefix(strings.ToUpper(a), "/D="):
			dir = a[3:]
		case strings.EqualFold(a, "/uninstall") || a == "--uninstall":
			doUninstall = true
		}
	}
	if doUninstall {
		uninstall()
		return
	}
	install(dir)
	pause()
}
