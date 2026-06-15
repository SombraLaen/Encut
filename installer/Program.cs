using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using Microsoft.Win32;

internal static class Program
{
    private const string AppName = "Encut";
    private const string AppId = "Encut";
    private const string LegacyAppName = "Cortador de Silencio";
    private const string LegacyAppId = "CortadorSilencioCodex";
    private const string SetupFileName = "EncutSetup.exe";
    private const string LegacySetupFileName = "CortadorSilencioSetup.exe";
    private const string PythonVersion = "3.12.10";
    private const string PythonUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe";
    private const string PythonRuntimeZipName = "PythonRuntime-3.12.10-windows-x64.zip";
    private const string PythonRuntimeZipUrl = "https://github.com/SombraLaen/Encut/releases/latest/download/PythonRuntime-3.12.10-windows-x64.zip";
    private const string FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip";
    private const string DefaultGitHubRepo = "SombraLaen/Encut";
    private const string DefaultGitHubBranch = "main";
    private const string DefaultUpdateEndpointUrl = "https://api.github.com/repos/SombraLaen/Encut/releases/latest";
    private const string DefaultDownloadUrl = "";

    private static readonly Dictionary<string, string> EmbeddedFiles = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        { "app.silence_cutter.py", "silence_cutter.py" },
        { "app.README.md", "README.md" },
        { "app.VERSION", "VERSION" },
        { "app.CHANGELOG.md", "CHANGELOG.md" },
        { "app.iniciar.exe", "iniciar.exe" },
        { "app.iniciar.bat", "iniciar.bat" },
        { "app.instalar.bat", "instalar.bat" },
        { "app.desinstalar.bat", "desinstalar.bat" },
        { "app.instalar.ps1", "instalar.ps1" },
        { "app.desinstalar.ps1", "desinstalar.ps1" },
        { "app.presets_ajustes.json", "presets_ajustes.json" },
        { "app.update_config.json", "update_config.json" },
        { "app.build_site_package.ps1", "build_site_package.ps1" },
        { "app.launcher.Iniciar.cs", Path.Combine("launcher", "Iniciar.cs") },
        { "app.launcher.Iniciar.csproj", Path.Combine("launcher", "Iniciar.csproj") },
    };

    private static readonly HashSet<string> PreserveIfExists = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "presets_ajustes.json",
        "update_config.json",
    };

    private static int Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        Console.Title = AppName + " Setup v" + ReadEmbeddedVersion();

        try
        {
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;

            if (HasArg(args, "/help") || HasArg(args, "--help") || HasArg(args, "-h"))
            {
                PrintHelp();
                return 0;
            }

            if (HasArg(args, "/uninstall") || HasArg(args, "--uninstall"))
            {
                return RunUninstall(args);
            }

            return RunInstall(args);
        }
        catch (Exception ex)
        {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine();
            Console.WriteLine("Erro: " + ex.Message);
            Console.ResetColor();
            Console.WriteLine();
            PauseIfInteractive(args);
            return 1;
        }
    }

    private static int RunInstall(string[] args)
    {
        string appDir = Path.GetFullPath(GetValueArg(args, "/dir") ?? GetDefaultInstallDir());
        string installDir = Path.Combine(appDir, "instalacao");
        string runtimeDir = Path.Combine(appDir, "runtime");
        string downloadDir = Path.Combine(runtimeDir, "downloads");
        string logPath = Path.Combine(installDir, "instalador.log");

        Directory.CreateDirectory(appDir);
        Directory.CreateDirectory(installDir);
        Directory.CreateDirectory(downloadDir);

        using (InstallerLog log = new InstallerLog(logPath))
        {
            string setupVersion = ReadSetupVersion(appDir);
            log.Write("Iniciando instalacao do " + AppName + " v" + setupVersion + ".");
            log.Write("Pasta da aplicacao: " + appDir);
            if (!ShouldSkipUpdate(args) && TryRunNewerSetupFromSite(args, appDir, downloadDir, setupVersion, log))
            {
                return 0;
            }

            ExtractAppFiles(appDir, log);
            EnsureUpdateConfig(appDir, log);
            setupVersion = ReadSetupVersion(appDir);
            CopySelfToInstallFolder(installDir, log);
            InstallPython(runtimeDir, downloadDir, log);
            InstallFfmpeg(runtimeDir, downloadDir, log);

            string desktopShortcut = CreateDesktopShortcut(appDir, log);
            ShortcutPair shortcuts = CreateStartMenuShortcuts(appDir, installDir, log);
            WriteManifest(appDir, installDir, desktopShortcut, shortcuts.StartShortcut, shortcuts.UninstallShortcut, log);
            RemoveLegacyInstallArtifacts(appDir, log);
            RegisterUninstaller(appDir, installDir, log);

            log.Write("Instalacao concluida.");
        }

        Console.WriteLine();
        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine(AppName + " v" + ReadSetupVersion(appDir) + " instalado com sucesso.");
        Console.ResetColor();
        Console.WriteLine("Abra pelo atalho da area de trabalho, pelo Menu Iniciar ou por iniciar.exe.");
        PauseIfInteractive(args);
        return 0;
    }

    private static int RunUninstall(string[] args)
    {
        string appDir = Path.GetFullPath(GetInstalledAppDir());
        string installDir = Path.Combine(appDir, "instalacao");
        string logPath = Path.Combine(installDir, "desinstalador.log");
        Directory.CreateDirectory(installDir);

        using (InstallerLog log = new InstallerLog(logPath))
        {
            bool deleteAll = HasArg(args, "/delete-all") || HasArg(args, "--delete-all") || HasArg(args, "/apagar-tudo");
            bool keepFiles = HasArg(args, "/keep") || HasArg(args, "--keep") || HasArg(args, "/manter");
            bool silent = HasArg(args, "/silent") || HasArg(args, "--silent");

            log.Write("Iniciando desinstalacao do " + AppName + " v" + ReadSetupVersion(appDir) + ".");
            log.Write("Pasta detectada: " + appDir);

            if (!deleteAll && !keepFiles && !silent)
            {
                deleteAll = AskDeleteAll();
            }

            RemoveShortcuts(appDir, log);
            UnregisterUninstaller(log);

            if (deleteAll)
            {
                EnsureSafeDeleteTarget(appDir);
                log.Write("Usuario escolheu apagar tudo. A pasta sera removida apos o desinstalador fechar.");
                ScheduleDirectoryDeletion(appDir);
                Console.WriteLine();
                Console.WriteLine("A pasta inteira sera apagada em alguns segundos:");
                Console.WriteLine(appDir);
            }
            else
            {
                log.Write("Usuario escolheu manter arquivos. Pasta Encut preservada.");
                Console.WriteLine();
                Console.WriteLine("Atalhos e registro removidos. Arquivos preservados em:");
                Console.WriteLine(appDir);
            }

            log.Write("Desinstalacao concluida.");
        }

        PauseIfInteractive(args);
        return 0;
    }

    private static void ExtractAppFiles(string appDir, InstallerLog log)
    {
        Assembly assembly = Assembly.GetExecutingAssembly();
        foreach (KeyValuePair<string, string> item in EmbeddedFiles)
        {
            string destination = Path.Combine(appDir, item.Value);
            if (PreserveIfExists.Contains(item.Value) && File.Exists(destination))
            {
                log.Write("Preservando arquivo existente: " + item.Value);
                continue;
            }

            using (Stream stream = assembly.GetManifestResourceStream(item.Key))
            {
                if (stream == null)
                {
                    throw new InvalidOperationException("Recurso interno nao encontrado: " + item.Key);
                }

                string parent = Path.GetDirectoryName(destination);
                if (!string.IsNullOrWhiteSpace(parent))
                {
                    Directory.CreateDirectory(parent);
                }

                using (FileStream output = File.Create(destination))
                {
                    stream.CopyTo(output);
                }
            }
            log.Write("Arquivo instalado: " + item.Value);
        }
    }

    private static void EnsureUpdateConfig(string appDir, InstallerLog log)
    {
        string path = Path.Combine(appDir, "update_config.json");
        string defaultConfig =
            "{\r\n" +
            "  \"enabled\": true,\r\n" +
            "  \"check_on_startup\": true,\r\n" +
            "  \"github_repo\": \"" + JsonEscape(DefaultGitHubRepo) + "\",\r\n" +
            "  \"github_branch\": \"" + JsonEscape(DefaultGitHubBranch) + "\",\r\n" +
            "  \"manifest_url\": \"" + JsonEscape(DefaultUpdateEndpointUrl) + "\"\r\n" +
            "}\r\n";

        try
        {
            if (!File.Exists(path))
            {
                File.WriteAllText(path, defaultConfig, Encoding.UTF8);
                log.Write("Configuracao de atualizacao criada: GitHub " + DefaultGitHubRepo);
                return;
            }

            string config = File.ReadAllText(path, Encoding.UTF8);
            config = EnsureJsonStringProperty(config, "github_repo", DefaultGitHubRepo);
            config = EnsureJsonStringProperty(config, "github_branch", DefaultGitHubBranch);
            Match match = Regex.Match(config, "\"manifest_url\"\\s*:\\s*\"(?<value>(?:\\\\.|[^\"])*)\"");
            if (match.Success)
            {
                string current = JsonUnescape(match.Groups["value"].Value).Trim();
                if (!string.IsNullOrWhiteSpace(current) && !IsLegacyUpdateEndpoint(current))
                {
                    File.WriteAllText(path, config, Encoding.UTF8);
                    log.Write("Configuracao de atualizacao preservada: " + current);
                    return;
                }

                string replacement = "\"manifest_url\": \"" + JsonEscape(DefaultUpdateEndpointUrl) + "\"";
                config = config.Substring(0, match.Index) + replacement + config.Substring(match.Index + match.Length);
                File.WriteAllText(path, config, Encoding.UTF8);
                log.Write("Configuracao de atualizacao preenchida: GitHub " + DefaultGitHubRepo);
                return;
            }

            string trimmed = config.TrimEnd();
            int closeIndex = trimmed.LastIndexOf('}');
            if (closeIndex >= 0)
            {
                string before = trimmed.Substring(0, closeIndex).TrimEnd();
                if (!before.EndsWith("{", StringComparison.Ordinal))
                {
                    before += ",";
                }
                string after = trimmed.Substring(closeIndex);
                config = before + "\r\n  \"manifest_url\": \"" + JsonEscape(DefaultUpdateEndpointUrl) + "\"\r\n" + after + "\r\n";
                File.WriteAllText(path, config, Encoding.UTF8);
                log.Write("Configuracao de atualizacao adicionada: GitHub " + DefaultGitHubRepo);
                return;
            }
        }
        catch (Exception ex)
        {
            log.Write("Nao foi possivel ajustar update_config.json: " + ex.Message);
            return;
        }

        File.WriteAllText(path, defaultConfig, Encoding.UTF8);
        log.Write("Configuracao de atualizacao recriada: GitHub " + DefaultGitHubRepo);
    }

    private static string EnsureJsonStringProperty(string config, string propertyName, string value)
    {
        Match match = Regex.Match(config, "\"" + Regex.Escape(propertyName) + "\"\\s*:");
        if (match.Success)
        {
            return config;
        }

        string trimmed = config.TrimEnd();
        int closeIndex = trimmed.LastIndexOf('}');
        if (closeIndex < 0)
        {
            return config;
        }

        string before = trimmed.Substring(0, closeIndex).TrimEnd();
        if (!before.EndsWith("{", StringComparison.Ordinal))
        {
            before += ",";
        }
        string after = trimmed.Substring(closeIndex);
        return before + "\r\n  \"" + propertyName + "\": \"" + JsonEscape(value) + "\"\r\n" + after + "\r\n";
    }

    private static void InstallPython(string runtimeDir, string downloadDir, InstallerLog log)
    {
        string pythonDir = Path.Combine(runtimeDir, "python");
        string pythonw = Path.Combine(pythonDir, "pythonw.exe");
        if (ValidatePythonRuntime(pythonDir, log))
        {
            log.Write("Python local ja instalado: " + pythonw);
            return;
        }
        if (Directory.Exists(pythonDir))
        {
            log.Write("Removendo instalacao parcial do Python: " + pythonDir);
            Directory.Delete(pythonDir, true);
        }

        try
        {
            InstallPythonFromRuntimeZip(pythonDir, downloadDir, log);
        }
        catch (Exception ex)
        {
            log.Write("Instalacao pelo runtime ZIP falhou: " + ex.Message);
            if (Directory.Exists(pythonDir))
            {
                Directory.Delete(pythonDir, true);
            }
            InstallPythonFromOfficialInstaller(pythonDir, downloadDir, log);
        }

        if (!ValidatePythonRuntime(pythonDir, log))
        {
            throw new FileNotFoundException(
                "Python foi instalado, mas a validacao falhou em " + pythonDir + ". Verifique se python.exe, pythonw.exe e tkinter existem.",
                pythonw);
        }
        log.Write("Python instalado e validado em: " + pythonDir);
    }

    private static void InstallPythonFromRuntimeZip(string pythonDir, string downloadDir, InstallerLog log)
    {
        string zipPath = Path.Combine(downloadDir, PythonRuntimeZipName);
        string extractDir = Path.Combine(downloadDir, "python_runtime_extract");
        DownloadFile(PythonRuntimeZipUrl, zipPath, "Python runtime", log);

        if (Directory.Exists(extractDir))
        {
            Directory.Delete(extractDir, true);
        }
        Directory.CreateDirectory(extractDir);

        log.Write("Extraindo Python runtime...");
        ZipFile.ExtractToDirectory(zipPath, extractDir);

        string extractedPythonw = Directory.GetFiles(extractDir, "pythonw.exe", SearchOption.AllDirectories).FirstOrDefault();
        if (string.IsNullOrWhiteSpace(extractedPythonw))
        {
            throw new FileNotFoundException("Pacote Python runtime nao contem pythonw.exe.");
        }

        string sourceDir = Path.GetDirectoryName(extractedPythonw);
        if (Directory.Exists(pythonDir))
        {
            Directory.Delete(pythonDir, true);
        }
        Directory.CreateDirectory(Path.GetDirectoryName(pythonDir));
        CopyDirectory(sourceDir, pythonDir);
        Directory.Delete(extractDir, true);
    }

    private static void InstallPythonFromOfficialInstaller(string pythonDir, string downloadDir, InstallerLog log)
    {
        string pythonw = Path.Combine(pythonDir, "pythonw.exe");
        string installerPath = Path.Combine(downloadDir, "python-" + PythonVersion + "-amd64.exe");
        string installerLogPath = Path.Combine(downloadDir, "python-installer.log");
        DownloadFile(PythonUrl, installerPath, "Python", log);

        Directory.CreateDirectory(pythonDir);
        string arguments =
            "/quiet " +
            "/log \"" + installerLogPath + "\" " +
            "InstallAllUsers=0 " +
            "TargetDir=\"" + pythonDir + "\" " +
            "DefaultJustForMeTargetDir=\"" + pythonDir + "\" " +
            "Include_tcltk=1 Include_pip=0 Include_test=0 Include_doc=0 " +
            "Include_launcher=0 InstallLauncherAllUsers=0 AssociateFiles=0 Shortcuts=0 PrependPath=0";

        log.Write("Instalando Python local...");
        log.Write("Log do instalador Python: " + installerLogPath);
        int exitCode = RunProcess(installerPath, arguments, log);
        if (exitCode != 0)
        {
            throw new InvalidOperationException("Instalador do Python retornou codigo " + exitCode + ".");
        }

        if (!File.Exists(pythonw))
        {
            string installedPythonw = FindInstalledPythonw(pythonDir, log);
            if (!string.IsNullOrWhiteSpace(installedPythonw))
            {
                string installedDir = Path.GetDirectoryName(installedPythonw);
                log.Write("Python instalado fora da pasta esperada: " + installedDir);
                log.Write("Copiando Python para: " + pythonDir);
                if (Directory.Exists(pythonDir))
                {
                    Directory.Delete(pythonDir, true);
                }
                CopyDirectory(installedDir, pythonDir);
            }
        }
    }

    private static bool ValidatePythonRuntime(string pythonDir, InstallerLog log)
    {
        string python = Path.Combine(pythonDir, "python.exe");
        string pythonw = Path.Combine(pythonDir, "pythonw.exe");
        if (!File.Exists(python) || !File.Exists(pythonw))
        {
            return false;
        }

        int exitCode = RunProcess(
            python,
            "-c \"import sys, tkinter; print(sys.version.split()[0]); print('tkinter ok')\"",
            log);
        if (exitCode != 0)
        {
            log.Write("Validacao do Python falhou com codigo " + exitCode + ".");
            return false;
        }
        return true;
    }

    private static string FindInstalledPythonw(string expectedPythonDir, InstallerLog log)
    {
        List<string> candidates = new List<string>();
        AddPythonCandidate(candidates, Path.Combine(expectedPythonDir, "pythonw.exe"));
        AddPythonCandidate(candidates, Path.Combine(expectedPythonDir, "python.exe"));

        string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string programFilesX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);

        AddPythonCandidate(candidates, Path.Combine(localAppData, "Programs", "Python", "Python312", "pythonw.exe"));
        AddPythonCandidate(candidates, Path.Combine(programFiles, "Python312", "pythonw.exe"));
        AddPythonCandidate(candidates, Path.Combine(programFilesX86, "Python312", "pythonw.exe"));

        foreach (string root in new[] {
            Path.Combine(localAppData, "Programs", "Python"),
            Path.Combine(programFiles, "Python312"),
            Path.Combine(programFilesX86, "Python312"),
        })
        {
            try
            {
                if (!Directory.Exists(root))
                {
                    continue;
                }
                foreach (string found in Directory.GetFiles(root, "pythonw.exe", SearchOption.AllDirectories))
                {
                    AddPythonCandidate(candidates, found);
                }
            }
            catch (Exception ex)
            {
                log.Write("Busca de Python ignorada em " + root + ": " + ex.Message);
            }
        }

        foreach (string candidate in candidates.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            if (File.Exists(candidate) && File.Exists(Path.Combine(Path.GetDirectoryName(candidate), "python.exe")))
            {
                return candidate;
            }
        }
        return "";
    }

    private static void AddPythonCandidate(List<string> candidates, string path)
    {
        if (!string.IsNullOrWhiteSpace(path))
        {
            candidates.Add(path);
        }
    }

    private static void InstallFfmpeg(string runtimeDir, string downloadDir, InstallerLog log)
    {
        string ffmpegDir = Path.Combine(runtimeDir, "ffmpeg");
        string ffmpegExe = Path.Combine(ffmpegDir, "bin", "ffmpeg.exe");
        string ffprobeExe = Path.Combine(ffmpegDir, "bin", "ffprobe.exe");
        if (File.Exists(ffmpegExe) && File.Exists(ffprobeExe))
        {
            log.Write("ffmpeg local ja instalado: " + ffmpegExe);
            return;
        }

        string zipPath = Path.Combine(downloadDir, "ffmpeg-release-essentials.zip");
        string tempExtract = Path.Combine(downloadDir, "ffmpeg_extract");
        DownloadFile(FfmpegUrl, zipPath, "ffmpeg", log);

        if (Directory.Exists(tempExtract))
        {
            Directory.Delete(tempExtract, true);
        }
        Directory.CreateDirectory(tempExtract);

        log.Write("Extraindo ffmpeg...");
        ZipFile.ExtractToDirectory(zipPath, tempExtract);

        string foundFfmpeg = Directory.GetFiles(tempExtract, "ffmpeg.exe", SearchOption.AllDirectories).FirstOrDefault();
        if (foundFfmpeg == null)
        {
            throw new FileNotFoundException("ffmpeg.exe nao foi encontrado dentro do zip baixado.");
        }

        string binDir = Path.GetDirectoryName(foundFfmpeg);
        string sourceRoot = binDir == null ? null : Directory.GetParent(binDir).FullName;
        if (sourceRoot == null)
        {
            throw new InvalidOperationException("Estrutura do ffmpeg baixado nao foi reconhecida.");
        }

        if (Directory.Exists(ffmpegDir))
        {
            Directory.Delete(ffmpegDir, true);
        }
        CopyDirectory(sourceRoot, ffmpegDir);
        Directory.Delete(tempExtract, true);

        if (!File.Exists(ffmpegExe) || !File.Exists(ffprobeExe))
        {
            throw new FileNotFoundException("ffmpeg/ffprobe nao foram instalados corretamente.");
        }
        log.Write("ffmpeg instalado em: " + ffmpegDir);
    }

    private static bool IsLegacyUpdateEndpoint(string url)
    {
        return !string.IsNullOrWhiteSpace(url) &&
            (url.IndexOf("api.base44.com/api/apps/6a0a893b79eb8fdc64346940/functions/update", StringComparison.OrdinalIgnoreCase) >= 0 ||
             url.IndexOf("key-flow-core.base44.app/functions/update", StringComparison.OrdinalIgnoreCase) >= 0 ||
             url.IndexOf("key-flow-core.base44.app/versions", StringComparison.OrdinalIgnoreCase) >= 0);
    }
    private static bool ShouldSkipUpdate(string[] args)
    {
        return HasArg(args, "/skip-update") ||
            HasArg(args, "--skip-update") ||
            HasArg(args, "/no-update") ||
            HasArg(args, "--no-update");
    }

    private static bool TryRunNewerSetupFromSite(string[] args, string appDir, string downloadDir, string setupVersion, InstallerLog log)
    {
        try
        {
            log.Write("Verificando atualizacoes em: " + DefaultUpdateEndpointUrl);
            UpdateInfo update = FetchLatestUpdate(DefaultUpdateEndpointUrl);
            if (update == null)
            {
                log.Write("Nenhuma atualizacao valida foi encontrada no endpoint.");
                return false;
            }

            if (!IsNewerVersion(update.Version, setupVersion))
            {
                log.Write("Setup ja esta atualizado (local v" + setupVersion + ", endpoint v" + update.Version + ").");
                return false;
            }

            log.Write("Atualizacao encontrada no endpoint: v" + update.Version + " (local v" + setupVersion + ").");
            Console.WriteLine("Nova versao encontrada: v" + update.Version + ". Baixando setup atualizado...");
            string setupPath = DownloadUpdateSetup(update, downloadDir, log);
            string relaunchArgs = BuildRelaunchArguments(args, appDir);
            log.Write("Executando setup atualizado: " + setupPath + " " + relaunchArgs);
            int exitCode = RunProcess(setupPath, relaunchArgs, log);
            if (exitCode == 0)
            {
                log.Write("Setup atualizado concluiu a instalacao.");
                return true;
            }

            log.Write("Setup atualizado retornou codigo " + exitCode + ". Continuando com o setup atual.");
            return false;
        }
        catch (Exception ex)
        {
            log.Write("Verificacao de atualizacao ignorada: " + ex.Message);
            return false;
        }
    }

    private static UpdateInfo FetchLatestUpdate(string endpointUrl)
    {
        if (endpointUrl.IndexOf("api.github.com/repos/", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            try
            {
                return FetchLatestUpdateFromEndpoint(endpointUrl);
            }
            catch
            {
                return FetchLatestUpdateFromGitHubRepository(DefaultGitHubRepo, DefaultGitHubBranch);
            }
        }

        return FetchLatestUpdateFromEndpoint(endpointUrl);
    }

    private static UpdateInfo FetchLatestUpdateFromEndpoint(string endpointUrl)
    {
        string raw = DownloadUpdateEndpoint(endpointUrl);
        string trimmed = (raw ?? "").TrimStart('\uFEFF', ' ', '\r', '\n', '\t');
        if (trimmed.StartsWith("<", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("O endpoint retornou HTML em vez de JSON publico de atualizacao.");
        }

        JavaScriptSerializer serializer = new JavaScriptSerializer { MaxJsonLength = 4 * 1024 * 1024 };
        object root;
        try
        {
            root = serializer.DeserializeObject(trimmed);
        }
        catch (Exception ex)
        {
            throw new InvalidOperationException("Resposta de atualizacao invalida. O endpoint precisa retornar JSON.", ex);
        }

        Dictionary<string, object> release = root as Dictionary<string, object>;
        if (release != null && endpointUrl.IndexOf("api.github.com/repos/", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            UpdateInfo githubUpdate = UpdateFromGitHubRelease(release);
            if (githubUpdate != null)
            {
                return githubUpdate;
            }
        }

        List<UpdateInfo> updates = new List<UpdateInfo>();
        CollectUpdateCandidates(root, updates, endpointUrl, serializer);
        return updates
            .Where(item => !string.IsNullOrWhiteSpace(item.Version) && (!string.IsNullOrWhiteSpace(item.ZipUrl) || !string.IsNullOrWhiteSpace(item.SetupUrl)))
            .OrderByDescending(item => VersionSortKey(item.Version), StringComparer.Ordinal)
            .FirstOrDefault();
    }

    private static UpdateInfo FetchLatestUpdateFromGitHubRepository(string repo, string branch)
    {
        string version = DownloadUpdateText(GitHubRawUrl(repo, branch, "VERSION")).Trim();
        version = Regex.Replace(version, "^[vV]", "");
        if (string.IsNullOrWhiteSpace(version))
        {
            return null;
        }

        string notes = "";
        try
        {
            notes = DownloadUpdateText(GitHubRawUrl(repo, branch, "CHANGELOG.md"));
            if (notes.Length > 4000)
            {
                notes = notes.Substring(0, 4000);
            }
        }
        catch
        {
            notes = "";
        }

        return new UpdateInfo
        {
            Version = version,
            SetupUrl = GitHubRawUrl(repo, branch, SetupFileName),
            Notes = notes,
        };
    }

    private static string GitHubRawUrl(string repo, string branch, string path)
    {
        string slug = NormalizeGitHubRepo(repo);
        if (string.IsNullOrWhiteSpace(slug))
        {
            throw new InvalidOperationException("Repositorio GitHub invalido. Use o formato dono/repositorio.");
        }

        return "https://raw.githubusercontent.com/" + slug + "/" + Uri.EscapeDataString(branch) + "/" + string.Join("/", path.Split('/').Select(Uri.EscapeDataString));
    }

    private static string NormalizeGitHubRepo(string value)
    {
        value = (value ?? "").Trim().Trim('/');
        value = Regex.Replace(value, "^https?://github\\.com/", "", RegexOptions.IgnoreCase).Trim('/');
        value = Regex.Replace(value, "\\.git$", "", RegexOptions.IgnoreCase);
        string[] parts = value.Split(new[] { '/' }, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 2)
        {
            return "";
        }
        return parts[0] + "/" + parts[1];
    }

    private static UpdateInfo UpdateFromGitHubRelease(Dictionary<string, object> release)
    {
        string version = DictionaryString(release, "tag_name", "name", "version").Trim();
        version = Regex.Replace(version, "^[vV]", "");
        object assetsObject;
        object[] assets = release.TryGetValue("assets", out assetsObject) ? assetsObject as object[] : null;
        if (string.IsNullOrWhiteSpace(version) || assets == null)
        {
            return null;
        }

        string setupUrl = "";
        string zipUrl = "";
        string sha256 = "";

        foreach (object assetObject in assets)
        {
            Dictionary<string, object> asset = assetObject as Dictionary<string, object>;
            if (asset == null)
            {
                continue;
            }

            string name = DictionaryString(asset, "name");
            string downloadUrl = DictionaryString(asset, "browser_download_url", "download_url", "url");
            if (string.IsNullOrWhiteSpace(downloadUrl))
            {
                continue;
            }

            string lowerName = name.ToLowerInvariant();
            string lowerUrl = downloadUrl.ToLowerInvariant();
            if (string.IsNullOrWhiteSpace(setupUrl) && lowerName.EndsWith(".exe", StringComparison.Ordinal) && (lowerName.Contains("setup") || lowerName.Contains("encut")))
            {
                setupUrl = downloadUrl;
                sha256 = Sha256FromGitHubAsset(asset);
            }
            else if (string.IsNullOrWhiteSpace(zipUrl) && lowerName.EndsWith(".zip", StringComparison.Ordinal) && lowerName.Contains("encut"))
            {
                zipUrl = downloadUrl;
                if (string.IsNullOrWhiteSpace(sha256))
                {
                    sha256 = Sha256FromGitHubAsset(asset);
                }
            }
            else if (string.IsNullOrWhiteSpace(setupUrl) && lowerUrl.EndsWith(".exe", StringComparison.Ordinal))
            {
                setupUrl = downloadUrl;
                sha256 = Sha256FromGitHubAsset(asset);
            }
            else if (string.IsNullOrWhiteSpace(zipUrl) && lowerUrl.EndsWith(".zip", StringComparison.Ordinal))
            {
                zipUrl = downloadUrl;
                if (string.IsNullOrWhiteSpace(sha256))
                {
                    sha256 = Sha256FromGitHubAsset(asset);
                }
            }
        }

        if (string.IsNullOrWhiteSpace(setupUrl) && string.IsNullOrWhiteSpace(zipUrl))
        {
            return null;
        }

        return new UpdateInfo
        {
            Version = version,
            ZipUrl = zipUrl,
            SetupUrl = setupUrl,
            Sha256 = sha256,
            Notes = DictionaryString(release, "body", "notes", "changelog", "description").Trim(),
        };
    }

    private static string Sha256FromGitHubAsset(Dictionary<string, object> asset)
    {
        string digest = DictionaryString(asset, "digest").Trim();
        if (digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase))
        {
            return digest.Substring("sha256:".Length).Trim().ToLowerInvariant();
        }
        return DictionaryString(asset, "sha256", "sha_256", "hash", "checksum").Trim().ToLowerInvariant();
    }

    private static string DownloadUpdateEndpoint(string endpointUrl)
    {
        try
        {
            using (WebClient client = CreateUpdateWebClient())
            {
                return client.DownloadString(endpointUrl);
            }
        }
        catch (WebException firstError)
        {
            try
            {
                using (WebClient client = CreateUpdateWebClient())
                {
                    client.Headers[HttpRequestHeader.ContentType] = "application/json";
                    return client.UploadString(endpointUrl, "POST", "{}");
                }
            }
            catch
            {
                throw firstError;
            }
        }
    }

    private static string DownloadUpdateText(string url)
    {
        using (WebClient client = CreateUpdateWebClient())
        {
            return client.DownloadString(url);
        }
    }

    private static WebClient CreateUpdateWebClient()
    {
        WebClient client = new WebClient();
        client.Encoding = Encoding.UTF8;
        client.Headers[HttpRequestHeader.Accept] = "application/json";
        client.Headers[HttpRequestHeader.UserAgent] = AppName + " Setup/" + ReadEmbeddedVersion();
        return client;
    }

    private static void CollectUpdateCandidates(object node, List<UpdateInfo> updates, string endpointUrl, JavaScriptSerializer serializer)
    {
        Dictionary<string, object> dict = node as Dictionary<string, object>;
        if (dict != null)
        {
            UpdateInfo update = UpdateFromDictionary(dict, endpointUrl);
            if (update != null)
            {
                updates.Add(update);
            }

            foreach (object value in dict.Values)
            {
                CollectUpdateCandidates(value, updates, endpointUrl, serializer);
            }
            return;
        }

        object[] array = node as object[];
        if (array != null)
        {
            foreach (object item in array)
            {
                CollectUpdateCandidates(item, updates, endpointUrl, serializer);
            }
            return;
        }

        string text = node as string;
        if (text == null)
        {
            return;
        }

        string trimmed = text.TrimStart('\uFEFF', ' ', '\r', '\n', '\t');
        if (!(trimmed.StartsWith("{", StringComparison.Ordinal) || trimmed.StartsWith("[", StringComparison.Ordinal)))
        {
            return;
        }

        try
        {
            CollectUpdateCandidates(serializer.DeserializeObject(trimmed), updates, endpointUrl, serializer);
        }
        catch
        {
            // String comum, nao um JSON interno.
        }
    }

    private static string NormalizeDownloadUrl(string downloadUrl)
    {
        if (string.IsNullOrWhiteSpace(downloadUrl))
        {
            return "";
        }
        if (downloadUrl.IndexOf("api.base44.com/api/apps/6a0a893b79eb8fdc64346940/functions/downloadLatest", StringComparison.OrdinalIgnoreCase) >= 0)
        {
            return DefaultDownloadUrl;
        }
        return downloadUrl;
    }
    private static UpdateInfo UpdateFromDictionary(Dictionary<string, object> dict, string endpointUrl)
    {
        string version = DictionaryString(dict, "version", "app_version", "appVersion", "latest_version", "latestVersion", "versao", "versão");
        string zipUrl = DictionaryString(dict, "zip_url", "zipUrl", "package_url", "packageUrl", "package", "zip", "arquivo_zip");
        string setupUrl = DictionaryString(dict, "setup_url", "setupUrl", "installer_url", "installerUrl", "setup", "installer", "setup_exe");
        string downloadUrl = DictionaryString(dict, "download_url", "downloadUrl", "file_url", "fileUrl", "url", "href", "download", "link");
        if (string.IsNullOrWhiteSpace(zipUrl) && string.IsNullOrWhiteSpace(setupUrl))
        {
            downloadUrl = NormalizeDownloadUrl(downloadUrl);
            if (string.IsNullOrWhiteSpace(downloadUrl))
            {
                downloadUrl = DefaultDownloadUrl;
            }
            if (downloadUrl.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
            {
                setupUrl = downloadUrl;
            }
            else
            {
                zipUrl = downloadUrl;
            }
        }

        if (string.IsNullOrWhiteSpace(version) || (string.IsNullOrWhiteSpace(zipUrl) && string.IsNullOrWhiteSpace(setupUrl)))
        {
            return null;
        }

        return new UpdateInfo
        {
            Version = version.Trim(),
            ZipUrl = ResolveUpdateUrl(endpointUrl, zipUrl.Trim()),
            SetupUrl = ResolveUpdateUrl(endpointUrl, setupUrl.Trim()),
            Sha256 = DictionaryString(dict, "sha256", "sha_256", "hash", "checksum").Trim(),
            Notes = DictionaryString(dict, "notes", "changelog", "description", "descricao", "descrição").Trim(),
        };
    }

    private static string DictionaryString(Dictionary<string, object> dict, params string[] names)
    {
        foreach (string name in names)
        {
            foreach (KeyValuePair<string, object> item in dict)
            {
                if (string.Equals(item.Key, name, StringComparison.OrdinalIgnoreCase) && item.Value != null)
                {
                    if (item.Value is Dictionary<string, object> || item.Value is object[])
                    {
                        continue;
                    }
                    return Convert.ToString(item.Value) ?? "";
                }
            }
        }
        return "";
    }

    private static string ResolveUpdateUrl(string endpointUrl, string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "";
        }

        Uri absolute;
        if (Uri.TryCreate(value, UriKind.Absolute, out absolute))
        {
            return absolute.ToString();
        }

        Uri baseUri;
        if (Uri.TryCreate(endpointUrl, UriKind.Absolute, out baseUri))
        {
            return new Uri(baseUri, value).ToString();
        }

        return value;
    }

    private static string DownloadUpdateSetup(UpdateInfo update, string downloadDir, InstallerLog log)
    {
        Directory.CreateDirectory(downloadDir);
        string safeVersion = SafeFilePart(update.Version);
        if (!string.IsNullOrWhiteSpace(update.SetupUrl))
        {
            string setupPath = Path.Combine(downloadDir, "EncutSetup_" + safeVersion + ".exe");
            DownloadFileFresh(update.SetupUrl, setupPath, "setup v" + update.Version, log);
            ValidateSha256IfPresent(setupPath, update.Sha256);
            return setupPath;
        }

        string zipPath = Path.Combine(downloadDir, "Encut_" + safeVersion + ".zip");
        string extractDir = Path.Combine(downloadDir, "update_" + safeVersion);
        DownloadFileFresh(update.ZipUrl, zipPath, "pacote v" + update.Version, log);
        ValidateSha256IfPresent(zipPath, update.Sha256);
        if (Directory.Exists(extractDir))
        {
            Directory.Delete(extractDir, true);
        }
        Directory.CreateDirectory(extractDir);
        ZipFile.ExtractToDirectory(zipPath, extractDir);
        string extractedSetupPath = Directory.GetFiles(extractDir, SetupFileName, SearchOption.AllDirectories).FirstOrDefault();
        if (extractedSetupPath == null)
        {
            throw new FileNotFoundException("Pacote de atualizacao nao contem " + SetupFileName + ".");
        }
        return extractedSetupPath;
    }

    private static void DownloadFileFresh(string url, string destination, string label, InstallerLog log)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(destination));
        string temp = destination + ".tmp";
        if (File.Exists(temp))
        {
            File.Delete(temp);
        }
        if (File.Exists(destination))
        {
            File.Delete(destination);
        }

        log.Write("Baixando " + label + ": " + url);
        using (WebClient client = CreateUpdateWebClient())
        {
            client.DownloadFile(url, temp);
        }
        File.Move(temp, destination);
        log.Write(label + " baixado em: " + destination);
    }

    private static void ValidateSha256IfPresent(string path, string expected)
    {
        if (string.IsNullOrWhiteSpace(expected))
        {
            return;
        }

        string actual = Sha256File(path);
        if (!string.Equals(actual, expected.Trim(), StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Hash SHA256 da atualizacao nao confere.");
        }
    }

    private static string Sha256File(string path)
    {
        using (SHA256 sha = SHA256.Create())
        using (FileStream stream = File.OpenRead(path))
        {
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
    }

    private static bool IsNewerVersion(string remoteVersion, string localVersion)
    {
        return CompareVersions(remoteVersion, localVersion) > 0;
    }

    private static int CompareVersions(string a, string b)
    {
        int[] left = VersionParts(a);
        int[] right = VersionParts(b);
        for (int index = 0; index < left.Length; index++)
        {
            int compared = left[index].CompareTo(right[index]);
            if (compared != 0)
            {
                return compared;
            }
        }
        return 0;
    }

    private static int[] VersionParts(string value)
    {
        MatchCollection matches = Regex.Matches(value ?? "", "\\d+");
        int[] parts = new int[] { 0, 0, 0, 0 };
        for (int index = 0; index < parts.Length && index < matches.Count; index++)
        {
            int parsed;
            if (int.TryParse(matches[index].Value, out parsed))
            {
                parts[index] = parsed;
            }
        }
        return parts;
    }

    private static string VersionSortKey(string version)
    {
        int[] parts = VersionParts(version);
        return parts[0].ToString("D6") + "." + parts[1].ToString("D6") + "." + parts[2].ToString("D6") + "." + parts[3].ToString("D6");
    }

    private static string BuildRelaunchArguments(string[] args, string appDir)
    {
        List<string> forwarded = new List<string>();
        bool hasDir = false;
        bool hasSilent = false;
        foreach (string arg in args)
        {
            if (string.Equals(arg, "/skip-update", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(arg, "--skip-update", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(arg, "/no-update", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(arg, "--no-update", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            if (arg.StartsWith("/dir=", StringComparison.OrdinalIgnoreCase))
            {
                hasDir = true;
            }
            if (string.Equals(arg, "/silent", StringComparison.OrdinalIgnoreCase) || string.Equals(arg, "--silent", StringComparison.OrdinalIgnoreCase))
            {
                hasSilent = true;
            }
            forwarded.Add(QuoteArg(arg));
        }
        if (!hasDir)
        {
            forwarded.Add(QuoteArg("/dir=" + appDir));
        }
        if (!hasSilent)
        {
            forwarded.Add("/silent");
        }
        forwarded.Add("/skip-update");
        return string.Join(" ", forwarded.ToArray());
    }

    private static string QuoteArg(string arg)
    {
        if (string.IsNullOrEmpty(arg))
        {
            return "\"\"";
        }
        if (arg.IndexOfAny(new[] { ' ', '\t', '\"' }) < 0)
        {
            return arg;
        }
        return "\"" + arg.Replace("\"", "\\\"") + "\"";
    }

    private static string SafeFilePart(string value)
    {
        string safe = Regex.Replace(value ?? "", "[^0-9A-Za-z._-]+", "_");
        return string.IsNullOrWhiteSpace(safe) ? "update" : safe;
    }
    private static void DownloadFile(string url, string destination, string label, InstallerLog log)
    {
        if (File.Exists(destination) && new FileInfo(destination).Length > 0)
        {
            log.Write(label + " ja baixado: " + destination);
            return;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(destination));
        string temp = destination + ".tmp";
        if (File.Exists(temp))
        {
            File.Delete(temp);
        }

        log.Write("Baixando " + label + ": " + url);
        Console.WriteLine("Baixando " + label + ". Isso pode demorar alguns minutos...");
        using (WebClient client = new WebClient())
        {
            client.DownloadFile(url, temp);
        }

        if (File.Exists(destination))
        {
            File.Delete(destination);
        }
        File.Move(temp, destination);
        log.Write(label + " baixado em: " + destination);
    }

    private static int RunProcess(string fileName, string arguments, InstallerLog log)
    {
        ProcessStartInfo startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            Arguments = arguments,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        using (Process process = Process.Start(startInfo))
        {
            if (process == null)
            {
                throw new InvalidOperationException("Nao foi possivel iniciar: " + fileName);
            }
            process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    log.Write(e.Data);
                }
            };
            process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
            {
                if (!string.IsNullOrWhiteSpace(e.Data))
                {
                    log.Write(e.Data);
                }
            };
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    private static string CreateDesktopShortcut(string appDir, InstallerLog log)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string shortcut = Path.Combine(desktop, AppName + ".lnk");
        CreateShortcut(shortcut, Path.Combine(appDir, "iniciar.exe"), "", appDir, "Abrir " + AppName, Path.Combine(appDir, "iniciar.exe"));
        log.Write("Atalho da area de trabalho: " + shortcut);
        return shortcut;
    }

    private static ShortcutPair CreateStartMenuShortcuts(string appDir, string installDir, InstallerLog log)
    {
        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        string startMenuDir = Path.Combine(programs, AppName);
        Directory.CreateDirectory(startMenuDir);

        string appShortcut = Path.Combine(startMenuDir, AppName + ".lnk");
        string uninstallShortcut = Path.Combine(startMenuDir, "Desinstalar " + AppName + ".lnk");
        string setupCopy = Path.Combine(installDir, SetupFileName);

        CreateShortcut(appShortcut, Path.Combine(appDir, "iniciar.exe"), "", appDir, "Abrir " + AppName, Path.Combine(appDir, "iniciar.exe"));
        CreateShortcut(uninstallShortcut, setupCopy, "/uninstall", appDir, "Desinstalar " + AppName, setupCopy);

        log.Write("Atalhos do Menu Iniciar: " + startMenuDir);
        return new ShortcutPair(appShortcut, uninstallShortcut);
    }

    private static void CreateShortcut(string shortcutPath, string targetPath, string arguments, string workingDirectory, string description, string iconPath)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(shortcutPath));
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType == null)
        {
            throw new InvalidOperationException("WScript.Shell nao esta disponivel.");
        }
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { shortcutPath });

        SetComProperty(shortcut, "TargetPath", targetPath);
        SetComProperty(shortcut, "Arguments", arguments);
        SetComProperty(shortcut, "WorkingDirectory", workingDirectory);
        SetComProperty(shortcut, "Description", description);
        SetComProperty(shortcut, "IconLocation", iconPath);
        shortcut.GetType().InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, new object[0]);

        if (Marshal.IsComObject(shortcut))
        {
            Marshal.FinalReleaseComObject(shortcut);
        }
        if (Marshal.IsComObject(shell))
        {
            Marshal.FinalReleaseComObject(shell);
        }
    }

    private static void SetComProperty(object target, string name, object value)
    {
        target.GetType().InvokeMember(name, BindingFlags.SetProperty, null, target, new[] { value });
    }

    private static void RegisterUninstaller(string appDir, string installDir, InstallerLog log)
    {
        string setupCopy = Path.Combine(installDir, SetupFileName);
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppId))
        {
            if (key == null)
            {
                throw new InvalidOperationException("Nao foi possivel criar a chave de desinstalacao.");
            }

            key.SetValue("DisplayName", AppName, RegistryValueKind.String);
            key.SetValue("DisplayVersion", ReadVersion(appDir), RegistryValueKind.String);
            key.SetValue("Publisher", "Codex local", RegistryValueKind.String);
            key.SetValue("InstallLocation", appDir, RegistryValueKind.String);
            key.SetValue("DisplayIcon", Path.Combine(appDir, "iniciar.exe"), RegistryValueKind.String);
            key.SetValue("UninstallString", "\"" + setupCopy + "\" /uninstall", RegistryValueKind.String);
            key.SetValue("QuietUninstallString", "\"" + setupCopy + "\" /uninstall /silent /keep", RegistryValueKind.String);
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
        }
        log.Write("Registro de desinstalacao configurado.");
    }

    private static void UnregisterUninstaller(InstallerLog log)
    {
        using (RegistryKey parent = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall", true))
        {
            if (parent != null)
            {
                try
                {
                    parent.DeleteSubKeyTree(AppId);
                }
                catch (ArgumentException)
                {
                    // Already removed.
                }
                try
                {
                    parent.DeleteSubKeyTree(LegacyAppId);
                }
                catch (ArgumentException)
                {
                    // Already removed.
                }
            }
        }
        log.Write("Registro de desinstalacao removido.");
    }

    private static void RemoveLegacyInstallArtifacts(string appDir, InstallerLog log)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        string legacyStartMenuDir = Path.Combine(programs, LegacyAppName);

        string[] legacyPaths = new[]
        {
            Path.Combine(desktop, LegacyAppName + ".lnk"),
            Path.Combine(legacyStartMenuDir, LegacyAppName + ".lnk"),
            Path.Combine(legacyStartMenuDir, "Desinstalar " + LegacyAppName + ".lnk"),
            Path.Combine(appDir, LegacySetupFileName),
            Path.Combine(appDir, "instalacao", LegacySetupFileName),
        };

        foreach (string path in legacyPaths)
        {
            if (File.Exists(path))
            {
                File.Delete(path);
                log.Write("Artefato antigo removido: " + path);
            }
        }

        if (Directory.Exists(legacyStartMenuDir) && Directory.GetFileSystemEntries(legacyStartMenuDir).Length == 0)
        {
            Directory.Delete(legacyStartMenuDir);
            log.Write("Pasta antiga do Menu Iniciar removida: " + legacyStartMenuDir);
        }

        using (RegistryKey parent = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall", true))
        {
            if (parent != null)
            {
                try
                {
                    parent.DeleteSubKeyTree(LegacyAppId);
                    log.Write("Registro antigo removido: " + LegacyAppId);
                }
                catch (ArgumentException)
                {
                    // Already removed.
                }
            }
        }
    }

    private static void WriteManifest(string appDir, string installDir, string desktopShortcut, string startShortcut, string uninstallShortcut, InstallerLog log)
    {
        InstallManifest manifest = new InstallManifest
        {
            app_name = AppName,
            app_id = AppId,
            version = ReadVersion(appDir),
            installed_at = DateTime.Now.ToString("s"),
            install_location = appDir,
            desktop_shortcut = desktopShortcut,
            start_menu_shortcut = startShortcut,
            start_menu_uninstall_shortcut = uninstallShortcut,
            setup_exe = Path.Combine(installDir, SetupFileName),
            python_path = Path.Combine(appDir, "runtime", "python", "pythonw.exe"),
            ffmpeg_path = Path.Combine(appDir, "runtime", "ffmpeg", "bin", "ffmpeg.exe"),
        };

        string manifestPath = Path.Combine(installDir, "instalacao.json");
        File.WriteAllText(manifestPath, ManifestToJson(manifest), Encoding.UTF8);
        log.Write("Manifesto salvo: " + manifestPath);
    }

    private static void RemoveShortcuts(string appDir, InstallerLog log)
    {
        InstallManifest manifest = ReadManifest(appDir);
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        string startMenuDir = Path.Combine(programs, AppName);
        string legacyStartMenuDir = Path.Combine(programs, LegacyAppName);

        string[] paths = new[]
        {
            manifest != null && !string.IsNullOrWhiteSpace(manifest.desktop_shortcut) ? manifest.desktop_shortcut : Path.Combine(desktop, AppName + ".lnk"),
            manifest != null && !string.IsNullOrWhiteSpace(manifest.start_menu_shortcut) ? manifest.start_menu_shortcut : Path.Combine(startMenuDir, AppName + ".lnk"),
            manifest != null && !string.IsNullOrWhiteSpace(manifest.start_menu_uninstall_shortcut) ? manifest.start_menu_uninstall_shortcut : Path.Combine(startMenuDir, "Desinstalar " + AppName + ".lnk"),
            Path.Combine(desktop, LegacyAppName + ".lnk"),
            Path.Combine(legacyStartMenuDir, LegacyAppName + ".lnk"),
            Path.Combine(legacyStartMenuDir, "Desinstalar " + LegacyAppName + ".lnk"),
        };

        foreach (string path in paths)
        {
            if (File.Exists(path))
            {
                File.Delete(path);
                log.Write("Atalho removido: " + path);
            }
        }

        if (Directory.Exists(startMenuDir) && Directory.GetFileSystemEntries(startMenuDir).Length == 0)
        {
            Directory.Delete(startMenuDir);
            log.Write("Pasta vazia do Menu Iniciar removida: " + startMenuDir);
        }
        if (Directory.Exists(legacyStartMenuDir) && Directory.GetFileSystemEntries(legacyStartMenuDir).Length == 0)
        {
            Directory.Delete(legacyStartMenuDir);
            log.Write("Pasta antiga vazia do Menu Iniciar removida: " + legacyStartMenuDir);
        }
    }

    private static InstallManifest ReadManifest(string appDir)
    {
        string path = Path.Combine(appDir, "instalacao", "instalacao.json");
        if (!File.Exists(path))
        {
            return null;
        }

        try
        {
            string json = File.ReadAllText(path, Encoding.UTF8);
            return new InstallManifest
            {
                app_name = JsonValue(json, "app_name"),
                app_id = JsonValue(json, "app_id"),
                version = JsonValue(json, "version"),
                installed_at = JsonValue(json, "installed_at"),
                install_location = JsonValue(json, "install_location"),
                desktop_shortcut = JsonValue(json, "desktop_shortcut"),
                start_menu_shortcut = JsonValue(json, "start_menu_shortcut"),
                start_menu_uninstall_shortcut = JsonValue(json, "start_menu_uninstall_shortcut"),
                setup_exe = JsonValue(json, "setup_exe"),
                python_path = JsonValue(json, "python_path"),
                ffmpeg_path = JsonValue(json, "ffmpeg_path"),
            };
        }
        catch
        {
            return null;
        }
    }

    private static void CopySelfToInstallFolder(string installDir, InstallerLog log)
    {
        string currentExe = Process.GetCurrentProcess().MainModule.FileName;
        string destination = Path.Combine(installDir, SetupFileName);
        string legacyDestination = Path.Combine(installDir, LegacySetupFileName);
        Directory.CreateDirectory(installDir);

        if (!PathsEqual(currentExe, destination))
        {
            File.Copy(currentExe, destination, true);
            log.Write("Desinstalador copiado para: " + destination);
        }
        if (File.Exists(legacyDestination) && !PathsEqual(legacyDestination, destination))
        {
            File.Delete(legacyDestination);
            log.Write("Desinstalador antigo removido: " + legacyDestination);
        }
    }

    private static string GetInstalledAppDir()
    {
        string currentDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (string.Equals(Path.GetFileName(currentDir), "instalacao", StringComparison.OrdinalIgnoreCase))
        {
            DirectoryInfo parent = Directory.GetParent(currentDir);
            if (parent != null)
            {
                return parent.FullName;
            }
        }

        if (File.Exists(Path.Combine(currentDir, "silence_cutter.py")))
        {
            return currentDir;
        }

        using (RegistryKey key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppId))
        {
            string installLocation = key == null ? null : key.GetValue("InstallLocation") as string;
            if (!string.IsNullOrWhiteSpace(installLocation))
            {
                return installLocation;
            }
        }

        return GetDefaultInstallDir();
    }

    private static bool AskDeleteAll()
    {
        Console.WriteLine();
        Console.WriteLine("Como deseja desinstalar?");
        Console.WriteLine("1 - Manter arquivos da pasta Encut");
        Console.WriteLine("2 - Apagar tudo, incluindo relatorios, backups, presets, runtime e fontes");
        Console.Write("Escolha 1 ou 2: ");

        while (true)
        {
            ConsoleKeyInfo key = Console.ReadKey(true);
            if (key.KeyChar == '1')
            {
                Console.WriteLine("1");
                return false;
            }
            if (key.KeyChar == '2')
            {
                Console.WriteLine("2");
                Console.Write("Digite APAGAR para confirmar: ");
                string confirmation = Console.ReadLine();
                return string.Equals(confirmation, "APAGAR", StringComparison.OrdinalIgnoreCase);
            }
        }
    }

    private static void ScheduleDirectoryDeletion(string appDir)
    {
        string batchPath = Path.Combine(Path.GetTempPath(), "cortador_silencio_remover_" + Guid.NewGuid().ToString("N") + ".cmd");
        string content =
            "@echo off\r\n" +
            "timeout /t 2 /nobreak >nul\r\n" +
            "rmdir /s /q \"" + appDir + "\"\r\n" +
            "del \"" + batchPath + "\" >nul 2>nul\r\n";
        File.WriteAllText(batchPath, content, Encoding.Default);

        ProcessStartInfo startInfo = new ProcessStartInfo
        {
            FileName = "cmd.exe",
            Arguments = "/c \"" + batchPath + "\"",
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        Process.Start(startInfo);
    }

    private static void EnsureSafeDeleteTarget(string appDir)
    {
        string full = Path.GetFullPath(appDir).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string root = Path.GetPathRoot(full) ?? "";
        if (string.Equals(full, root.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Alvo de remocao invalido: raiz do disco.");
        }

        bool hasAppMarker =
            File.Exists(Path.Combine(full, "silence_cutter.py")) ||
            File.Exists(Path.Combine(full, "instalacao", "instalacao.json"));
        if (!hasAppMarker)
        {
            throw new InvalidOperationException("A pasta nao parece ser uma instalacao do Encut: " + full);
        }
    }

    private static string GetDefaultInstallDir()
    {
        string currentDir = AppDomain.CurrentDomain.BaseDirectory;
        if (File.Exists(Path.Combine(currentDir, "silence_cutter.py")) || string.Equals(Path.GetFileName(currentDir.TrimEnd(Path.DirectorySeparatorChar)), "Encut", StringComparison.OrdinalIgnoreCase))
        {
            return currentDir;
        }

        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        return Path.Combine(desktop, "Encut");
    }

    private static string ReadVersion(string appDir)
    {
        string path = Path.Combine(appDir, "VERSION");
        if (File.Exists(path))
        {
            string version = File.ReadAllText(path).Trim();
            if (!string.IsNullOrWhiteSpace(version))
            {
                return version;
            }
        }
        return "0.0.0";
    }

    private static string ReadSetupVersion(string appDir)
    {
        string version = ReadVersion(appDir);
        if (!string.Equals(version, "0.0.0", StringComparison.OrdinalIgnoreCase))
        {
            return version;
        }
        return ReadEmbeddedVersion();
    }

    private static string ReadEmbeddedVersion()
    {
        try
        {
            using (Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("app.VERSION"))
            {
                if (stream == null)
                {
                    return "0.0.0";
                }

                using (StreamReader reader = new StreamReader(stream, Encoding.UTF8))
                {
                    string version = reader.ReadToEnd().Trim();
                    return string.IsNullOrWhiteSpace(version) ? "0.0.0" : version;
                }
            }
        }
        catch
        {
            return "0.0.0";
        }
    }
    private static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (string dir in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(dir.Replace(source, destination));
        }
        foreach (string file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
        {
            string target = file.Replace(source, destination);
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            File.Copy(file, target, true);
        }
    }

    private static bool HasArg(string[] args, string name)
    {
        foreach (string arg in args)
        {
            if (string.Equals(arg, name, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private static string GetValueArg(string[] args, string name)
    {
        string prefix = name + "=";
        foreach (string arg in args)
        {
            if (arg.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                return arg.Substring(prefix.Length).Trim('"');
            }
        }
        return null;
    }

    private static bool PathsEqual(string a, string b)
    {
        return string.Equals(
            Path.GetFullPath(a).TrimEnd(Path.DirectorySeparatorChar),
            Path.GetFullPath(b).TrimEnd(Path.DirectorySeparatorChar),
            StringComparison.OrdinalIgnoreCase);
    }

    private static string ManifestToJson(InstallManifest manifest)
    {
        StringBuilder builder = new StringBuilder();
        builder.AppendLine("{");
        AppendJson(builder, "app_name", manifest.app_name, true);
        AppendJson(builder, "app_id", manifest.app_id, true);
        AppendJson(builder, "version", manifest.version, true);
        AppendJson(builder, "installed_at", manifest.installed_at, true);
        AppendJson(builder, "install_location", manifest.install_location, true);
        AppendJson(builder, "desktop_shortcut", manifest.desktop_shortcut, true);
        AppendJson(builder, "start_menu_shortcut", manifest.start_menu_shortcut, true);
        AppendJson(builder, "start_menu_uninstall_shortcut", manifest.start_menu_uninstall_shortcut, true);
        AppendJson(builder, "setup_exe", manifest.setup_exe, true);
        AppendJson(builder, "python_path", manifest.python_path, true);
        AppendJson(builder, "ffmpeg_path", manifest.ffmpeg_path, false);
        builder.AppendLine("}");
        return builder.ToString();
    }

    private static void AppendJson(StringBuilder builder, string name, string value, bool comma)
    {
        builder.Append("  \"").Append(JsonEscape(name)).Append("\": \"").Append(JsonEscape(value)).Append("\"");
        if (comma)
        {
            builder.Append(",");
        }
        builder.AppendLine();
    }

    private static string JsonValue(string json, string name)
    {
        Match match = Regex.Match(json, "\"" + Regex.Escape(name) + "\"\\s*:\\s*\"(?<value>(?:\\\\.|[^\"])*)\"");
        return match.Success ? JsonUnescape(match.Groups["value"].Value) : "";
    }

    private static string JsonEscape(string value)
    {
        return (value ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n");
    }

    private static string JsonUnescape(string value)
    {
        return Regex.Unescape(value ?? "");
    }

    private static void PrintHelp()
    {
        Console.WriteLine(AppName + " Setup v" + ReadEmbeddedVersion());
        Console.WriteLine();
        Console.WriteLine("Instalar:");
        Console.WriteLine("  EncutSetup.exe");
        Console.WriteLine("  EncutSetup.exe /dir=\"C:\\Users\\Sombra\\Desktop\\Encut\"");
        Console.WriteLine();
        Console.WriteLine("Desinstalar:");
        Console.WriteLine("  EncutSetup.exe /uninstall");
        Console.WriteLine("  EncutSetup.exe /uninstall /keep");
        Console.WriteLine("  EncutSetup.exe /uninstall /delete-all");
        Console.WriteLine();
        Console.WriteLine("Atualizacoes:");
        Console.WriteLine("  Repositorio GitHub padrao: " + DefaultGitHubRepo);
        Console.WriteLine("  Endpoint de release: " + DefaultUpdateEndpointUrl);
        Console.WriteLine("  EncutSetup.exe /skip-update");
    }
    private static void PauseIfInteractive(string[] args)
    {
        if (HasArg(args, "/silent") || HasArg(args, "--silent"))
        {
            return;
        }

        if (Environment.UserInteractive)
        {
            Console.WriteLine();
            Console.WriteLine("Pressione qualquer tecla para fechar...");
            Console.ReadKey(true);
        }
    }

    private sealed class UpdateInfo
    {
        public string Version;
        public string ZipUrl;
        public string SetupUrl;
        public string Sha256;
        public string Notes;
    }
    private sealed class ShortcutPair
    {
        public readonly string StartShortcut;
        public readonly string UninstallShortcut;

        public ShortcutPair(string startShortcut, string uninstallShortcut)
        {
            StartShortcut = startShortcut;
            UninstallShortcut = uninstallShortcut;
        }
    }

    private sealed class InstallerLog : IDisposable
    {
        private readonly StreamWriter _writer;

        public InstallerLog(string path)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            _writer = new StreamWriter(path, true, Encoding.UTF8);
            _writer.AutoFlush = true;
        }

        public void Write(string message)
        {
            string line = "[" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "] " + message;
            Console.WriteLine(line);
            _writer.WriteLine(line);
        }

        public void Dispose()
        {
            _writer.Dispose();
        }
    }

    private sealed class InstallManifest
    {
        public string app_name;
        public string app_id;
        public string version;
        public string installed_at;
        public string install_location;
        public string desktop_shortcut;
        public string start_menu_shortcut;
        public string start_menu_uninstall_shortcut;
        public string setup_exe;
        public string python_path;
        public string ffmpeg_path;
    }
}
