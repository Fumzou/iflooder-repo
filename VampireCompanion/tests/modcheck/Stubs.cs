// Stand-ins for the V Rising / Unity types the collector uses, shaped from the signatures
// observed in Eclipse and Bloodcraft. Compiling Character.cs against these proves the
// collector's own logic; it does not prove the real assemblies match these shapes.
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

    public struct ModifiableFloat { public float _Value; public static ModifiableFloat Of(float v) => new ModifiableFloat { _Value = v }; }
    public struct ModifiableBool { public bool _Value; }
    public struct NetworkedEntity { public Entity _Entity; }

    // A handful of real names plus the single-letter field the shipped assemblies actually
    // carry for the spell crit chance, so the obfuscation path is exercised.
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

    public struct Durability { public float Value; public float MaxDurability; }
    public struct LifeTime { public float Duration; }
    public struct Age { public float Value; }

    public enum UnitStatType { PhysicalPower, SpellPower, MovementSpeed, SpellCriticalStrikeChance }
    public enum ModificationType { AddToBase, Multiply }
    public struct ModifyUnitStatBuff_DOTS
    {
        public UnitStatType StatType; public ModificationType ModificationType;
        public float Value; public float Modifier;
    }

    public struct SpellMod { public PrefabGUID Id; public float Power; }
    public struct SpellModSet
    {
        public SpellMod Mod0; public SpellMod Mod1;
        public int Count;
        public SpellMod this[int i] => i == 0 ? Mod0 : Mod1;
    }
    public struct SpellModSetComponent { public SpellModSet SpellMods; }
    public struct LegendaryItemInstance { public int TierIndex; }
    public struct LegendaryItemSpellModSetComponent { public SpellModSet StatMods; public SpellModSet AbilityMods0; }
    public struct AbilityGroupSlotBuffer { public PrefabGUID BaseAbilityGroupOnSlot; public NetworkedEntity GroupSlotEntity; }
}

namespace ProjectM.Shared
{
    using Stunlock.Core;
    using Unity.Entities;
    public struct BuffBuffer { public PrefabGUID PrefabGuid; public Entity Entity; }
}
