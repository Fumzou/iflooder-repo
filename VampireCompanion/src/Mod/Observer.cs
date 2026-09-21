using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using ProjectM;
using ProjectM.Network;
using ProjectM.CastleBuilding;
using ProjectM.Scripting;
using ProjectM.UI;
using Stunlock.Core;
using Stunlock.Localization;
using Unity.Entities;
using Unity.Transforms;
using UnityEngine;

namespace VampireCompanion;

// All game reads run from Unity system postfixes on the game's thread. The MCP process
// reads only atomic JSON files; it never touches an EntityManager from another thread.
internal sealed partial class Observer
{
    readonly string directory;
    readonly double interval;
    readonly Stopwatch clock = Stopwatch.StartNew();
    readonly Dictionary<string, Stock> stocks = new();
    readonly Dictionary<string, Station> stations = new();
    readonly Dictionary<int, Recipe> recipes = new();
    readonly Dictionary<int, string> names = new();
    readonly Dictionary<string, double> nextVisits = new();
    readonly Dictionary<string, string> errors = new();
    World? world;
    EntityManager em;
    GameDataSystem gameData = null!;
    PrefabCollectionSystem prefabs = null!;
    ClientGameManager client;
    Entity character, user;
    Snapshot snapshot = new();
    double nextPoll;

