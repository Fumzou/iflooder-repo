// The other half of the partial Observer, plus a runner that feeds the collector a
// synthetic character and checks what it publishes.
using System.Text.Json;
using ProjectM;
using ProjectM.Shared;
using Stunlock.Core;
using Unity.Entities;

namespace VampireCompanion;

public sealed class PrefabCollection
{
    public Dictionary<PrefabGUID, Entity> _PrefabGuidToEntityMap = new();
}

internal sealed partial class Observer
{
    internal EntityManager em = new();
    internal Entity character;
    internal PrefabCollection prefabs = new();
    internal Snapshot snapshot = new();
    internal readonly Dictionary<string, string> failures = new();

    string Name(PrefabGUID guid) => guid.GuidHash == 0 ? "aucun" : "Objet " + guid.GuidHash;

    internal void Part(string name, Action action)
    {
        try { action(); snapshot.Capabilities[name] = "observed"; }
        catch (Exception ex) { snapshot.Capabilities[name] = "unavailable"; failures[name] = ex.Message; }
    }

    internal void RunAll()
    {
        Part("stats", ReadStats);
        Part("blood", ReadBlood);
        Part("equipment", ReadEquipment);
        Part("buffs", ReadBuffs);
        Part("spells", ReadSpells);
    }
}

static class Harness
{
    static int failed;
    static void Check(string what, bool ok)
    {
        Console.WriteLine((ok ? "  ok   " : "  ECHEC") + "  " + what);
        if (!ok) failed++;
    }

