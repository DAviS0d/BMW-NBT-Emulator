// Windows counterpart to PlayPort's macOS helper. Stdout is binary in --address mode.
// Uses the installed Windows Bluetooth radio; no dongle or third-party driver required.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

internal static class BluetoothBridge {
    const string Bth = "bthprops.cpl";
    static readonly IntPtr InvalidSocket = new IntPtr(-1);
    [StructLayout(LayoutKind.Sequential)] struct RadioParams { public uint Size; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct RadioInfo {
        public uint Size; public ulong Address;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 248)] public string Name;
        public uint Class; public ushort Subversion, Manufacturer;
    }
    [StructLayout(LayoutKind.Sequential)] struct Search {
        public uint Size; public int Authenticated, Remembered, Unknown, Connected, Inquiry;
        public byte Timeout; public IntPtr Radio;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct Device {
        public uint Size; public ulong Address; public uint Class;
        public int Connected, Remembered, Authenticated;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 16)] public ushort[] Times;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 248)] public string Name;
    }
    // SOCKADDR_BTH is packed to one byte in ws2bth.h (30 bytes, not 40).
    [StructLayout(LayoutKind.Sequential, Pack = 1)] struct BthAddress {
        public ushort Family; public ulong Address; public Guid Service; public uint Port;
    }
    [DllImport(Bth, SetLastError = true)] static extern IntPtr BluetoothFindFirstRadio(ref RadioParams p, out IntPtr radio);
    [DllImport(Bth)] static extern bool BluetoothFindRadioClose(IntPtr find);
    [DllImport(Bth)] static extern uint BluetoothGetRadioInfo(IntPtr radio, ref RadioInfo info);
    [DllImport(Bth, SetLastError = true)] static extern IntPtr BluetoothFindFirstDevice(ref Search p, ref Device d);
    [DllImport(Bth, SetLastError = true)] static extern bool BluetoothFindNextDevice(IntPtr find, ref Device d);
    [DllImport(Bth)] static extern bool BluetoothFindDeviceClose(IntPtr find);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("ws2_32.dll")] static extern int WSAStartup(ushort version, IntPtr data);
    [DllImport("ws2_32.dll")] static extern int WSACleanup();
    [DllImport("ws2_32.dll")] static extern int WSAGetLastError();
    [DllImport("ws2_32.dll")] static extern IntPtr socket(int family, int type, int protocol);
    [DllImport("ws2_32.dll")] static extern int connect(IntPtr s, ref BthAddress address, int length);
    [DllImport("ws2_32.dll")] static extern int send(IntPtr s, byte[] data, int length, int flags);
    [DllImport("ws2_32.dll")] static extern int recv(IntPtr s, byte[] data, int length, int flags);
    [DllImport("ws2_32.dll")] static extern int shutdown(IntPtr s, int how);
    [DllImport("ws2_32.dll")] static extern int closesocket(IntPtr s);
    static string Mac(ulong address) {
        string h = address.ToString("X12");
        return String.Join(":", new string[] { h.Substring(0,2), h.Substring(2,2), h.Substring(4,2), h.Substring(6,2), h.Substring(8,2), h.Substring(10,2) });
    }
    static void ListDevices(bool scan) {
        Search p = new Search { Size = (uint)Marshal.SizeOf(typeof(Search)), Authenticated = 1, Remembered = 1, Connected = 1, Unknown = scan ? 1 : 0, Inquiry = scan ? 1 : 0, Timeout = 8 };
        Device d = new Device { Size = (uint)Marshal.SizeOf(typeof(Device)) };
        IntPtr find = BluetoothFindFirstDevice(ref p, ref d);
        if (find == IntPtr.Zero) {
            int error = Marshal.GetLastWin32Error();
            if (error != 259) throw new IOException("Bluetooth enumeration failed: " + error);
            return;
        }
        try {
            do {
                if (scan || d.Authenticated != 0) Console.WriteLine(Mac(d.Address) + " " + d.Name);
                d.Size = (uint)Marshal.SizeOf(typeof(Device));
            } while (BluetoothFindNextDevice(find, ref d));
        } finally { BluetoothFindDeviceClose(find); }
    }
    static void PrintAddress() {
        RadioParams p = new RadioParams { Size = (uint)Marshal.SizeOf(typeof(RadioParams)) };
        IntPtr radio;
        IntPtr find = BluetoothFindFirstRadio(ref p, out radio);
        if (find == IntPtr.Zero) throw new IOException("No enabled Windows Bluetooth radio found (error " + Marshal.GetLastWin32Error() + ").");
        try {
            RadioInfo info = new RadioInfo { Size = (uint)Marshal.SizeOf(typeof(RadioInfo)) };
            uint error = BluetoothGetRadioInfo(radio, ref info);
            if (error != 0) throw new IOException("BluetoothGetRadioInfo: " + error);
            Console.WriteLine(Mac(info.Address));
        } finally { CloseHandle(radio); BluetoothFindRadioClose(find); }
    }
    static void Pump(string address) {
        ulong mac = Convert.ToUInt64(address.Replace(":", "").Replace("-", ""), 16);
        IntPtr data = Marshal.AllocHGlobal(512);
        try {
            int error = WSAStartup(0x0202, data);
            if (error != 0) throw new IOException("WSAStartup: " + error);
        } finally { Marshal.FreeHGlobal(data); }
        IntPtr s = InvalidSocket;
        try {
            s = socket(32, 1, 3); // AF_BTH, SOCK_STREAM, BTHPROTO_RFCOMM
            if (s == InvalidSocket) throw new IOException("Bluetooth socket: " + WSAGetLastError());
            BthAddress remote = new BthAddress { Family = 32, Address = mac, Service = new Guid("00000000-deca-fade-deca-deafdecacafe"), Port = 0 };
            // Windows resolves the RFCOMM port from the iAP2 service UUID through SDP.
            var deadline = new Timer(delegate { Console.Error.WriteLine("bt-bridge: connection timed out"); Environment.Exit(2); }, null, 20000, Timeout.Infinite);
            int result = connect(s, ref remote, Marshal.SizeOf(typeof(BthAddress)));
            int connectError = result == 0 ? 0 : WSAGetLastError();
            deadline.Dispose();
            if (result != 0) throw new IOException("iAP2 RFCOMM connect failed: " + connectError + ". Pair the iPhone in Windows Bluetooth settings and keep it in range.");
            Console.Error.WriteLine("bt-bridge: RFCOMM connected");
            IntPtr connected = s;
            Thread input = new Thread(delegate() {
                try {
                    Stream stdin = Console.OpenStandardInput(); byte[] buffer = new byte[8192];
                    int count;
                    while ((count = stdin.Read(buffer, 0, buffer.Length)) > 0) {
                        int offset = 0;
                        while (offset < count) {
                            byte[] chunk = new byte[count - offset]; Array.Copy(buffer, offset, chunk, 0, chunk.Length);
                            int sent = send(connected, chunk, chunk.Length, 0);
                            if (sent <= 0) throw new IOException("RFCOMM send: " + WSAGetLastError());
                            offset += sent;
                        }
                    }
                } catch (Exception e) { Console.Error.WriteLine("bt-bridge: " + e.Message); }
                finally { shutdown(connected, 2); }
            });
            input.IsBackground = true; input.Start();
            Stream stdout = Console.OpenStandardOutput(); byte[] incoming = new byte[8192];
            while (true) {
                int count = recv(s, incoming, incoming.Length, 0);
                if (count == 0) break;
                if (count < 0) throw new IOException("RFCOMM recv: " + WSAGetLastError());
                stdout.Write(incoming, 0, count); stdout.Flush();
            }
        } finally { if (s != InvalidSocket) closesocket(s); WSACleanup(); }
    }
    static int Main(string[] args) {
        try {
            if (args.Length == 1 && args[0] == "--self-test") {
                if (Marshal.SizeOf(typeof(BthAddress)) != 30 || Marshal.SizeOf(typeof(Device)) != 560 ||
                    Marshal.SizeOf(typeof(RadioInfo)) != 520 || Marshal.SizeOf(typeof(Search)) != 40 ||
                    Marshal.OffsetOf(typeof(Search), "Radio").ToInt32() != 32 ||
                    Marshal.OffsetOf(typeof(Device), "Name").ToInt32() != 64) throw new Exception("Windows Bluetooth ABI layout mismatch");
                Console.WriteLine("Bluetooth bridge x64 ABI checks passed");
            }
            else if (args.Length == 1 && args[0] == "--print-address") PrintAddress();
            else if (args.Length == 1 && (args[0] == "--list" || args[0] == "--scan")) ListDevices(args[0] == "--scan");
            else if (args.Length == 2 && args[0] == "--address") Pump(args[1]);
            else { Console.Error.WriteLine("Usage: bt-bridge --print-address | --list | --scan | --address AA:BB:CC:DD:EE:FF"); return 2; }
            return 0;
        } catch (Exception e) { Console.Error.WriteLine("bt-bridge: " + e.Message); return 1; }
    }
}
