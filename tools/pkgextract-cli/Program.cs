// pkgextract-cli: extract the files of a fake-signed PS4 PKG into a folder.
// MIT, part of ghostldr (see LICENSE). Uses LibOrbisPkg (LGPL-3.0, by maxton).

using System.Reflection;
using System.Runtime.InteropServices;
using LibOrbisPkg.PFS;
using LibOrbisPkg.PKG;
using LibOrbisPkg.Util;

namespace PkgExtractCli;

internal sealed class UserError : Exception
{
    public UserError(string message) : base(message) { }
}

internal static class Program
{
    private const string Name = "pkgextract-cli";
    private const string ZeroPasscode = "00000000000000000000000000000000";
    private const int MaxFiles = 1_000_000;

    private const string Usage =
        "usage: " + Name + " <game.pkg> <output folder> [path inside the package]\n";

    private const string Help =
        Name + ": extract a fake-signed PS4 PKG (fPKG) into a folder.\n" +
        "\n" +
        Usage +
        "\n" +
        "  game.pkg      a PS4 game, update or DLC PKG made with the all-zero passcode\n" +
        "                or fake-signed by a PKG tool (fPKG)\n" +
        "  output folder created if missing; it must be empty if it already exists\n" +
        "  path          extract only this file or folder, e.g. sce_sys or eboot.bin\n" +
        "\n" +
        "The output folder gets the game's files (eboot.bin, sce_module/, ...) and,\n" +
        "in sce_sys/, the package's own entries (param.sfo, icon0.png, ...).\n" +
        "Retail (store or disc) PKGs cannot be opened: they need the console's keys.\n" +
        "\n" +
        "  -h, --help     show this help\n" +
        "  --version      show the version\n" +
        "  --licenses     show the licences of " + Name + " and what it is built from\n" +
        "\n" +
        "Exit status: 0 done, 1 bad arguments, 2 the extraction failed.\n";

