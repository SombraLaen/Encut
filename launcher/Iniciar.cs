using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;

internal static class Iniciar
{
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBox(IntPtr hWnd, string text, string caption, uint type);

    private static int Main()
    {
        string baseDir = AppContext.BaseDirectory;
        string scriptPath = Path.Combine(baseDir, "silence_cutter.py");
        string localFfmpegBin = Path.Combine(baseDir, "runtime", "ffmpeg", "bin");

        if (!File.Exists(scriptPath))
        {
            ShowError("Nao encontrei o arquivo silence_cutter.py na mesma pasta do iniciar.exe.");
            return 1;
        }

        PythonCommand python = FindPython();
        if (python == null)
        {
            ShowError("Python nao foi encontrado. Rode EncutSetup.exe para baixar as dependencias ou mantenha python.exe/pythonw.exe no PATH.");
            return 1;
        }

        try
        {
            ProcessStartInfo startInfo = new ProcessStartInfo
            {
                FileName = python.Executable,
                Arguments = python.BuildArguments(scriptPath),
                WorkingDirectory = baseDir,
                UseShellExecute = false,
                CreateNoWindow = python.HideWindow,
            };
            PrependPath(startInfo, Path.GetDirectoryName(python.Executable));
            if (Directory.Exists(localFfmpegBin))
            {
                PrependPath(startInfo, localFfmpegBin);
            }
            Process.Start(startInfo);
            return 0;
        }
        catch (Exception ex)
        {
            ShowError("Nao foi possivel abrir o Encut.\n\n" + ex.Message);
            return 1;
        }
    }

    private static PythonCommand FindPython()
    {
        string baseDir = AppContext.BaseDirectory;
        string[] localPaths = new string[]
        {
            Path.Combine(baseDir, "runtime", "python", "pythonw.exe"),
            Path.Combine(baseDir, "runtime", "python", "python.exe"),
        };
        foreach (string path in localPaths)
        {
            if (File.Exists(path))
            {
                return new PythonCommand(path, false);
            }
        }

        string[] names = new string[] { "pythonw.exe", "python.exe", "py.exe" };
        foreach (string name in names)
        {
            string found = FindOnPath(name);
            if (found != null)
            {
                return new PythonCommand(found, name.Equals("py.exe", StringComparison.OrdinalIgnoreCase));
            }
        }

        return null;
    }

    private static void PrependPath(ProcessStartInfo startInfo, string directory)
    {
        if (string.IsNullOrWhiteSpace(directory) || !Directory.Exists(directory))
        {
            return;
        }

        string current = startInfo.EnvironmentVariables["PATH"];
        startInfo.EnvironmentVariables["PATH"] = directory + Path.PathSeparator + current;
    }

    private static string FindOnPath(string executableName)
    {
        string pathValue = Environment.GetEnvironmentVariable("PATH");
        if (string.IsNullOrWhiteSpace(pathValue))
        {
            return null;
        }

        foreach (string rawPart in pathValue.Split(Path.PathSeparator))
        {
            string part = rawPart.Trim('"');
            if (string.IsNullOrWhiteSpace(part))
            {
                continue;
            }

            string candidate = Path.Combine(part, executableName);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static void ShowError(string message)
    {
        MessageBox(IntPtr.Zero, message, "Encut", 0x10);
    }

    private sealed class PythonCommand
    {
        public readonly string Executable;
        private readonly bool _isPyLauncher;

        public PythonCommand(string executable, bool isPyLauncher)
        {
            Executable = executable;
            _isPyLauncher = isPyLauncher;
        }

        public bool HideWindow
        {
            get
            {
                return !_isPyLauncher && Path.GetFileName(Executable).Equals("pythonw.exe", StringComparison.OrdinalIgnoreCase);
            }
        }

        public string BuildArguments(string scriptPath)
        {
            string quotedScript = "\"" + scriptPath.Replace("\"", "\\\"") + "\"";
            return _isPyLauncher ? "-3 " + quotedScript + " --gui" : quotedScript + " --gui";
        }
    }
}
