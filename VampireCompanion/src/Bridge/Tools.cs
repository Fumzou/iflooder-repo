using System.Text.Json;

namespace VampireCompanion;

public sealed partial class CompanionTools
{
    readonly string directory;
    public CompanionTools(string directory) => this.directory = Path.GetFullPath(directory);
    public Snapshot Read()
    {
        var path = Path.Combine(directory, "snapshot.json");
        if (!File.Exists(path)) throw new InvalidOperationException("Aucune donnée. Lance V Rising avec le mod et connecte-toi à une partie.");
        if (new FileInfo(path).Length > 32 * 1024 * 1024) throw new InvalidOperationException("Snapshot trop volumineux.");
        var s = JsonSerializer.Deserialize<Snapshot>(File.ReadAllText(path), Wire.Json)
            ?? throw new InvalidOperationException("Snapshot vide.");
        // Schema 1 is a 0.3 snapshot: it simply carries no character state, and the
        // character tools report that rather than inventing one.
        if (s.SchemaVersion is not (1 or 2)) throw new InvalidOperationException(
            "Version des données incompatible : le mod dans le jeu et la passerelle ne sont pas de la même version. Remplace les deux.");
        return s;
    }
    public static bool Fresh(Snapshot s, DateTimeOffset now) => s.Connected &&
        (now - s.CapturedAt).TotalSeconds is >= -5 and <= 10;
    static string Text(JsonElement a, string key, string fallback = "") =>
        a.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : fallback;
    static int Int(JsonElement a, string key, int fallback)
    {
        if (!a.TryGetProperty(key, out var v)) return fallback;
        if (v.ValueKind == JsonValueKind.Number && v.TryGetInt32(out var n)) return n;
        throw new ArgumentException(key + " doit être un entier.");
    }
    static bool Bool(JsonElement a, string key) => a.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.True;
    static bool Match(string text, string query) => System.Globalization.CultureInfo.InvariantCulture.CompareInfo.IndexOf(text, query,
            System.Globalization.CompareOptions.IgnoreCase | System.Globalization.CompareOptions.IgnoreNonSpace) >= 0;
    static object Page<T>(IEnumerable<T> items, int limit, int offset)
    {
        var all = items.ToList();
        return new { total = all.Count, offset, results = all.Skip(offset).Take(limit),
            nextOffset = offset + limit < all.Count ? (int?)(offset + limit) : null };
    }
    public async Task<object> Call(string tool, JsonElement args)
    {
        if (args.ValueKind != JsonValueKind.Object) throw new ArgumentException("arguments doit être un objet.");
        if (tool == "refresh")
        {
            var id = Guid.NewGuid().ToString("N");
            Wire.AtomicWrite(Path.Combine(directory, "request.json"), JsonSerializer.Serialize(new { id }));
            for (var attempt = 0; attempt < 30; attempt++)
            {
                await Task.Delay(100);
                try { var current = Read(); if (current.RequestId == id) return new { refreshed = true, current.CapturedAt, current.Connected }; }
                catch (IOException) { }
                catch (InvalidOperationException) { }
            }
            return new { refreshed = false, message = "Le jeu n'a pas répondu en 3 secondes. Il peut être fermé, déconnecté ou en chargement." };
        }
        var s = Read();
        var now = DateTimeOffset.UtcNow;
        var fresh = Fresh(s, now);
        var query = Text(args, "query");
        var limit = Math.Clamp(Int(args, "limit", 15), 1, 50);
        var offset = Math.Max(0, Int(args, "offset", 0));
        object data = tool switch
        {
            "get_shared_inventory" => SharedView(s, query, limit, offset, now),
            "get_character" => CharacterView(s, query, limit, offset, now),
            "get_equipment" => EquipmentView(s, query, limit, offset, now),
            "get_buffs" => BuffView(s, query, limit, offset, now),
            "explain_stat" => ExplainStat(s, query),
            "estimate_damage" => Damage(s, args),
            "get_status" => new { s.SharedInventoryStatus, sharedInventory = SharedView(s, "", 1, 0, now), s.ModVersion, s.GameVersion, s.SchemaVersion, s.Player, s.Capabilities,
                character = new { stats = s.Stats?.Values.Count ?? 0, blood = s.Blood != null,
                    equipmentSlots = s.Equipment.Count, buffs = s.Buffs.Count, spellSlots = s.Spells.Count },
                inventories = s.Inventories.Count, stations = s.Stations.Count,
                recipes = s.Recipes.Count, unlocks = s.Unlocks.Count, s.Warnings },
            "find_stock" => Page(s.Inventories.Concat(CountedStocks(s).Where(x => x.Kind == "shared_castle")).SelectMany(inv => inv.Items
                .Where(i => Match(i.Name, query) || i.Guid.ToString() == query)
                .Select(i => new { i.Guid, i.Name, i.Amount, inventoryId = inv.Id,
                    container = inv.Name, inv.Kind, inv.ObservedAt,
                    includedInTotals = s.SharedInventory == null || inv.Kind is "player" or "shared_castle",
                    state = Live(s, inv.Observing, inv.ObservedAt, now) ? "observed_now" : "last_observed" })), limit, offset),
            "get_stations" => Page(s.Stations.Where(st => Match(st.Name, query) || st.Id == query)
                .Select(st => new { st.Id, st.Name, st.MatchingFloor, st.ConfinedRoom, st.Level,
                    st.ObservedAt, state = Live(s, st.Observing, st.ObservedAt, now) ? "observed_now" : "last_observed",
                    st.Recipes, st.Queue }), limit, offset),
            "get_progression" => Page(s.Unlocks.Where(u => Match(u.Name, query) || u.Guid.ToString() == query), limit, offset),
            "find_recipes" => Page(s.Recipes.Where(r => Match(r.Name, query) || r.Guid.ToString() == query ||
                r.Outputs.Any(o => Match(o.Name, query))), limit, offset),
            "plan_craft" => Plan(s, Int(args, "recipeGuid", 0), Text(args, "stationId"),
                Int(args, "batches", 1), Bool(args, "includeCached"), now),
            "get_overview" => Overview(s, now),
            "summarize_stock" => Page(Totals(s, now).Where(t => Match(t.Name, query) || t.Guid.ToString() == query), limit, offset),
            "list_containers" => Containers(s, query, limit, offset, now),
            "audit_stations" => Audit(s, query, limit, offset, now),
            "compare_recipe_stations" => Compare(s, Int(args, "recipeGuid", 0), Bool(args, "includeCached"), limit, offset, now),
            "plan_project" => Project(s, args, now),
            _ => throw new ArgumentException("Outil inconnu : " + tool)
        };
        return new { s.SessionId, s.CapturedAt, s.Connected, fresh,
            accounting = Accounting(s),
            coverage = "Client uniquement : inventaire partagé répliqué et contenants observés. Les données mémorisées peuvent avoir changé. Les localisations ne doivent pas être additionnées aux totaux partagés.", data };
    }
    public static object Plan(Snapshot s, int recipeGuid, string stationId, int batches, bool includeCached, DateTimeOffset now)
    {
        if (batches is < 1 or > 10000) throw new ArgumentException("batches doit être compris entre 1 et 10000.");
        var recipe = s.Recipes.FirstOrDefault(r => r.Guid == recipeGuid)
            ?? throw new ArgumentException("Recette inconnue. Utilise find_recipes.");
        var station = s.Stations.FirstOrDefault(st => st.Id == stationId)
            ?? throw new ArgumentException("Station inconnue. Ouvre son menu dans le jeu, puis utilise get_stations.");
        if (!station.Recipes.Contains(recipeGuid)) throw new ArgumentException("Cette recette n'a pas été observée sur cette station.");
        var costs = station.EffectiveRecipes.FirstOrDefault(r => r.Guid == recipeGuid);
        if (costs == null) return new { canConfirm = false, reason = "Coûts effectifs non accessibles : ouvre le menu de la station. Aucun bonus n'est supposé.", recipe };
        var fresh = Fresh(s, now);
        var live = CountedStocks(s).Where(i => Live(s, i.Observing, i.ObservedAt, now)).ToList();
        var cached = CountedStocks(s).Where(i => !Live(s, i.Observing, i.ObservedAt, now)).ToList();
        var materials = GroupCosts(costs.Inputs).Select(m =>
        {
            var needed = checked((long)m.Amount * batches);
            var observed = live.Sum(i => i.Items.Where(x => x.Guid == m.Guid).Sum(x => x.Amount));
            var remembered = cached.Sum(i => i.Items.Where(x => x.Guid == m.Guid).Sum(x => x.Amount));
            return new { m.Guid, m.Name, needed, observedNow = observed, lastObserved = remembered,
                missing = Math.Max(0, needed - observed - (includeCached ? remembered : 0)) };
        }).ToList();
        var costsVerified = costs.Source == "workstation_ui";
        var certain = Live(s, station.Observing, station.ObservedAt, now) && recipe.Unlocked == true && !includeCached && costsVerified;
        return new { recipe = recipe.Name, station = station.Name, batches,
            canConfirm = certain, materialsSufficient = materials.All(m => m.missing == 0),
            canCraft = certain ? (bool?)materials.All(m => m.missing == 0) : null,
            unlocked = recipe.Unlocked, costsVerified, estimateIncludesCached = includeCached,
            warning = includeCached ? "Les stocks mémorisés peuvent compter deux fois des objets déplacés. Vérifie les coffres." :
                (!costsVerified ? "Les coûts de raffinage sont estimés ; leur arrondi reste à valider dans le jeu." :
                (!certain ? "La fraîcheur des données ou le déblocage ne permet pas de confirmer la fabrication." : null)),
            seconds = costs.Seconds * batches, costs.Source, materials,
            outputs = recipe.Outputs.Select(o => new { o.Name, amount = (long)o.Amount * batches }) };
    }
}
