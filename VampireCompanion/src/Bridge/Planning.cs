using System.Text.Json;

namespace VampireCompanion;

public sealed partial class CompanionTools
{
    // A live heartbeat must never make an old observation appear current.
    static bool Live(Snapshot s, bool observing, DateTimeOffset observedAt, DateTimeOffset now) =>
        observing && Fresh(s, now) && (now - observedAt).TotalSeconds is >= -5 and <= 10;
    static string State(Snapshot s, bool observing, DateTimeOffset at, DateTimeOffset now) =>
        Live(s, observing, at, now) ? "observed_now" : "last_observed";
    sealed record Total(int Guid, string Name, long ObservedNow, long LastObserved,
        int RecentContainers, int RememberedContainers);
    static List<Total> Totals(Snapshot s, DateTimeOffset now) => CountedStocks(s)
        .SelectMany(inv => inv.Items.Select(i => new { item = i, inv.Id,
            live = Live(s, inv.Observing, inv.ObservedAt, now) }))
        .GroupBy(x => x.item.Guid).Select(g => new Total(g.Key, g.First().item.Name,
            g.Where(x => x.live).Sum(x => x.item.Amount), g.Where(x => !x.live).Sum(x => x.item.Amount),
            g.Where(x => x.live).Select(x => x.Id).Distinct().Count(),
            g.Where(x => !x.live).Select(x => x.Id).Distinct().Count()))
        .OrderBy(x => x.Name, StringComparer.OrdinalIgnoreCase).ThenBy(x => x.Guid).ToList();

    static object Overview(Snapshot s, DateTimeOffset now) => new {
        s.Player,
        sharedInventory = SharedView(s, "", 1, 0, now),
        accounting = Accounting(s),
        inventories = new { known = s.Inventories.Count,
            recent = s.Inventories.Count(i => Live(s, i.Observing, i.ObservedAt, now)),
            remembered = s.Inventories.Count(i => !Live(s, i.Observing, i.ObservedAt, now)),
            resourceTypes = s.Inventories.SelectMany(i => i.Items).Select(i => i.Guid).Distinct().Count() },
        stations = new { known = s.Stations.Count,
            recent = s.Stations.Count(st => Live(s, st.Observing, st.ObservedAt, now)),
            missingFloorAtLastObservation = s.Stations.Count(st => st.MatchingFloor == false),
            missingRoomAtLastObservation = s.Stations.Count(st => st.ConfinedRoom == false),
            unknownBonuses = s.Stations.Count(st => st.MatchingFloor == null || st.ConfinedRoom == null),
            productionObservedRecently = s.Stations.Count(st => st.Queue.Count > 0 && Live(s, st.Observing, st.ObservedAt, now)),
            productionRemembered = s.Stations.Count(st => st.Queue.Count > 0 && !Live(s, st.Observing, st.ObservedAt, now)) },
        unlocks = s.Unlocks.GroupBy(u => u.Kind).ToDictionary(g => g.Key, g => g.Count()),
        knownRecipes = s.Recipes.Count, s.Capabilities, s.Warnings,
        nextStep = !Fresh(s, now) ? "Relancer le jeu ou actualiser les données avant de décider." :
            "Ouvrir les coffres et stations concernés pour actualiser leurs observations."
    };

    static double? Distance(float[]? a, float[]? b)
    {
        if (a?.Length != 3 || b?.Length != 3 || a.Any(x => !float.IsFinite(x)) || b.Any(x => !float.IsFinite(x))) return null;
        return Math.Round(Math.Sqrt(a.Select((x, i) => Math.Pow((double)x - b[i], 2)).Sum()), 1);
    }

    static object Containers(Snapshot s, string query, int limit, int offset, DateTimeOffset now) =>
        Page(s.Inventories.Where(i => Match(i.Name, query) || i.Id == query ||
            i.Items.Any(x => Match(x.Name, query) || x.Guid.ToString() == query))
        .OrderBy(i => i.Name).ThenBy(i => i.Id).Select(i => new {
            i.Id, i.OwnerId, i.Name, i.Kind, i.ObservedAt, i.Position,
            distanceFromPlayer = Fresh(s, now) ? Distance(s.Player?.Position, i.Position) : null,
            observationAgeSeconds = Math.Max(0, (now - i.ObservedAt).TotalSeconds),
            state = State(s, i.Observing, i.ObservedAt, now),
            resourceTypes = i.Items.Select(x => x.Guid).Distinct().Count(),
            observedEmpty = i.Items.Count == 0
        }), limit, offset);

