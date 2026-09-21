using System.Text.Json;
using System.Text.Json.Serialization;

namespace VampireCompanion;

public static class Wire
{
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };
    public static string DefaultDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "VampireCompanion");
    public static void AtomicWrite(string path, string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try { File.WriteAllText(temp, content); File.Move(temp, path, true); }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
}

public sealed record Item(int Guid, string Name, long Amount);
public sealed record Material(int Guid, string Name, int Amount);
public sealed record Player(string Name, float? Health, float? MaxHealth,
    float[]? Position, Dictionary<string, string> Details);
public sealed record Stock(string Id, string OwnerId, string Name, string Kind,
    DateTimeOffset ObservedAt, bool Observing, List<Item> Items)
{
    public float[]? Position { get; init; }
}
public sealed record Recipe(int Guid, string Name, List<Material> Inputs,
    List<Material> Outputs, float? BaseSeconds, bool? Unlocked);
public sealed record EffectiveRecipe(int Guid, List<Material> Inputs,
    float? Seconds, string Source);
public sealed record Station(string Id, string Name, DateTimeOffset ObservedAt,
    bool Observing, bool? MatchingFloor, bool? ConfinedRoom,
    string Level, List<int> Recipes, List<EffectiveRecipe> EffectiveRecipes,
    List<Production> Queue)
{
    public float[]? Position { get; init; }
}
public sealed record Production(int RecipeGuid, string Name, int? Amount, float? Progress);
public sealed record Unlock(int Guid, string Name, string Kind);

public sealed record SharedInventoryObservation(string ManagerId, DateTimeOffset ObservedAt,
    bool Accessible, int InstanceCount, List<Item> Items);

// One line of the character's final stat block, as the game computed it. Field is the
// raw name found on the game component: obfuscated names are kept as-is rather than
// guessed, and Label is null when no French wording is known for that field.
public sealed record StatValue(string Field, string? Label, float Value);
public sealed record CharacterStats(List<StatValue> Values, List<string> Unreadable);

// A single contribution declared by a piece of gear, a buff or a blood bonus. These are
// inputs to the final stats, never a second helping on top of them.
public sealed record StatBonus(string Stat, string? Label, float Value, string? Modification);
public sealed record Modifier(int Guid, string Name, float Power);

public sealed record EquipmentPiece(string Slot, int Guid, string Name,
    float? Durability, float? MaxDurability, int? LegendaryTier,
    int? InfusionGuid, string? InfusionName,
    List<StatBonus> Bonuses, string BonusSource, List<Modifier> StatMods);

public sealed record ActiveBuff(int Guid, string Name, float? TotalSeconds,
    float? RemainingSeconds, bool Permanent, List<StatBonus> Bonuses);

// Amount and Quality are the values the client holds; MaxAmount stays null unless the
// game exposes it, because 100 is a convention and not an observation.
public sealed record BloodState(int TypeGuid, string TypeName, float? Quality,
    float? Amount, float? MaxAmount);

public sealed record SpellSlot(int Index, int GroupGuid, string GroupName,
    bool ModsReadable, List<Modifier> Mods);

