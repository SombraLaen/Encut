// C# Wrapper for Encut DLL
// Install-Package pythonnet
using Python.Runtime;

public class Encut
{
    static Encut()
    {
        Runtime.PythonDLL = @"runtime\python\python311.dll";
        PythonEngine.Initialize();
    }

    public static string GetVersion()
    {
        using (Py.GIL())
        {
            dynamic api = Py.Import("encut_api");
            return api.get_version();
        }
    }

    public static string ProbeVideo(string path)
    {
        using (Py.GIL())
        {
            dynamic api = Py.Import("encut_api");
            dynamic result = api.probe_video(path);
            return $"Duration: {result["duration"]}s, Streams: {result["audio_streams"]}";
        }
    }

    public static void ProcessVideo(string input, string output, float threshold = -35.0f)
    {
        using (Py.GIL())
        {
            dynamic api = Py.Import("encut_api");
            api.process_video(input, output, threshold);
        }
    }
}