    static object Audit(Snapshot s, string query, int limit, int offset, DateTimeOffset now) =>
        Page(s.Stations.Where(st => Match(st.Name, query) || st.Id == query).Select(st => new {
            st.Id, st.Name, st.ObservedAt, st.Position, state = State(s, st.Observing, st.ObservedAt, now),
            st.MatchingFloor, st.ConfinedRoom,
            checks = new[] {
                st.MatchingFloor == false ? "Bonus de sol absent à la dernière observation : vérifier le sol adapté." :
                    st.MatchingFloor == null ? "Bonus de sol inconnu." : null,
                st.ConfinedRoom == false ? "Bonus de pièce close absent à la dernière observation : vérifier la fermeture de la pièce." :
                    st.ConfinedRoom == null ? "Bonus de pièce close inconnu." : null,
                !Live(s, st.Observing, st.ObservedAt, now) ? "Rouvrir la station pour confirmer son état." : null
            }.Where(x => x != null),
            production = new { entries = st.Queue.Count, results = st.Queue.Take(10), truncated = st.Queue.Count > 10 },
            outputInventories = s.Inventories.Where(i => i.OwnerId == st.Id && i.Kind == "station_output")
                .Select(i => new { i.Id, resourceTypes = i.Items.Count,
                    hasItemsAtObservation = i.Items.Any(x => x.Amount > 0),
                    state = State(s, i.Observing, i.ObservedAt, now) }).Take(10)
        }), limit, offset);

    static List<Material> GroupCosts(IEnumerable<Material> inputs)
    {
        if (inputs.Any(i => i.Amount < 0)) throw new InvalidOperationException("Coût négatif invalide.");
        return inputs.GroupBy(i => i.Guid)
            .Select(g => new Material(g.Key, g.First().Name, g.Sum(x => x.Amount))).ToList();
    }
    static object Compare(Snapshot s, int recipeGuid, bool includeCached, int limit, int offset, DateTimeOffset now)
    {
        var recipe = s.Recipes.FirstOrDefault(r => r.Guid == recipeGuid)
            ?? throw new ArgumentException("Recette inconnue. Utilise find_recipes.");
        var totals = Totals(s, now).ToDictionary(t => t.Guid);
        return Page(s.Stations.Where(st => st.Recipes.Contains(recipeGuid)).Select(st => {
            var effective = st.EffectiveRecipes.FirstOrDefault(r => r.Guid == recipeGuid);
            var inputs = effective == null ? null : GroupCosts(effective.Inputs);
            var materials = inputs?.Select(m => {
                totals.TryGetValue(m.Guid, out var stock);
                var available = checked((stock?.ObservedNow ?? 0) + (includeCached ? stock?.LastObserved ?? 0 : 0));
                var baseInputs = recipe.Inputs.Where(x => x.Guid == m.Guid).ToList();
                long? baseAmount = baseInputs.Count == 0 ? null : baseInputs.Sum(x => (long)x.Amount);
                return new { m.Guid, m.Name, neededPerBatch = m.Amount, available,
                    baseAmount, savedPerBatch = baseAmount - m.Amount,
                    batchesFromThisMaterial = m.Amount > 0 ? (long?)(available / m.Amount) : null };
            }).ToList();
            var constraints = materials?.Where(m => m.batchesFromThisMaterial.HasValue).ToList();
            long? maxBatches = constraints?.Count > 0 ? constraints.Min(m => m.batchesFromThisMaterial) : null;
            return new { stationId = st.Id, st.Name, st.ObservedAt,
                state = State(s, st.Observing, st.ObservedAt, now), st.MatchingFloor, st.ConfinedRoom,
                recipe.Unlocked, costsAvailable = effective != null,
                costsVerified = effective?.Source == "workstation_ui", source = effective?.Source,
                secondsPerBatch = effective?.Seconds, maxBatchesByIngredients = maxBatches,
                estimateIncludesCached = includeCached, materials,
                warning = "Capacité théorique d'après les stocks observés. Transferts, accès, files en cours et conditions de lancement non vérifiés. Les observations mémorisées peuvent compter deux fois des objets déplacés."
            };
        }), limit, offset);
    }

