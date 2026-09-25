// Small Windows GUI entry point. Runtime and application code remain updateable.
using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using System.Web.Script.Serialization;
using System.Collections.Generic;

[assembly: AssemblyTitle("Bilingual Sora 2nd")]
[assembly: AssemblyVersion("1.0.0.0")]
static class Launcher {
    static string Quote(string value) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            result.Append('\\', slashes * (c == '"' ? 2 : 1) + (c == '"' ? 1 : 0));
            result.Append(c); slashes = 0;
        }
        return result.Append('\\', slashes * 2).Append('"').ToString();
    }
    [STAThread]
    static int Main(string[] args) {
        string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        try {
            string id = File.ReadAllText(Path.Combine(root, "runtime", "current.txt")).Trim();
            // Recover with the PREVIOUS runtime: rollback must never delete loaded DLLs.
            string journal = Path.Combine(root, "generated", "updates", "transaction.json");
            if (File.Exists(journal)) {
                var serializer = new JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024 };
                var state = serializer.Deserialize<Dictionary<string, object>>(File.ReadAllText(journal));
                object recovery;
                if (state.TryGetValue("recovery_runtime", out recovery) && recovery is string) id = (string)recovery;
            }
            if (!Regex.IsMatch(id, "\\A[0-9a-f]{16}\\z")) throw new IOException("Invalid runtime selector");
            string python = Path.Combine(root, "runtime", id, "pythonw.exe");
            string entry = Path.Combine(root, "launch.py");
            if (!File.Exists(python) || !File.Exists(entry)) throw new FileNotFoundException("Incomplete package");
            Directory.CreateDirectory(Path.Combine(root, "generated"));
            var command = new StringBuilder("-B -X utf8 " + Quote(entry));
            foreach (string arg in args) command.Append(" ").Append(Quote(arg));
            Process.Start(new ProcessStartInfo(python, command.ToString()) {
                WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true
            });
            return 0;
        } catch (Exception error) {
            string lang = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName;
            string message = lang == "zh" ? "无法启动。请先将整个 ZIP 解压到可写文件夹，再运行 BilingualSora2nd.exe。" :
                lang == "ja" ? "起動できません。ZIP 全体を書き込み可能なフォルダーに展開してから BilingualSora2nd.exe を実行してください。" :
                "Cannot start. Extract the entire ZIP into a writable folder, then run BilingualSora2nd.exe.";
            MessageBox.Show(message + "\n\n" + error.Message, "Bilingual Sora 2nd", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
