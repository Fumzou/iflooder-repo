using System.Reflection;
using ProjectM;
using ProjectM.Shared;
using Stunlock.Core;
using Unity.Entities;

namespace VampireCompanion;

// Character state: final stats, blood, equipment, active buffs and spell slots.
//
// The game already folds gear, blood and buffs into UnitStats, so that block is published
// as the character's final stats, and every per-source contribution is published beside it
// as an input. The two are never summed: adding a ring's bonus to the final block would
// count it twice. Damage is not computed here — the mod publishes what it reads.
//
// Field names are discovered on the components themselves rather than hard-coded, because
// several of them are obfuscated in the shipped assemblies and change between builds. An
// unknown name is published raw with a null label instead of being renamed to a guess.
internal sealed partial class Observer
{
    const BindingFlags Members = BindingFlags.Public | BindingFlags.Instance;

    void ReadStats()
    {
        if (!em.HasComponent<UnitStats>(character))
            throw new InvalidOperationException("Le composant UnitStats n'est pas répliqué sur le personnage.");
        var stats = em.GetComponentData<UnitStats>(character);
        var values = new List<StatValue>();
        var unreadable = new List<string>();
        foreach (var field in typeof(UnitStats).GetFields(Members))
        {
            if (Number(field.GetValue(stats), out var value))
                values.Add(new StatValue(field.Name, Labels.Stat(field.Name), value));
            else unreadable.Add(field.Name);
        }
        if (values.Count == 0)
            throw new InvalidOperationException("Aucun champ numérique lisible sur UnitStats.");
        snapshot.Stats = new CharacterStats(
            values.OrderBy(v => v.Field, StringComparer.Ordinal).ToList(), unreadable);
    }

    void ReadBlood()
    {
        if (!em.HasComponent<Blood>(character))
            throw new InvalidOperationException("Le composant Blood n'est pas répliqué sur le personnage.");
        var blood = em.GetComponentData<Blood>(character);
        // A maximum is published only if the component carries one: 100 is a convention.
        float? max = null;
        foreach (var field in typeof(Blood).GetFields(Members))
            if (field.Name.IndexOf("Max", StringComparison.OrdinalIgnoreCase) >= 0 &&
                Number(field.GetValue(blood), out var candidate)) max = candidate;
        snapshot.Blood = new BloodState(blood.BloodType.GuidHash, Name(blood.BloodType),
            float.IsFinite(blood.Quality) ? (float?)blood.Quality : null,
            float.IsFinite(blood.Value) ? (float?)blood.Value : null, max);
    }

    void ReadEquipment()
    {
        if (!em.HasComponent<Equipment>(character))
            throw new InvalidOperationException("Le composant Equipment n'est pas répliqué sur le personnage.");
        var equipment = em.GetComponentData<Equipment>(character);
        var pieces = new List<EquipmentPiece>();
        // Every field carrying both a SlotId and a SlotEntity is an equipment slot, whatever
        // it is called. Slots the game renames or adds are picked up without a code change.
        foreach (var field in typeof(Equipment).GetFields(Members))
        {
            var slot = field.GetValue(equipment);
            if (slot == null) continue;
            var type = slot.GetType();
            if (type.GetField("SlotId", Members)?.GetValue(slot) is not PrefabGUID guid) continue;
            var item = Networked(type.GetField("SlotEntity", Members)?.GetValue(slot));
            pieces.Add(ReadPiece(field.Name, guid, item));
        }
        if (pieces.Count == 0)
            throw new InvalidOperationException("Aucun emplacement d'équipement lisible sur Equipment.");
        snapshot.Equipment = pieces;
    }

    EquipmentPiece ReadPiece(string slot, PrefabGUID guid, Entity item)
    {
        float? durability = null, maxDurability = null;
        int? tier = null, infusion = null;
        string? infusionName = null;
        var statMods = new List<Modifier>();
        if (guid.GuidHash != 0 && em.Exists(item))
        {
            if (em.HasComponent<Durability>(item))
            {
                var d = em.GetComponentData<Durability>(item);
                if (float.IsFinite(d.Value)) durability = d.Value;
                if (float.IsFinite(d.MaxDurability)) maxDurability = d.MaxDurability;
            }
            if (em.HasComponent<LegendaryItemInstance>(item))
                tier = em.GetComponentData<LegendaryItemInstance>(item).TierIndex;
            if (em.HasComponent<LegendaryItemSpellModSetComponent>(item))
            {
                var set = em.GetComponentData<LegendaryItemSpellModSetComponent>(item);
                statMods = Mods(set.StatMods);
                var school = set.AbilityMods0.Mod0.Id;
                if (school.GuidHash != 0) { infusion = school.GuidHash; infusionName = Name(school); }
            }
        }
        var bonuses = Contributions(item, guid, out var source);
        return new EquipmentPiece(slot, guid.GuidHash, Name(guid), durability, maxDurability,
            tier, infusion, infusionName, bonuses, source, statMods);
    }

