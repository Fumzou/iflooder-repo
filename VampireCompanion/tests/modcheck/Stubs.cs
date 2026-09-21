// Stand-ins for the V Rising / Unity types the collector uses.
//
// Namespaces, field names and field widths below were read out of the real
// VampireReferenceAssemblies 1.1.12-r99041-b2 with MetadataLoadContext, not guessed.
// Compiling Character.cs against these proves the collector's own logic; only building
// src/Mod against the reference assemblies proves the game really has these members.
//
// Three stubs stay deliberately synthetic, because they exist to exercise a code path
// rather than to mirror a component; each one says so where it is declared.
using System.Collections.Generic;

namespace Unity.Entities
{
    public struct Entity
    {
        public int Index; public int Version;
        public static Entity Null => new Entity { Index = 0, Version = 0 };
        public override string ToString() => Index + ":" + Version;
    }
    public sealed class DynamicBuffer<T>
    {
        readonly List<T> items;
        public DynamicBuffer(List<T> items) => this.items = items;
        public int Length => items.Count;
        public T this[int i] => items[i];
    }
    public sealed class EntityManager
    {
        readonly Dictionary<(int, System.Type), object> components = new();
        readonly HashSet<int> alive = new();
        public void SetAlive(Entity e) => alive.Add(e.Index);
        public void Set<T>(Entity e, T value) { alive.Add(e.Index); components[(e.Index, typeof(T))] = value!; }
        public void SetBuffer<T>(Entity e, List<T> value) { alive.Add(e.Index); components[(e.Index, typeof(DynamicBuffer<T>))] = new DynamicBuffer<T>(value); }
        public bool Exists(Entity e) => alive.Contains(e.Index);
        public bool HasComponent<T>(Entity e) =>
            components.ContainsKey((e.Index, typeof(T))) || components.ContainsKey((e.Index, typeof(DynamicBuffer<T>)));
        public T GetComponentData<T>(Entity e) => (T)components[(e.Index, typeof(T))];
        public DynamicBuffer<T> GetBuffer<T>(Entity e, bool readOnly) => (DynamicBuffer<T>)components[(e.Index, typeof(DynamicBuffer<T>))];
    }
}

namespace Stunlock.Core
{
    public struct PrefabGUID
    {
        public int GuidHash;
        public PrefabGUID(int hash) => GuidHash = hash;
    }
}

namespace ProjectM
{
    using Stunlock.Core;
    using Unity.Entities;

    // The real wrappers carry a public _Value field plus a Value property over it; the
    // collector reflects on the field, which is why the field is what matters here.
    public struct ModifiableFloat
    {
        public float _Value;
        public float Value => _Value;
        public static ModifiableFloat Of(float v) => new ModifiableFloat { _Value = v };
    }
    public struct ModifiableInt { public int _Value; public int Value => _Value; }
    public struct ModifiableBool { public bool _Value; public bool Value => _Value; }
    public struct NetworkedEntity { public Entity _Entity; public bool _WaitingForSync; }

    // SYNTHETIC, on purpose. The real ProjectM.UnitStats of 1.1.12 carries 15 fields —
    // PhysicalPower, SpellPower, ResourcePower, SiegePower, PhysicalResistance,
    // SpellResistance, FireResistance, PassiveHealthRegen, CCReduction, HealthRecovery,
    // DamageReduction, HealingReceived, ReducedBloodDrain, BloodDrainMultiplier,
    // CorruptionDamageReduction — and no single-letter field: the crit, speed and
    // DamageVs stats live on ProjectM.Shared.VampireSpecificAttributes instead.
    // The shape below is kept because it is what exercises the collector's paths: an
    // obfuscated name with no label, a stat sitting at zero, a bool, a bare int and a
    // non-numeric field. Replacing it with the real 15 would drop those five checks.
    public struct UnitStats
    {
        public ModifiableFloat PhysicalPower;
        public ModifiableFloat SpellPower;
        public ModifiableFloat PhysicalCriticalStrikeChance;
        public ModifiableFloat PhysicalCriticalStrikeDamage;
        public ModifiableFloat a;
        public ModifiableFloat MovementSpeed;
        public ModifiableBool ImmuneToHazards;
        public int InventorySlots;
        public string NotANumber;
    }

    // SYNTHETIC in one respect: the real ProjectM.Blood does expose a maximum, as
    // MaxBlood (ModifiableFloat), so in game the collector will publish MaxAmount. No
    // Max field is declared here so the "nothing invented when the game exposes no
    // maximum" check keeps testing that path.
    public struct Blood { public PrefabGUID BloodType; public float Quality; public float Value; }

    public struct EquipmentSlot { public PrefabGUID SlotId; public NetworkedEntity SlotEntity; }
    public struct Equipment
    {
        public EquipmentSlot WeaponSlot;
        public EquipmentSlot ArmorChestSlot;
        public EquipmentSlot CloakSlot;
        public ModifiableFloat ArmorLevel;
        public ModifiableFloat WeaponLevel;
        public ModifiableFloat SpellLevel;
    }

    public struct LifeTime { public float Duration; }
    public struct Age { public float Value; }

    // Trimmed to the members the collector reads. The real UnitStatType has 83 values and
    // ModifyUnitStatBuff_DOTS 10 fields; the extra ones change nothing the check covers.
    public enum UnitStatType { PhysicalPower, SpellPower, MovementSpeed, SpellCriticalStrikeChance }
    public enum ModificationType { Set, SetMin, SetMax, Add, Multiply, MultiplyBaseAdd, AddToBase, BitwiseOR, BitwiseNOT }
    public struct ModifyUnitStatBuff_DOTS
    {
        public UnitStatType StatType; public ModificationType ModificationType;
        public float Value; public float Modifier;
    }

    public struct AbilityGroupSlotBuffer { public PrefabGUID BaseAbilityGroupOnSlot; public NetworkedEntity GroupSlotEntity; }

    public struct BuffBuffer { public PrefabGUID PrefabGuid; public Unity.Entities.Entity Entity; }
}

namespace ProjectM.Shared
{
    using Stunlock.Core;

    public struct Durability { public float Value; public float MaxDurability; }

    public struct SpellMod { public PrefabGUID Id; public float Power; }
    public struct SpellModSet
    {
        public SpellMod Mod0; public SpellMod Mod1;
        public byte Count;
        public SpellMod this[int i] => i == 0 ? Mod0 : Mod1;
    }
    public struct SpellModSetComponent { public SpellModSet SpellMods; }
    public struct LegendaryItemInstance { public byte TierIndex; }
    public struct LegendaryItemSpellModSetComponent { public SpellModSet StatMods; public SpellModSet AbilityMods0; }
}