    public Observer(string directory, double interval)
    {
        this.directory = Path.GetFullPath(directory); this.interval = interval;
        Write();
    }
    public void Report(string section, Exception ex)
    {
        var message = section + ": " + ex.GetType().Name + " — " + ex.Message;
        if (errors.TryGetValue(section, out var previous) && previous == message) return;
        errors[section] = message;
        Plugin.Instance.Log.LogWarning(message);
    }
    void Part(string name, Action action)
    {
        try { action(); snapshot.Capabilities[name] = "observed"; errors.Remove(name); }
        catch (Exception ex) { snapshot.Capabilities[name] = "unavailable"; Report(name, ex); }
    }
    bool Initialize(World candidate)
    {
        if (!candidate.IsCreated || candidate.Name != "Client") return false;
        if (world == null || world.Pointer != candidate.Pointer)
        {
            var dataSystem = candidate.GetExistingSystemManaged<GameDataSystem>();
            var prefabSystem = candidate.GetExistingSystemManaged<PrefabCollectionSystem>();
            var scriptSystem = candidate.GetExistingSystemManaged<ClientScriptMapper>();
            if (dataSystem == null || prefabSystem == null || scriptSystem == null) return false;
            world = candidate; em = candidate.EntityManager;
            stocks.Clear(); stations.Clear(); recipes.Clear(); names.Clear(); nextVisits.Clear();
            snapshot = new Snapshot { SessionId = Guid.NewGuid().ToString("N"), GameVersion = Application.version };
            gameData = dataSystem; prefabs = prefabSystem; client = scriptSystem._ClientGameManager;
        }
        return ConsoleShared.TryGetLocalCharacterInCurrentWorld(out character, world) &&
            ConsoleShared.TryGetLocalUserInCurrentWorld(out user, world) && em.Exists(character) && em.Exists(user);
    }
    public void Pump()
    {
        if (world != null && world.IsCreated) Tick(world);
    }
    public void Tick(World candidate)
    {
        if (clock.Elapsed.TotalSeconds < nextPoll) return;
        nextPoll = clock.Elapsed.TotalSeconds + interval;
        if (!Initialize(candidate)) { if (snapshot.Connected) Disconnect(); return; }
        snapshot.Connected = true;
        Part("player", ReadPlayer);
        Part("stats", ReadStats);
        Part("blood", ReadBlood);
        Part("equipment", ReadEquipment);
        Part("buffs", ReadBuffs);
        Part("spells", ReadSpells);
        Part("player_inventory", () => ReadInventories(character, "player", "Personnage"));
        Part("progression", ReadProgression);
        Part("shared_inventory", ReadSharedInventory);
        snapshot.Capabilities["shared_inventory"] = snapshot.SharedInventoryStatus;
        foreach (var key in stocks.Keys.ToList())
            stocks[key] = stocks[key] with { Observing = (DateTimeOffset.UtcNow - stocks[key].ObservedAt).TotalSeconds < interval + 1 };
        foreach (var key in stations.Keys.ToList())
            stations[key] = stations[key] with { Observing = (DateTimeOffset.UtcNow - stations[key].ObservedAt).TotalSeconds < interval + 1 };
        var requestPath = Path.Combine(directory, "request.json");
        if (File.Exists(requestPath))
        {
            try
            {
                using var request = JsonDocument.Parse(File.ReadAllText(requestPath));
                snapshot.RequestId = request.RootElement.GetProperty("id").GetString();
                // Keep the small request file: avoids deleting a concurrent client's newer request.
            }
            catch (Exception ex) { Report("request", ex); }
        }
        Write();
    }
    void ReadSharedInventory()
    {
        // Invalidate first: a failed or incomplete read must never renew cached quantities.
        if (snapshot.SharedInventory != null)
            snapshot.SharedInventory = snapshot.SharedInventory with { Accessible = false };
        snapshot.SharedInventoryStatus = "no_character_connection";
        if (!em.HasComponent<SharedCastleInventoryConnection>(character)) return;
        var manager = em.GetComponentData<SharedCastleInventoryConnection>(character).SharedInventoryManager._Entity;
        if (manager == Entity.Null) return;
        snapshot.SharedInventoryStatus = "manager_not_replicated";
        if (!em.Exists(manager)) return;
        snapshot.SharedInventoryStatus = "instances_not_replicated";
        if (!em.HasComponent<SharedCastleInventoryInstances>(manager)) return;
        var instances = em.GetBuffer<SharedCastleInventoryInstances>(manager, true);
        if (instances.Length == 0) { snapshot.SharedInventoryStatus = "empty_instance_list_unconfirmed"; return; }
        var seen = new HashSet<Entity>();
        var amounts = new Dictionary<int, long>();
        for (var i = 0; i < instances.Length; i++)
        {
            var entity = instances[i].Entity._Entity;
            if (entity == Entity.Null || !em.Exists(entity) || !em.HasComponent<SharedCastleInventoryItems>(entity))
            { snapshot.SharedInventoryStatus = "partial_replication"; return; }
            if (!seen.Add(entity)) continue;
            if (em.HasComponent<SharedCastleInventoryInstance>(entity) &&
                em.GetComponentData<SharedCastleInventoryInstance>(entity).ManagerEntity._Entity != manager)
            { snapshot.SharedInventoryStatus = "instance_manager_mismatch"; return; }
            var items = em.GetBuffer<SharedCastleInventoryItems>(entity, true);
            for (var j = 0; j < items.Length; j++)
            {
                var item = items[j];
                if (item.Amount < 0) { snapshot.SharedInventoryStatus = "invalid_quantity"; return; }
                if (item.ItemType.GuidHash == 0 || item.Amount == 0) continue;
                amounts.TryGetValue(item.ItemType.GuidHash, out var previous);
                amounts[item.ItemType.GuidHash] = checked(previous + item.Amount);
            }
        }
        // Commit only after every instance has been read successfully on the Unity thread.
        snapshot.SharedInventory = new SharedInventoryObservation(Id(manager), DateTimeOffset.UtcNow,
            true, seen.Count, amounts.Select(x => new Item(x.Key, Name(new PrefabGUID(x.Key)), x.Value)).ToList());
        snapshot.SharedInventoryStatus = "observed";
    }
    void Write()
    {
        snapshot.CapturedAt = DateTimeOffset.UtcNow;
        snapshot.Inventories = stocks.Values.ToList();
        snapshot.Stations = stations.Values.ToList();
        snapshot.Recipes = recipes.Values.ToList();
        snapshot.Warnings = errors.Values.ToList();
        snapshot.Capabilities["coverage"] = "Local character stats, blood, equipment, buffs and spell slots, opened menus and replicated shared inventory linked to the local character; reset on reconnect.";
        Wire.AtomicWrite(Path.Combine(directory, "snapshot.json"), JsonSerializer.Serialize(snapshot, Wire.Json));
    }
    public void Disconnect()
    {
        snapshot.Connected = false;
        if (snapshot.SharedInventory != null) snapshot.SharedInventory = snapshot.SharedInventory with { Accessible = false };
        snapshot.SharedInventoryStatus = "disconnected";
        foreach (var k in stocks.Keys.ToList()) stocks[k] = stocks[k] with { Observing = false };
        foreach (var k in stations.Keys.ToList()) stations[k] = stations[k] with { Observing = false };
        Write(); world = null; nextPoll = 0;
    }
    bool Ready(World candidate, Entity target, string section)
    {
        if (!Initialize(candidate) || !em.Exists(target)) return false;
        var key = section + Id(target);
        if (nextVisits.TryGetValue(key, out var next) && clock.Elapsed.TotalSeconds < next) return false;
        nextVisits[key] = clock.Elapsed.TotalSeconds + 0.5;
        return true;
    }
    public void VisitInventory(World candidate, Entity target)
    {
        if (!Ready(candidate, target, "inventory")) return;
        Part("opened_inventories", () => ReadInventories(target, target == character ? "player" : "container", EntityName(target)));
    }
    public void VisitWorkstation(World candidate, Entity target, WorkstationSubMenuMapper mapper)
    {
        if (!Ready(candidate, target, "workstation")) return;
        Part("workstations", () =>
        {
            ReadInventories(target, "station", EntityName(target));
            var ids = new List<int>(); var effective = new List<EffectiveRecipe>(); var queue = new List<Production>();
            foreach (var data in mapper._RecipesDatas)
            {
                var r = ReadRecipe(data.EntryId, data.IsUnlocked);
                if (r == null) continue;
                ids.Add(r.Guid);
                var costs = new List<Material>();
                // Match by localized item names, never by list position or a guessed 25% bonus.
                foreach (var input in r.Inputs)
                {
                    CostData? match = null;
                    foreach (var cost in data.Requirements)
                        if (Localization.Get(cost.ItemName) == input.Name) { match = cost; break; }
                    if (match == null) { costs.Clear(); break; }
                    costs.Add(input with { Amount = match.Amount });
                }
                if (costs.Count == r.Inputs.Count)
                    effective.Add(new EffectiveRecipe(r.Guid, costs, data.CraftDuration, "workstation_ui"));
                if (data.QueuedCount > 0) queue.Add(new Production(r.Guid, r.Name, data.QueuedCount, data.Progress));
            }
            RecordStation(target, ids, effective, queue);
        });
    }
    public void VisitRefinement(World candidate, Entity target, RefinementstationSubMenuMapper mapper)
    {
        if (!Ready(candidate, target, "refinement")) return;
        Part("refinement", () =>
        {
            ReadInventories(target, "station", EntityName(target));
            var ids = new List<int>(); var effective = new List<EffectiveRecipe>(); var queue = new List<Production>();
            foreach (var data in mapper._RecipesDatas)
            {
                var r = ReadRecipe(data.EntryId, data.IsUnlocked);
                if (r == null) continue;
                ids.Add(r.Guid);
                if (!float.IsFinite(data.ResourceMultiplier) || data.ResourceMultiplier < 0) continue;
                // Same replicated requirements and multiplier as the refinement UI.
                var costs = new List<Material>();
                for (var i = 0; i < data.Requirements.Length; i++)
                {
                    var requirement = data.Requirements[i];
                    costs.Add(new Material(requirement.Guid.GuidHash, Name(requirement.Guid),
                        Mathf.CeilToInt(requirement.Amount * data.ResourceMultiplier)));
                }
                effective.Add(new EffectiveRecipe(r.Guid, costs, null, "refinement_ui_multiplier; rounding_requires_ingame_validation"));
            }
            if (em.HasComponent<Refinementstation>(target))
            {
                var refiner = em.GetComponentData<Refinementstation>(target);
                if (refiner.IsWorking) queue.Add(new Production(refiner.CurrentRecipeGuid.GuidHash, Name(refiner.CurrentRecipeGuid), null, null));
                ReadInventory(refiner.InputInventoryEntity._Entity, target, "station_input", EntityName(target) + " — entrée");
                ReadInventory(refiner.OutputInventoryEntity._Entity, target, "station_output", EntityName(target) + " — sortie");
            }
            RecordStation(target, ids, effective, queue);
        });
    }
    void RecordStation(Entity target, List<int> ids, List<EffectiveRecipe> effective, List<Production> queue)
    {
        bool? floor = null, room = null; var level = "unknown";
        if (em.HasComponent<CastleWorkstation>(target))
        {
            var cw = em.GetComponentData<CastleWorkstation>(target);
            floor = (cw.WorkstationLevel & WorkstationLevel.MatchingFloor) != 0;
            room = (cw.WorkstationLevel & WorkstationLevel.EnclosedRoom) != 0;
            level = cw.WorkstationLevel.ToString();
        }
        stations[Id(target)] = new Station(Id(target), EntityName(target), DateTimeOffset.UtcNow,
            true, floor, room, level, ids.Distinct().ToList(), effective, queue) { Position = WorldPosition(target) };
    }
    void ReadInventories(Entity owner, string kind, string label)
    {
        ReadInventory(owner, owner, kind, label);
        if (!em.HasComponent<InventoryInstanceElement>(owner)) return;
        var instances = em.GetBuffer<InventoryInstanceElement>(owner, true);
        for (var i = 0; i < instances.Length; i++)
            ReadInventory(instances[i].ExternalInventoryEntity._Entity, owner, kind, label + " / " + instances[i].Category);
    }
    void ReadInventory(Entity inventory, Entity owner, string kind, string label)
    {
        if (inventory == Entity.Null || !em.Exists(inventory) || !em.HasComponent<InventoryBuffer>(inventory)) return;
        var buffer = em.GetBuffer<InventoryBuffer>(inventory, true);
        var quantities = new Dictionary<int, long>();
        for (var i = 0; i < buffer.Length; i++)
        {
            var entry = buffer[i]; if (entry.Amount <= 0 || entry.ItemType.GuidHash == 0) continue;
            quantities.TryGetValue(entry.ItemType.GuidHash, out var amount);
            quantities[entry.ItemType.GuidHash] = amount + entry.Amount;
        }
        var items = quantities.Select(kv => new Item(kv.Key, Name(new PrefabGUID(kv.Key)), kv.Value)).ToList();
        stocks[Id(inventory)] = new Stock(Id(inventory), Id(owner), label, kind, DateTimeOffset.UtcNow, true, items) { Position = WorldPosition(owner) };
    }
    float[]? WorldPosition(Entity entity)
    {
        // A local transform under a parent is not a world coordinate.
        if (!em.Exists(entity) || em.HasComponent<Parent>(entity) || !em.HasComponent<LocalTransform>(entity)) return null;
        var p = em.GetComponentData<LocalTransform>(entity).Position;
        return float.IsFinite(p.x) && float.IsFinite(p.y) && float.IsFinite(p.z) ? new[] { p.x, p.y, p.z } : null;
    }
    void ReadPlayer()
    {
        float? health = null, max = null; float[]? position = null;
        var details = new Dictionary<string, string>();
        if (em.HasComponent<Health>(character)) { var h = em.GetComponentData<Health>(character); health = h.Value; max = h.MaxHealth.Value; }
        position = WorldPosition(character);
        if (em.HasComponent<Equipment>(character))
        {
            var e = em.GetComponentData<Equipment>(character);
            details["weapon"] = Name(e.WeaponSlot.SlotId);
            details["weaponLevel"] = e.WeaponLevel.Value.ToString(CultureInfo.InvariantCulture);
            details["armorLevel"] = e.ArmorLevel.Value.ToString(CultureInfo.InvariantCulture);
            details["spellLevel"] = e.SpellLevel.Value.ToString(CultureInfo.InvariantCulture);
        }
        var playerName = em.HasComponent<User>(user) ? em.GetComponentData<User>(user).CharacterName.ToString() : "Personnage";
        snapshot.Player = new Player(playerName, health, max, position, details);
    }
    void ReadProgression()
    {
        var entities = new HashSet<Entity> { user, character };
        foreach (var e in entities.ToList())
            if (em.HasComponent<ProgressionMapper>(e))
            { var p = em.GetComponentData<ProgressionMapper>(e).ProgressionEntity._Entity; if (em.Exists(p)) entities.Add(p); }
        var unlocks = new Dictionary<string, Unlock>();
        void Add(PrefabGUID guid, string kind) => unlocks[kind + guid.GuidHash] = new Unlock(guid.GuidHash, Name(guid), kind);
        bool any = false;
        foreach (var e in entities)
        {
            if (em.HasComponent<UnlockedRecipeElement>(e))
            {
                any = true; var b = em.GetBuffer<UnlockedRecipeElement>(e, true);
                for (var i = 0; i < b.Length; i++) if (b[i].UserHasRequiredContentFlags)
                { Add(b[i].UnlockedRecipe, "recipe"); ReadRecipe(b[i].UnlockedRecipe, true); }
            }
            if (em.HasComponent<UnlockedBlueprintElement>(e))
            {
                any = true; var b = em.GetBuffer<UnlockedBlueprintElement>(e, true);
                for (var i = 0; i < b.Length; i++) if (b[i].UserHasRequiredContentFlags) Add(b[i].UnlockedBlueprint, "blueprint_or_floor");
            }
            if (em.HasComponent<UnlockedVBlood>(e))
            { any = true; var b = em.GetBuffer<UnlockedVBlood>(e, true); for (var i = 0; i < b.Length; i++) Add(b[i].VBlood, "vblood"); }
            if (em.HasComponent<UnlockedProgressionElement>(e))
            { any = true; var b = em.GetBuffer<UnlockedProgressionElement>(e, true); for (var i = 0; i < b.Length; i++) Add(b[i].UnlockedPrefab, "progression"); }
        }
        if (any) snapshot.Unlocks = unlocks.Values.ToList();
        else throw new InvalidOperationException("Les buffers de progression ne sont pas exposés actuellement par le client.");
    }
    Recipe? ReadRecipe(PrefabGUID guid, bool? unlocked)
    {
        if (!gameData.RecipeHashLookupMap.TryGetValue(guid, out var data)) return null;
        // Missing replicated buffers mean unknown data, never a free recipe.
        if (!em.Exists(data.Entity) || !em.HasComponent<RecipeRequirementBuffer>(data.Entity) ||
            !em.HasComponent<RecipeOutputBuffer>(data.Entity)) return null;
        var inputs = new List<Material>(); var outputs = new List<Material>();
        if (em.HasComponent<RecipeRequirementBuffer>(data.Entity))
        { var b = em.GetBuffer<RecipeRequirementBuffer>(data.Entity, true); for (var i = 0; i < b.Length; i++) inputs.Add(new Material(b[i].Guid.GuidHash, Name(b[i].Guid), b[i].Amount)); }
        if (em.HasComponent<RecipeOutputBuffer>(data.Entity))
        { var b = em.GetBuffer<RecipeOutputBuffer>(data.Entity, true); for (var i = 0; i < b.Length; i++) outputs.Add(new Material(b[i].Guid.GuidHash, Name(b[i].Guid), b[i].Amount)); }
        var r = new Recipe(guid.GuidHash, outputs.Count > 0 ? string.Join(" + ", outputs.Select(o => o.Name)) : Name(guid),
            inputs, outputs, data.CraftDuration, unlocked ?? (data.AlwaysUnlocked ? true : null));
        recipes[r.Guid] = r; return r;
    }
    string Name(PrefabGUID guid)
    {
        if (guid.GuidHash == 0) return "aucun";
        if (names.TryGetValue(guid.GuidHash, out var name)) return name;
        try
        {
            var managed = world!.GetExistingSystemManaged<ManagedDataSystem>().ManagedDataRegistry.GetOrDefault<ManagedItemData>(guid);
            if (managed != null) { name = Localization.Get(managed.Name); if (!string.IsNullOrWhiteSpace(name)) return names[guid.GuidHash] = name; }
        }
        catch { /* Prefabs without item localization retain their game debug name. */ }
        if (prefabs._PrefabGuidToEntityMap.TryGetValue(guid, out var entity))
        { name = client.GetDebugName(entity); if (!string.IsNullOrWhiteSpace(name)) return names[guid.GuidHash] = name; }
        return guid.GuidHash.ToString(CultureInfo.InvariantCulture);
    }
    string EntityName(Entity entity) => em.HasComponent<PrefabGUID>(entity) ? Name(em.GetComponentData<PrefabGUID>(entity)) : "Objet " + Id(entity);
    static string Id(Entity e) => e.Index + ":" + e.Version;
}