    static int Main()
    {
        var o = new Observer();
        var em = o.em;
        var next = 1;
        Entity New() => new Entity { Index = next++, Version = 1 };

        o.character = New();
        em.SetAlive(o.character);
        em.Set(o.character, new UnitStats {
            PhysicalPower = ModifiableFloat.Of(100f),
            SpellPower = ModifiableFloat.Of(80f),
            PhysicalCriticalStrikeChance = ModifiableFloat.Of(0.2f),
            PhysicalCriticalStrikeDamage = ModifiableFloat.Of(1.5f),
            a = ModifiableFloat.Of(0.35f),
            MovementSpeed = ModifiableFloat.Of(0f),
            InventorySlots = 24,
            NotANumber = "ignoré" });
        em.Set(o.character, new Blood { BloodType = new PrefabGUID(7), Quality = 87.5f, Value = 62f });

        // Weapon: an instance carrying its own bonuses, a legendary tier and an infusion.
        var weapon = New();
        em.SetAlive(weapon);
        em.SetBuffer(weapon, new List<ModifyUnitStatBuff_DOTS> {
            new() { StatType = UnitStatType.PhysicalPower, Value = 30f, ModificationType = ModificationType.AddToBase },
            new() { StatType = UnitStatType.PhysicalPower, Value = 0f, ModificationType = ModificationType.AddToBase } });
        em.Set(weapon, new Durability { Value = 90f, MaxDurability = 100f });
        em.Set(weapon, new LegendaryItemInstance { TierIndex = 2 });
        em.Set(weapon, new LegendaryItemSpellModSetComponent {
            StatMods = new SpellModSet { Count = 1, Mod0 = new SpellMod { Id = new PrefabGUID(9), Power = 0.4f } },
            AbilityMods0 = new SpellModSet { Count = 1, Mod0 = new SpellMod { Id = new PrefabGUID(5), Power = 1f } } });

        // Chest piece: instance with no buffer, so the bonuses must fall back to the prefab.
        var chest = New();
        em.SetAlive(chest);
        var chestPrefab = New();
        em.SetBuffer(chestPrefab, new List<ModifyUnitStatBuff_DOTS> {
            new() { StatType = UnitStatType.PhysicalPower, Value = 12f, ModificationType = ModificationType.AddToBase } });
        o.prefabs._PrefabGuidToEntityMap[new PrefabGUID(102)] = chestPrefab;

        em.Set(o.character, new Equipment {
            WeaponSlot = new EquipmentSlot { SlotId = new PrefabGUID(101), SlotEntity = new NetworkedEntity { _Entity = weapon } },
            ArmorChestSlot = new EquipmentSlot { SlotId = new PrefabGUID(102), SlotEntity = new NetworkedEntity { _Entity = chest } },
            CloakSlot = new EquipmentSlot { SlotId = new PrefabGUID(0), SlotEntity = new NetworkedEntity { _Entity = Entity.Null } },
            ArmorLevel = ModifiableFloat.Of(50f) });

        var potion = New();
        em.SetAlive(potion);
        em.Set(potion, new LifeTime { Duration = 600f });
        em.Set(potion, new Age { Value = 480f });
        em.SetBuffer(potion, new List<ModifyUnitStatBuff_DOTS> {
            new() { StatType = UnitStatType.PhysicalPower, Value = 8f, ModificationType = ModificationType.AddToBase } });
        var bloodBuff = New();
        em.SetAlive(bloodBuff);
        em.Set(bloodBuff, new LifeTime { Duration = -1f });
        em.SetBuffer(o.character, new List<BuffBuffer> {
            new() { PrefabGuid = new PrefabGUID(201), Entity = potion },
            new() { PrefabGuid = new PrefabGUID(202), Entity = bloodBuff },
            new() { PrefabGuid = new PrefabGUID(0), Entity = Entity.Null } });

        var jewelled = New();
        em.SetAlive(jewelled);
        em.Set(jewelled, new SpellModSetComponent { SpellMods = new SpellModSet {
            Count = 1, Mod0 = new SpellMod { Id = new PrefabGUID(401), Power = 0.75f } } });
        var bare = New();
        em.SetAlive(bare);
        em.SetBuffer(o.character, new List<AbilityGroupSlotBuffer> {
            new() { BaseAbilityGroupOnSlot = new PrefabGUID(301), GroupSlotEntity = new NetworkedEntity { _Entity = jewelled } },
            new() { BaseAbilityGroupOnSlot = new PrefabGUID(302), GroupSlotEntity = new NetworkedEntity { _Entity = bare } } });

        o.RunAll();
        foreach (var failure in o.failures) Console.WriteLine("  !! " + failure.Key + " : " + failure.Value);
        var s = o.snapshot;

        Console.WriteLine("Statistiques");
        var stats = s.Stats!.Values;
        Check("tous les collecteurs ont abouti", o.failures.Count == 0);
        Check("champ obfusqué 'a' lu avec sa valeur", stats.Any(v => v.Field == "a" && Math.Abs(v.Value - 0.35f) < 1e-6));
        Check("champ obfusqué sans libellé inventé", stats.First(v => v.Field == "a").Label == null);
        Check("libellé français appliqué aux champs connus", stats.First(v => v.Field == "PhysicalPower").Label == "Puissance physique");
        Check("statistique à zéro conservée", stats.Any(v => v.Field == "MovementSpeed" && v.Value == 0f));
        Check("booléen lu comme 0/1", stats.Any(v => v.Field == "ImmuneToHazards" && v.Value == 0f));
        Check("entier nu lu", stats.Any(v => v.Field == "InventorySlots" && v.Value == 24f));
        Check("champ non numérique signalé au lieu d'être inventé", s.Stats.Unreadable.Contains("NotANumber"));

        Console.WriteLine("Sang");
        Check("qualité lue", s.Blood!.Quality == 87.5f);
        Check("quantité lue", s.Blood.Amount == 62f);
        Check("aucun maximum inventé", s.Blood.MaxAmount == null);

        Console.WriteLine("Équipement");
        Check("trois emplacements découverts par réflexion", s.Equipment.Count == 3);
        Check("les champs hors emplacement sont ignorés", !s.Equipment.Any(p => p.Slot == "ArmorLevel"));
        var w = s.Equipment.First(p => p.Slot == "WeaponSlot");
        Check("bonus lus sur l'exemplaire équipé", w.BonusSource == "item_instance");
        Check("bonus nul écarté", w.Bonuses.Count == 1 && w.Bonuses[0].Value == 30f);
        Check("type de modification conservé", w.Bonuses[0].Modification == "AddToBase");
        Check("durabilité lue", w.Durability == 90f && w.MaxDurability == 100f);
        Check("palier légendaire lu", w.LegendaryTier == 2);
        Check("infusion lue", w.InfusionGuid == 5);
        Check("modificateurs d'arme lus", w.StatMods.Count == 1 && w.StatMods[0].Power == 0.4f);
        var c = s.Equipment.First(p => p.Slot == "ArmorChestSlot");
        Check("repli sur le modèle de l'objet signalé", c.BonusSource == "item_prefab" && c.Bonuses.Count == 1);
        var cloak = s.Equipment.First(p => p.Slot == "CloakSlot");
        Check("emplacement vide distingué d'un emplacement illisible", cloak.BonusSource == "empty_slot" && cloak.Guid == 0);

        Console.WriteLine("Buffs");
        Check("buff vide ignoré", s.Buffs.Count == 2);
        var p1 = s.Buffs.First(b => b.Guid == 201);
        Check("temps restant calculé", p1.RemainingSeconds == 120f && p1.TotalSeconds == 600f && !p1.Permanent);
        Check("apport du buff lu", p1.Bonuses.Count == 1 && p1.Bonuses[0].Value == 8f);
        var p2 = s.Buffs.First(b => b.Guid == 202);
        Check("durée négative traitée comme permanente, pas comme expirée", p2.Permanent && p2.RemainingSeconds == null);

        Console.WriteLine("Sorts");
        Check("deux emplacements de sort", s.Spells.Count == 2);
        Check("joyau lu", s.Spells[0].ModsReadable && s.Spells[0].Mods.Count == 1 && s.Spells[0].Mods[0].Power == 0.75f);
        Check("modificateurs illisibles marqués inconnus, pas « aucun »", !s.Spells[1].ModsReadable && s.Spells[1].Mods.Count == 0);

        Console.WriteLine("Sérialisation");
        var json = JsonSerializer.Serialize(s, Wire.Json);
        Check("le snapshot se sérialise", json.Contains("\"physicalPower\"", StringComparison.OrdinalIgnoreCase) || json.Contains("PhysicalPower"));
        Check("version de format 2", s.SchemaVersion == 2);

        Console.WriteLine(failed == 0 ? "\nTOUT PASSE" : "\n" + failed + " ECHEC(S)");
        return failed == 0 ? 0 : 1;
    }
}