// French wording for the stat names the game exposes. A name missing from this map is
// reported with its raw field name and a null label, never renamed to a guess.
public static class Labels
{
    public static string? Stat(string field) => Map.TryGetValue(field, out var label) ? label : null;
    static readonly Dictionary<string, string> Map = new(StringComparer.OrdinalIgnoreCase)
    {
        ["PhysicalPower"] = "Puissance physique",
        ["SpellPower"] = "Puissance magique",
        ["BonusPhysicalPower"] = "Puissance physique bonus",
        ["BonusSpellPower"] = "Puissance magique bonus",
        ["WeaponSkillPower"] = "Puissance de compétence d'arme",
        ["ResourcePower"] = "Puissance de récolte",
        ["SiegePower"] = "Puissance de siège",
        ["PhysicalCriticalStrikeChance"] = "Chance de coup critique physique",
        ["PhysicalCriticalStrikeDamage"] = "Dégâts de coup critique physique",
        ["SpellCriticalStrikeChance"] = "Chance de coup critique magique",
        ["SpellCriticalStrikeDamage"] = "Dégâts de coup critique magique",
        ["PhysicalResistance"] = "Résistance physique",
        ["SpellResistance"] = "Résistance magique",
        ["FireResistance"] = "Résistance au feu",
        ["HolyResistance"] = "Résistance sacrée",
        ["SilverResistance"] = "Résistance à l'argent",
        ["SilverCoinResistance"] = "Résistance aux pièces d'argent",
        ["DamageReduction"] = "Réduction des dégâts",
        ["CorruptionDamageReduction"] = "Réduction des dégâts de corruption",
        ["PvPResilience"] = "Résilience JcJ",
        ["MaxHealth"] = "Vie maximale",
        ["BonusMaxHealth"] = "Vie maximale bonus",
        ["HealthRecovery"] = "Récupération de vie",
        ["PassiveHealthRegen"] = "Régénération passive de vie",
        ["HealingReceived"] = "Soins reçus",
        ["PhysicalLifeLeech"] = "Vol de vie physique",
        ["SpellLifeLeech"] = "Vol de vie magique",
        ["PrimaryLifeLeech"] = "Vol de vie de l'attaque principale",
        ["MovementSpeed"] = "Vitesse de déplacement",
        ["BonusMovementSpeed"] = "Vitesse de déplacement bonus",
        ["BonusMountMovementSpeed"] = "Vitesse de monture bonus",
        ["BonusShapeshiftMovementSpeed"] = "Vitesse sous forme animale bonus",
        ["AttackSpeed"] = "Vitesse d'attaque",
        ["PrimaryAttackSpeed"] = "Vitesse d'attaque principale",
        ["AbilityAttackSpeed"] = "Vitesse d'incantation",
        ["CooldownRecoveryRate"] = "Récupération des temps de recharge",
        ["SpellCooldownRecoveryRate"] = "Récupération des sorts",
        ["WeaponCooldownRecoveryRate"] = "Récupération des armes",
        ["UltimateCooldownRecoveryRate"] = "Récupération de l'ultime",
        ["TravelCooldownRecoveryRate"] = "Récupération des déplacements",
        ["FeedCooldownRecoveryRate"] = "Récupération de morsure",
        ["PrimaryCooldownModifier"] = "Modificateur de l'attaque principale",
        ["UltimateEfficiency"] = "Efficacité de l'ultime",
        ["BloodDrain"] = "Consommation de sang",
        ["ReducedBloodDrain"] = "Consommation de sang réduite",
        ["BloodDrainMultiplier"] = "Multiplicateur de consommation de sang",
        ["BloodEfficiency"] = "Efficacité du sang",
        ["BloodMendHealEfficiency"] = "Efficacité de Régénération sanguine",
        ["ShieldAbsorb"] = "Absorption des boucliers",
        ["IncreasedShieldEfficiency"] = "Efficacité des boucliers",
        ["CCReduction"] = "Réduction des contrôles",
        ["DemountProtection"] = "Protection contre le démontage",
        ["MinionDamage"] = "Dégâts des serviteurs",
        ["InventorySlots"] = "Emplacements d'inventaire",
        ["ResourceYield"] = "Rendement de récolte",
        ["ReducedResourceDurabilityLoss"] = "Perte de durabilité réduite",
        ["ImmuneToHazards"] = "Immunité aux dangers",
        ["SpellFreeCast"] = "Incantation gratuite (sort)",
        ["WeaponFreeCast"] = "Incantation gratuite (arme)",
        ["FallGravity"] = "Gravité de chute",
        ["DamageVsBeasts"] = "Dégâts contre les bêtes",
        ["DamageVsCastleObjects"] = "Dégâts contre les objets de château",
        ["DamageVsDemons"] = "Dégâts contre les démons",
        ["DamageVsHumans"] = "Dégâts contre les humains",
        ["DamageVsLightArmor"] = "Dégâts contre les armures légères",
        ["DamageVsMagic"] = "Dégâts contre la magie",
        ["DamageVsMechanical"] = "Dégâts contre les mécaniques",
        ["DamageVsMineral"] = "Dégâts contre le minéral",
        ["DamageVsUndeads"] = "Dégâts contre les morts-vivants",
        ["DamageVsVampires"] = "Dégâts contre les vampires",
        ["DamageVsVBloods"] = "Dégâts contre les V Blood",
        ["DamageVsVegetation"] = "Dégâts contre la végétation",
        ["DamageVsWood"] = "Dégâts contre le bois",
        ["ResistVsBeasts"] = "Résistance aux bêtes",
        ["ResistVsCastleObjects"] = "Résistance aux objets de château",
        ["ResistVsDemons"] = "Résistance aux démons",
        ["ResistVsHumans"] = "Résistance aux humains",
        ["ResistVsMechanical"] = "Résistance aux mécaniques",
        ["ResistVsUndeads"] = "Résistance aux morts-vivants",
        ["ResistVsVampires"] = "Résistance aux vampires",
        ["Radial_SpellResistance"] = "Résistance magique radiale"
    };
}

public sealed class Snapshot
{
    public int SchemaVersion { get; set; } = 2;
    public string ModVersion { get; set; } = "0.4.0";
    public string GameVersion { get; set; } = "unknown";
    public string SessionId { get; set; } = "disconnected";
    public string? RequestId { get; set; }
    public DateTimeOffset CapturedAt { get; set; } = DateTimeOffset.UtcNow;
    public bool Connected { get; set; }
    public Player? Player { get; set; }
    public CharacterStats? Stats { get; set; }
    public BloodState? Blood { get; set; }
    public List<EquipmentPiece> Equipment { get; set; } = new();
    public List<ActiveBuff> Buffs { get; set; } = new();
    public List<SpellSlot> Spells { get; set; } = new();
    public SharedInventoryObservation? SharedInventory { get; set; }
    public string SharedInventoryStatus { get; set; } = "not_collected";
    public List<Stock> Inventories { get; set; } = new();
    public List<Station> Stations { get; set; } = new();
    public List<Recipe> Recipes { get; set; } = new();
    public List<Unlock> Unlocks { get; set; } = new();
    public Dictionary<string, string> Capabilities { get; set; } = new();
    public List<string> Warnings { get; set; } = new();
}
