using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading;

namespace VRisingRLBridge
{
    /// <summary>
    /// Serveur TCP local, protocole "une ligne JSON par message".
    /// Le client Python envoie {"cmd": "..."} et reçoit une réponse JSON.
    ///
    /// IMPORTANT : la lecture/écriture de l'état ECS doit se faire sur le thread
    /// principal du jeu. On NE touche donc PAS au monde ECS depuis le thread
    /// réseau : on dépose une requête dans une file, le plugin la traite dans son
    /// OnUpdate (thread jeu) et publie la réponse. Voir Plugin.cs.
    /// </summary>
    public class BridgeServer
    {
        public class Pending
        {
            public string Cmd = "ping";
            public int Action = -1;
            public readonly ManualResetEventSlim Done = new(false);
            public string ResponseJson = "{}";
        }

        private readonly int _port;
        private readonly Action<string> _log;
        private TcpListener _listener;
        private Thread _thread;
        private volatile bool _running;

        // File des requêtes à traiter sur le thread principal du jeu.
        public readonly ConcurrentQueue<Pending> Inbox = new();

        public BridgeServer(int port, Action<string> log)
        {
            _port = port;
            _log = log;
        }

        public void Start()
        {
            _running = true;
            _thread = new Thread(Loop) { IsBackground = true, Name = "VRisingRLBridge" };
            _thread.Start();
            _log($"[bridge] en écoute sur 127.0.0.1:{_port}");
        }

        public void Stop()
        {
            _running = false;
            try { _listener?.Stop(); } catch { /* ignore */ }
        }

        private void Loop()
        {
            try
            {
                _listener = new TcpListener(IPAddress.Loopback, _port);
                _listener.Start();
                while (_running)
                {
                    using TcpClient client = _listener.AcceptTcpClient();
                    using NetworkStream stream = client.GetStream();
                    HandleClient(stream);
                }
            }
            catch (Exception ex)
            {
                if (_running) _log($"[bridge] erreur serveur : {ex.Message}");
            }
        }

        private void HandleClient(NetworkStream stream)
        {
            var sb = new StringBuilder();
            var buffer = new byte[4096];
            while (_running)
            {
                int read;
                try { read = stream.Read(buffer, 0, buffer.Length); }
                catch { break; }
                if (read <= 0) break;

                sb.Append(Encoding.UTF8.GetString(buffer, 0, read));
                int nl;
                while ((nl = IndexOfNewline(sb)) >= 0)
                {
                    string line = sb.ToString(0, nl);
                    sb.Remove(0, nl + 1);
                    string response = Dispatch(line);
                    byte[] outBytes = Encoding.UTF8.GetBytes(response + "\n");
                    try { stream.Write(outBytes, 0, outBytes.Length); }
                    catch { return; }
                }
            }
        }

        private static int IndexOfNewline(StringBuilder sb)
        {
            for (int i = 0; i < sb.Length; i++)
                if (sb[i] == '\n') return i;
            return -1;
        }

        /// <summary>Parse la commande et attend que le thread jeu la traite.</summary>
        private string Dispatch(string line)
        {
            try
            {
                using JsonDocument doc = JsonDocument.Parse(line);
                JsonElement root = doc.RootElement;
                string cmd = root.TryGetProperty("cmd", out var c) ? c.GetString() : "ping";

                if (cmd == "ping")
                    return "{\"ok\":true}";

                var pending = new Pending { Cmd = cmd };
                if (root.TryGetProperty("action", out var a) && a.TryGetInt32(out int act))
                    pending.Action = act;

                Inbox.Enqueue(pending);
                // Attend la réponse produite sur le thread principal (timeout de sécurité).
                if (!pending.Done.Wait(5000))
                    return "{\"error\":\"timeout cote jeu\"}";
                return pending.ResponseJson;
            }
            catch (Exception ex)
            {
                return "{\"error\":\"" + ex.Message.Replace("\"", "'") + "\"}";
            }
        }
    }
}