    void ReadBuffs()
    {
        if (!em.HasComponent<BuffBuffer>(character))
            throw new InvalidOperationException("Le tampon BuffBuffer n'est pas répliqué sur le personnage.");
        var buffer = em.GetBuffer<BuffBuffer>(character, true);
        var buffs = new List<ActiveBuff>();
        for (var i = 0; i < buffer.Length; i++)
        {
            var entry = buffer[i];
            if (entry.PrefabGuid.GuidHash == 0) continue;
            var buffEntity = entry.Entity;
            float? total = null, remaining = null;
            var permanent = true;
            var bonuses = new List<StatBonus>();
            if (em.Exists(buffEntity))
            {
                if (em.HasComponent<LifeTime>(buffEntity))
                {
                    // A duration of zero or less marks a buff without expiry, not one about
                    // to end, so it is reported as permanent rather than as "0 seconde".
                    var duration = em.GetComponentData<LifeTime>(buffEntity).Duration;
                    if (float.IsFinite(duration) && duration > 0) { total = duration; permanent = false; }
                }
                if (total.HasValue && em.HasComponent<Age>(buffEntity))
                {
                    var age = em.GetComponentData<Age>(buffEntity).Value;
                    if (float.IsFinite(age) && age >= 0) remaining = Math.Max(0f, total.Value - age);
                }
                if (em.HasComponent<ModifyUnitStatBuff_DOTS>(buffEntity)) bonuses = Bonuses(buffEntity);
            }
            buffs.Add(new ActiveBuff(entry.PrefabGuid.GuidHash, Name(entry.PrefabGuid),
                total, remaining, permanent, bonuses));
        }
        snapshot.Buffs = buffs;
    }

    void ReadSpells()
    {
        if (!em.HasComponent<AbilityGroupSlotBuffer>(character))
            throw new InvalidOperationException("Le tampon AbilityGroupSlotBuffer n'est pas répliqué sur le personnage.");
        var slots = em.GetBuffer<AbilityGroupSlotBuffer>(character, true);
        var list = new List<SpellSlot>();
        for (var i = 0; i < slots.Length; i++)
        {
            var entry = slots[i];
            var slotEntity = Networked(entry.GroupSlotEntity);
            // An unreadable mod set means unknown, never "this spell has no jewel".
            var readable = em.Exists(slotEntity) && em.HasComponent<SpellModSetComponent>(slotEntity);
            var mods = readable
                ? Mods(em.GetComponentData<SpellModSetComponent>(slotEntity).SpellMods)
                : new List<Modifier>();
            list.Add(new SpellSlot(i, entry.BaseAbilityGroupOnSlot.GuidHash,
                Name(entry.BaseAbilityGroupOnSlot), readable, mods));
        }
        snapshot.Spells = list;
    }

    // Contributions are read from the equipped instance when it carries them, and only
    // otherwise from the item's prefab, which holds base values and ignores anything the
    // instance gained. The caller is told which of the two was used.
    List<StatBonus> Contributions(Entity item, PrefabGUID guid, out string source)
    {
        if (guid.GuidHash == 0) { source = "empty_slot"; return new List<StatBonus>(); }
        if (em.Exists(item) && em.HasComponent<ModifyUnitStatBuff_DOTS>(item))
        { source = "item_instance"; return Bonuses(item); }
        if (prefabs._PrefabGuidToEntityMap.TryGetValue(guid, out var prefab) && em.Exists(prefab) &&
            em.HasComponent<ModifyUnitStatBuff_DOTS>(prefab))
        { source = "item_prefab"; return Bonuses(prefab); }
        source = "unavailable";
        return new List<StatBonus>();
    }

    List<StatBonus> Bonuses(Entity holder)
    {
        var list = new List<StatBonus>();
        var buffer = em.GetBuffer<ModifyUnitStatBuff_DOTS>(holder, true);
        for (var i = 0; i < buffer.Length; i++)
        {
            var entry = buffer[i];
            if (!float.IsFinite(entry.Value) || entry.Value == 0f) continue;
            var stat = entry.StatType.ToString();
            list.Add(new StatBonus(stat, Labels.Stat(stat), entry.Value, entry.ModificationType.ToString()));
        }
        return list;
    }

    List<Modifier> Mods(SpellModSet set)
    {
        var list = new List<Modifier>();
        for (var i = 0; i < set.Count && i < 8; i++)
        {
            var mod = set[i];
            if (mod.Id.GuidHash == 0) continue;
            list.Add(new Modifier(mod.Id.GuidHash, Name(mod.Id),
                float.IsFinite(mod.Power) ? mod.Power : 0f));
        }
        return list;
    }

    // Stat wrappers keep their number in a _Value field; plain numbers are taken as they are.
    static bool Number(object? boxed, out float value)
    {
        value = 0f;
        switch (boxed)
        {
            case null: return false;
            case float f: value = f; break;
            case double d: value = (float)d; break;
            case int i: value = i; break;
            case bool b: value = b ? 1f : 0f; break;
            default:
                var inner = boxed.GetType().GetField("_Value", Members);
                return inner != null && Number(inner.GetValue(boxed), out value);
        }
        return float.IsFinite(value);
    }

    static Entity Networked(object? value)
    {
        if (value is Entity direct) return direct;
        var inner = value?.GetType().GetField("_Entity", Members);
        return inner?.GetValue(value) is Entity entity ? entity : Entity.Null;
    }
}