    static object Project(Snapshot s, JsonElement args, DateTimeOffset now)
    {
        if (!args.TryGetProperty("targets", out var targets) || targets.ValueKind != JsonValueKind.Array ||
            targets.GetArrayLength() is < 1 or > 20)
            throw new ArgumentException("targets doit contenir entre 1 et 20 fabrications.");
        var includeCached = Bool(args, "includeCached");
        var needs = new Dictionary<int, (string Name, long Amount)>();
        var plans = new List<object>();
        var blockers = new List<string>();
        var unverified = false;
        var completeCosts = true;
        var totalSecondsKnown = true;
        double sequentialSeconds = 0;
        foreach (var target in targets.EnumerateArray())
        {
            if (target.ValueKind != JsonValueKind.Object) throw new ArgumentException("Chaque cible doit être un objet.");
            var batches = Int(target, "batches", 1);
            if (batches is < 1 or > 10000) throw new ArgumentException("batches doit être compris entre 1 et 10000.");
            var recipeGuid = Int(target, "recipeGuid", 0);
            var stationId = Text(target, "stationId");
            var recipe = s.Recipes.FirstOrDefault(r => r.Guid == recipeGuid)
                ?? throw new ArgumentException("Recette inconnue : " + recipeGuid);
            var station = s.Stations.FirstOrDefault(st => st.Id == stationId)
                ?? throw new ArgumentException("Station inconnue : " + stationId);
            if (!station.Recipes.Contains(recipeGuid)) throw new ArgumentException("Recette non observée sur la station : " + stationId);
            var cost = station.EffectiveRecipes.FirstOrDefault(r => r.Guid == recipeGuid);
            if (cost == null) { completeCosts = false; blockers.Add(recipe.Name + " : coûts indisponibles ; ouvrir la station."); }
            if (recipe.Unlocked != true) blockers.Add(recipe.Name + " : déblocage non confirmé.");
            if (cost != null)
                foreach (var m in GroupCosts(cost.Inputs))
                {
                    needs.TryGetValue(m.Guid, out var previous);
                    needs[m.Guid] = (m.Name, checked(previous.Amount + (long)m.Amount * batches));
                }
            unverified |= cost?.Source != "workstation_ui" || !Live(s, station.Observing, station.ObservedAt, now);
            if (cost?.Seconds is float seconds && float.IsFinite(seconds) && seconds >= 0) sequentialSeconds += seconds * (double)batches;
            else totalSecondsKnown = false;
            plans.Add(new { recipeGuid, recipe = recipe.Name, stationId, batches, recipe.Unlocked,
                source = cost?.Source, stationState = State(s, station.Observing, station.ObservedAt, now),
                outputs = recipe.Outputs.Select(o => new { o.Guid, o.Name, amount = (long)o.Amount * batches }) });
        }
        var totals = Totals(s, now).ToDictionary(t => t.Guid);
        var materials = needs.OrderBy(kv => kv.Value.Name).Select(kv => {
            totals.TryGetValue(kv.Key, out var stock);
            var available = checked((stock?.ObservedNow ?? 0) + (includeCached ? stock?.LastObserved ?? 0 : 0));
            return new { guid = kv.Key, name = kv.Value.Name, needed = kv.Value.Amount,
                observedNow = stock?.ObservedNow ?? 0, lastObserved = stock?.LastObserved ?? 0,
                missing = Math.Max(0, kv.Value.Amount - available) };
        }).ToList();
        return new { targets = plans, completeCosts, blockers,
            reliableIngredientsCheck = completeCosts && !unverified && !includeCached && Fresh(s, now) && blockers.Count == 0,
            materialsSufficient = completeCosts ? (bool?)materials.All(m => m.missing == 0) : null,
            estimateIncludesCached = includeCached,
            sequentialWorkSeconds = totalSecondsKnown ? (double?)sequentialSeconds : null,
            materials,
            warning = "Ingrédients directs cumulés ; les produits des étapes ne sont pas réutilisés automatiquement. La durée additionne le travail, sans tenir compte des files ni du parallélisme. Aucune garantie de lancement immédiat ; les stocks mémorisés peuvent être périmés ou compter deux fois des objets déplacés."
        };
    }
}