    private static int Main(string[] args)
    {
        var positional = new List<string>();
        var onlyPositional = false;
        foreach (var arg in args)
        {
            if (!onlyPositional && arg == "--")
                onlyPositional = true;
            else if (!onlyPositional && arg is "-h" or "--help" or "-?" or "/?")
            {
                Console.Write(Help);
                return 0;
            }
            else if (!onlyPositional && arg == "--version")
            {
                Console.WriteLine($"{Name} {Version()}");
                return 0;
            }
            else if (!onlyPositional && arg == "--licenses")
            {
                Console.Write(Licences());
                return 0;
            }
            else if (!onlyPositional && arg.StartsWith('-') && arg.Length > 1)
            {
                Console.Error.Write($"{Name}: unknown option {arg}\n{Usage}Try '{Name} --help'.\n");
                return 1;
            }
            else
                positional.Add(arg);
        }
        if (positional.Count is < 2 or > 3)
        {
            Console.Error.Write($"{Usage}Try '{Name} --help'.\n");
            return 1;
        }

        try
        {
            Extract(positional[0], positional[1], positional.Count == 3 ? positional[2] : "");
            return 0;
        }
        catch (UserError error)
        {
            Console.Error.WriteLine($"{Name}: {error.Message}");
        }
        catch (IOException error) when (IsDiskFull(error))
        {
            Console.Error.WriteLine($"{Name}: the disk is full; free some space or extract to another drive.");
        }
        catch (UnauthorizedAccessException error)
        {
            Console.Error.WriteLine($"{Name}: permission denied: {error.Message}");
        }
        catch (IOException error)
        {
            Console.Error.WriteLine($"{Name}: {error.Message}");
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"{Name}: the PKG could not be read; it may be damaged or incomplete ({error.Message}).");
        }
        return 2;
    }

    private static string Version()
    {
        var v = typeof(Program).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "";
        var plus = v.IndexOf('+');
        return plus >= 0 ? v[..plus] : v;
    }

    // The licence texts are built in (pkgextract-cli.csproj), so the one file carries them.
    private static string Licences()
    {
        string Text(string name)
        {
            using var s = typeof(Program).Assembly.GetManifestResourceStream(name)
                ?? throw new InvalidOperationException($"no {name} built in");
            return new System.IO.StreamReader(s).ReadToEnd().TrimEnd() + "\n";
        }
        var commit = Text("LibOrbisPkg-commit").Trim();
        const string Rule = "\n========================================================================\n\n";
        return $"{Name} {Version()} is part of ghostldr (MIT, below): https://github.com/asylumexp/ghostldr\n" +
               "It is built from:\n" +
               "- LibOrbisPkg by maxton (LGPL-3.0, below; the LGPL is the GPL-3.0, also below, plus extra\n" +
               "  permissions): https://github.com/maxton/LibOrbisPkg\n" +
               $"  at {commit}, with ghostldr's\n" +
               "  tools/pkgextract-cli/LibOrbisPkg.patch. ghostldr's tools/pkgextract-cli/build.py rebuilds\n" +
               "  this program from that source, with your own LibOrbisPkg if you like.\n" +
               "- the .NET runtime (MIT, below, with its third-party notices).\n" +
               Rule + "ghostldr\n\n" + Text("LICENSE.txt") +
               Rule + "LibOrbisPkg: GNU Lesser General Public License 3.0\n\n" + Text("LibOrbisPkg-LICENSE.txt") +
               Rule + Text("GPL-3.0.txt") +
               Rule + ".NET\n\n" + Text("dotnet-LICENSE.txt") +
               Rule + Text("dotnet-THIRD-PARTY-NOTICES.txt");
    }

    private static void Extract(string packageArg, string outArg, string pathArg)
    {
        // .NET's cryptography on Linux is OpenSSL's; without it the runtime aborts.
        if (OperatingSystem.IsLinux() && !new[] { "libssl.so.3", "libssl.so.1.1", "libssl.so.1.0.2",
                "libssl.so.1.0.0", "libssl.so.10", "libssl.so" }.Any(n => NativeLibrary.TryLoad(n, out _)))
            throw new UserError("OpenSSL (libssl) is missing; install it (Debian, Ubuntu: apt install libssl3; " +
                                "Fedora: dnf install openssl-libs) and try again.");
        var packagePath = Path.GetFullPath(packageArg);
        var outRoot = Path.GetFullPath(outArg);
        var only = NormalizeWanted(pathArg);

        if (Directory.Exists(packagePath))
            throw new UserError($"{packageArg} is a folder, not a PKG file.");
        if (!File.Exists(packagePath))
            throw new UserError($"{packageArg}: no such file.");
        if (File.Exists(outRoot))
            throw new UserError($"the output folder {outArg} is a file.");
        if (Directory.Exists(outRoot) && Directory.EnumerateFileSystemEntries(outRoot).Any())
            throw new UserError($"the output folder {outArg} already exists and is not empty; " +
                                "give a new folder (it is created) or an empty one.");

        using var stream = new FileStream(packagePath, FileMode.Open, FileAccess.Read,
            FileShare.Read, 1 << 20, FileOptions.RandomAccess);
        var magic = new byte[4];
        if (stream.Length < 0x1000 || stream.Read(magic, 0, 4) != 4 ||
            !magic.AsSpan().SequenceEqual("\u007fCNT"u8))
            throw new UserError($"{packageArg} is not a PS4 PKG file.");
        stream.Position = 0;
        Pkg pkg;
        try
        {
            pkg = new PkgReader(stream).ReadPkg();
        }
        catch (Exception error)
        {
            throw new UserError($"{packageArg} could not be read as a PS4 PKG; it may be damaged or incomplete ({error.Message}).");
        }
        var contentId = pkg.Header.content_id;

        // The game's files: the inner PFS image, inside the outer (encrypted) PFS.
        // Additional-license DLC has no PFS image, only the package entries.
        var files = new List<(PfsReader.File file, string path, long size)>();
        PFSCReader? innerPfsc = null;
        if (pkg.Header.pfs_image_size != 0)
        {
            var ekpfs = pkg.CheckPasscode(ZeroPasscode)
                ? Crypto.ComputeKeys(contentId, ZeroPasscode, 1)
                : pkg.GetEkpfs();
            if (ekpfs is null || !pkg.CheckEkpfs(ekpfs))
                throw new UserError($"{packageArg} is not a fake-signed PKG. Only fake-signed PKGs (fPKGs) " +
                                    "can be extracted; a retail PKG (from the store or a disc) is encrypted " +
                                    "with keys only the console has.");
            var image = new PackageRange(stream, checked((long)pkg.Header.pfs_image_offset),
                checked((long)pkg.Header.pfs_image_size));
            var outer = new PfsReader(image, pkg.Header.pfs_flags, ekpfs);
            var inner = outer.GetFile("pfs_image.dat")
                ?? throw new UserError($"{packageArg}: the package has no game image (pfs_image.dat).");
            innerPfsc = new PFSCReader(inner.GetView());
            foreach (var file in new PfsReader(innerPfsc).GetAllFiles())
            {
                if (files.Count == MaxFiles)
                    throw new UserError($"{packageArg}: more than {MaxFiles} files; the package looks damaged.");
                var path = NormalizePath(file.FullName);
                if (Wanted(path, only))
                    // LibOrbisPkg's compressed_size is the size once decompressed.
                    files.Add((file, path, file.size == file.compressed_size ? file.size : file.compressed_size));
            }
            files.Sort((a, b) => string.CompareOrdinal(a.path, b.path));
        }
        using var innerScope = innerPfsc;

        // param.sfo, icon0.png and the rest of sce_sys live in the PKG's entry
        // table, not in the PFS; installing a PKG copies them into sce_sys.
        var inPfs = new HashSet<string>(files.Select(f => f.path), StringComparer.Ordinal);
        var entries = new List<(MetaEntry meta, string path)>();
        var notExtracted = new List<string>();
        foreach (var meta in pkg.Metas.Metas)
        {
            if (!EntryNames.IdToName.TryGetValue(meta.id, out var entryName) || entryName.StartsWith('.'))
                continue;
            var path = "sce_sys/" + NormalizePath(entryName);
            if (!Wanted(path, only) || inPfs.Contains(path))
                continue;
            if (meta.Encrypted && (meta.KeyIndex != 3 || pkg.EntryKeys is null))
                notExtracted.Add($"{path} (encrypted with a console key)");
            else
                entries.Add((meta, path));
        }

        if (only.Length != 0 && files.Count == 0 && entries.Count == 0)
            throw new UserError($"nothing in {packageArg} is at {pathArg}.");

        long total = files.Sum(f => f.size) + entries.Sum(e => (long)e.meta.DataSize);
        CheckFreeSpace(outRoot, total);
        Directory.CreateDirectory(outRoot);

        var progress = new Progress(files.Count + entries.Count, total);
        var buffer = new byte[4 << 20];
        foreach (var (file, path, size) in files)
        {
            using var raw = file.GetView();
            IMemoryReader content = raw;
            if (file.size != file.compressed_size)
                content = new PFSCReader(raw);
            try
            {
                WriteFile(outRoot, path, output =>
                {
                    for (long pos = 0; pos < size;)
                    {
                        var n = (int)Math.Min(buffer.Length, size - pos);
                        content.Read(pos, buffer, 0, n);
                        output.Write(buffer, 0, n);
                        pos += n;
                        progress.Add(n);
                    }
                });
            }
            finally
            {
                if (!ReferenceEquals(content, raw))
                    content.Dispose();
            }
            progress.FileDone();
        }
        foreach (var (meta, path) in entries)
        {
            var data = new byte[meta.DataSize];
            stream.Position = meta.DataOffset;
            stream.ReadExactly(data);
            if (meta.Encrypted)
            {
                var padded = new byte[(data.Length + 15) & ~15];
                stream.Position = meta.DataOffset;
                stream.ReadExactly(padded);
                data = Entry.Decrypt(padded, pkg, meta)[..data.Length];
            }
            WriteFile(outRoot, path, output => output.Write(data));
            progress.Add(data.Length);
            progress.FileDone();
        }
        progress.Finish();

        var count = files.Count + entries.Count;
        Console.WriteLine($"Extracted {count} file{(count == 1 ? "" : "s")} ({Size(total)}) of {contentId} to {outRoot}");
        foreach (var skipped in notExtracted)
            Console.WriteLine($"Not extracted: {skipped}");
    }

    // Write one file as <name>.part, renamed when complete, so an interrupted
    // run never leaves a short file under the real name.
    private static void WriteFile(string outRoot, string path, Action<FileStream> write)
    {
        var target = Path.GetFullPath(Path.Combine(outRoot, path.Replace('/', Path.DirectorySeparatorChar)));
        if (!target.StartsWith(outRoot.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.Ordinal))
            throw new UserError($"the package names a file outside the output folder ({path}).");
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        if (File.Exists(target) || Directory.Exists(target))
            throw new UserError($"two files in the package have the name {path} on this disk (names that differ " +
                                "only in letter case?); extract to a case-sensitive drive.");
        var temp = target + ".part";
        try
        {
            using (var output = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20))
                write(output);
            File.Move(temp, target);
        }
        catch
        {
            try { File.Delete(temp); } catch { /* keep the original error */ }
            throw;
        }
    }

    private static void CheckFreeSpace(string outRoot, long needed)
    {
        long free;
        try
        {
            var existing = outRoot;
            while (!Directory.Exists(existing))
                existing = Path.GetDirectoryName(existing) ?? throw new IOException();
            free = new DriveInfo(existing).AvailableFreeSpace;
        }
        catch
        {
            return; // unknown: find out while writing
        }
        if (free < needed)
            throw new UserError($"not enough free space: the files need {Size(needed)}, the drive has {Size(free)} free.");
    }

    private static bool IsDiskFull(IOException error)
    {
        // Unix: ENOSPC (28) or EDQUOT (69 macOS, 122 Linux); Windows: ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL.
        var code = error.HResult;
        return code is 28 or 69 or 122 || (code & 0xFFFF) is 0x27 or 0x70 && (code >>> 16) == 0x8007;
    }

    private static string NormalizePath(string fullName)
    {
        var path = fullName.Replace('\\', '/');
        path = path.StartsWith("/uroot/", StringComparison.Ordinal) ? path[7..] : path.TrimStart('/');
        var parts = path.Split('/');
        if (parts.Any(part => part.Length == 0 || part == "." || part == ".." || part.Contains('\0') || part.Contains(':')))
            throw new UserError($"the package has a file name that is not safe to write ({fullName}).");
        return string.Join('/', parts);
    }

    private static string NormalizeWanted(string path) =>
        path.Replace('\\', '/').Trim('/');

    private static bool Wanted(string path, string only) =>
        only.Length == 0 || path == only ||
        (path.Length > only.Length && path[only.Length] == '/' && path.StartsWith(only, StringComparison.Ordinal));

    private static string Size(long bytes) => bytes switch
    {
        >= 1L << 30 => $"{bytes / (double)(1L << 30):0.00} GiB",
        >= 1L << 20 => $"{bytes / (double)(1L << 20):0.0} MiB",
        >= 1L << 10 => $"{bytes / 1024.0:0.0} KiB",
        _ => $"{bytes} bytes",
    };

    private sealed class Progress
    {
        private readonly int files;
        private readonly long bytes;
        private readonly bool live = !Console.IsErrorRedirected;
        private readonly System.Diagnostics.Stopwatch clock = System.Diagnostics.Stopwatch.StartNew();
        private long lastShown = -1000;
        private int filesDone;
        private long bytesDone;

        public Progress(int files, long bytes)
        {
            this.files = files;
            this.bytes = bytes;
        }

        public void Add(long n)
        {
            bytesDone += n;
            Show(false);
        }

        public void FileDone()
        {
            filesDone++;
            Show(false);
        }

        public void Finish()
        {
            Show(true);
            if (live && lastShown >= 0)
                Console.Error.WriteLine();
        }

        private void Show(bool last)
        {
            var now = clock.ElapsedMilliseconds;
            if (!last && now - lastShown < (live ? 250 : 10_000))
                return;
            if (last && lastShown < 0 && now < 1000)
                return; // small: no progress at all
            lastShown = now;
            var line = $"{filesDone}/{files} files, {Size(bytesDone)} of {Size(bytes)}";
            if (live)
                Console.Error.Write($"\r{line}   ");
            else
                Console.Error.WriteLine(line);
        }
    }

    // The PKG's PFS image, read through the shared file stream.
    private sealed class PackageRange : IMemoryReader
    {
        private readonly FileStream stream;
        private readonly long start;
        private readonly long length;
        private readonly object sync = new();

        public PackageRange(FileStream stream, long start, long length)
        {
            if (start < 0 || length < 0 || start > stream.Length || length > stream.Length - start)
                throw new UserError("the PKG is shorter than its header says; it may be incomplete.");
            this.stream = stream;
            this.start = start;
            this.length = length;
        }

        public void Read(long pos, byte[] buffer, int offset, int count)
        {
            if (pos < 0 || count < 0 || pos > length || count > length - pos)
                throw new InvalidDataException("read outside the PFS image");
            lock (sync)
            {
                stream.Position = start + pos;
                stream.ReadExactly(buffer, offset, count);
            }
        }

        public void Dispose() { }
    }
}
