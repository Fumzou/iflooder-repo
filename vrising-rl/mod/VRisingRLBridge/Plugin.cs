using System.Globalization;
using System.Text;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;

namespace VRisingRLBridge
{
    /// <summary>
    /// Mod BepInEx (IL2CPP) qui expose l'état du jeu à un agent RL Python via TCP.
    ///
    /// CE QU'IL RESTE À CÂBLER (marqué TODO) : la lecture de l'état du joueur et
    /// l'envoi des actions, qui dépendent de l'API ECS de V Rising. Tout le reste
    /// (réseau, protocole, boucle thread-safe) est prêt.
    /// </summary>
    [BepInPlugin(GUID, NAME, VERSION)]
    public class Plugin : BasePlugin
    {
        public const string GUID = "com.vrisingrl.bridge";
        public const string NAME = "VRisingRLBridge";
        public const string VERSION = "0.1.0";

        private const int Port = 9000;
        private const int ObservationSize = 16; // doit matcher config.yaml -> env.observation_size

        internal static ManualLogSource Log;
        private BridgeServer _server;

        public override void Load()
        {
            Log = base.Log;
            _server = new BridgeServer(Port, msg => Log.LogInfo(msg));
            _server.Start();

            // Traite la file des requêtes réseau sur le thread du jeu.
            // Selon ton framework de mod (Bloodstone / Wetstone), branche Pump()
            // sur un hook d'Update. Exemple générique ci-dessous via un IL2CPP
            // MonoBehaviour à enregistrer, ou un hook de système ECS.
            // TODO: enregistrer Pump() dans la boucle de jeu (OnUpdate).
            Log.LogInfo($"{NAME} {VERSION} chargé. Bridge sur le port {Port}.");
        }

        public override bool Unload()
        {
            _server?.Stop();
            return true;
        }

        /// <summary>À appeler chaque frame sur le thread principal du jeu.</summary>
        public void Pump()
        {
            while (_server.Inbox.TryDequeue(out BridgeServer.Pending req))
            {
                switch (req.Cmd)
                {
                    case "reset":
                        ResetEpisode();
                        req.ResponseJson = BuildResponse(terminated: false, truncated: false);
                        break;
                    case "step":
                        ApplyAction(req.Action);
                        req.ResponseJson = BuildResponse(terminated: false, truncated: false);
                        break;
                    case "close":
                        req.ResponseJson = "{\"ok\":true}";
                        break;
                    default:
                        req.ResponseJson = "{\"error\":\"commande inconnue\"}";
                        break;
                }
                req.Done.Set();
            }
        }

        // ------------------------------------------------------------------
        //  À IMPLÉMENTER avec l'API ECS de V Rising
        // ------------------------------------------------------------------

        /// <summary>Construit le vecteur d'observation depuis l'état du joueur.</summary>
        private float[] GetObservation()
        {
            var obs = new float[ObservationSize];
            // TODO: récupérer l'entité joueur et lire ses composants, ex :
            //   var hp = playerEntity.Read<Health>();
            //   obs[0] = hp.Value / hp.MaxHealth;
            //   obs[1] = hp.MaxHealth / 1000f;
            //   ... position, niveau d'équipement, ennemis proches, sang, etc.
            return obs;
        }

        /// <summary>Construit le dictionnaire info (stats utilisées pour la récompense).</summary>
        private string BuildInfoJson()
        {
            // TODO: remplir avec les vraies valeurs lues sur le joueur.
            // Ces clés sont consommées par vrising_env.py -> _compute_reward.
            return "{" +
                   "\"player_hp\":0.0," +
                   "\"gear_level\":0.0," +
                   "\"total_damage_dealt\":0.0," +
                   "\"enemies_killed\":0.0," +
                   "\"bosses_killed\":0.0," +
                   "\"player_dead\":false" +
                   "}";
        }

        /// <summary>Applique une action discrète (déplacement, attaque, sort…).</summary>
        private void ApplyAction(int action)
        {
            // TODO: traduire l'index d'action (voir env.actions dans config.yaml)
            // en input/commande de jeu. Ex : déplacer le joueur, déclencher
            // l'attaque primaire, lancer une capacité, esquiver, interagir.
        }

        /// <summary>Réinitialise un épisode (respawn / téléport au point de départ…).</summary>
        private void ResetEpisode()
        {
            // TODO: remettre le joueur dans un état de départ reproductible
            // (PV pleins, position fixe, boss réinitialisé) pour un entraînement stable.
        }

        // ------------------------------------------------------------------
        private string BuildResponse(bool terminated, bool truncated)
        {
            float[] obs = GetObservation();
            var sb = new StringBuilder();
            sb.Append("{\"obs\":[");
            for (int i = 0; i < obs.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(obs[i].ToString("R", CultureInfo.InvariantCulture));
            }
            sb.Append("],\"terminated\":").Append(terminated ? "true" : "false");
            sb.Append(",\"truncated\":").Append(truncated ? "true" : "false");
            sb.Append(",\"info\":").Append(BuildInfoJson());
            sb.Append('}');
            return sb.ToString();
        }
    }
}
