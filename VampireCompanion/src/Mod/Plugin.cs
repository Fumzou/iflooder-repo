using BepInEx;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using ProjectM;
using ProjectM.UI;
using UnityEngine;

namespace VampireCompanion;

[BepInPlugin("fr.tristan.vampirecompanion", "Vampire Companion", "0.4.0")]
public sealed class Plugin : BasePlugin
{
    internal static Plugin Instance = null!;
    internal static Observer? Observer;
    Harmony? harmony;
    CompanionUpdate? driver;
    public override void Load()
    {
        Instance = this;
        if (Application.productName == "VRisingServer") { Log.LogWarning("Client uniquement."); return; }
        var directory = Config.Bind("Companion", "DataDirectory", Wire.DefaultDirectory,
            "Dossier local partagé avec la passerelle MCP.").Value;
        var seconds = Config.Bind("Companion", "PollSeconds", 2f,
            "Intervalle de lecture (minimum 1 seconde).").Value;
        Observer = new Observer(directory, Math.Max(1, seconds));
        driver = AddComponent<CompanionUpdate>();
        harmony = new Harmony("fr.tristan.vampirecompanion");
        // Each optional collector is isolated: one missing UI method must not disable all data.
        foreach (var patch in new[] { typeof(GameTick), typeof(Disconnect), typeof(InventoryTick), typeof(WorkstationTick), typeof(RefinementTick) })
        {
            try { harmony.CreateClassProcessor(patch).Patch(); }
            catch (Exception ex) { Observer.Report(patch.Name, ex); }
        }
        Log.LogInfo("Vampire Companion chargé. Lecture locale uniquement. Données : " + directory);
    }
    public override bool Unload()
    {
        Observer?.Disconnect(); harmony?.UnpatchSelf(); Observer = null;
        if (driver != null) UnityEngine.Object.Destroy(driver);
        return true;
    }
    internal static void Safe(string name, Action action)
    {
        try { action(); } catch (Exception ex) { Observer?.Report(name, ex); }
    }
}

public sealed class CompanionUpdate : MonoBehaviour
{
    public CompanionUpdate(IntPtr pointer) : base(pointer) { }
    public void Update() => Plugin.Safe("poll", () => Plugin.Observer?.Pump());
}

[HarmonyPatch(typeof(GameDataManager), nameof(GameDataManager.OnUpdate))]
static class GameTick
{
    static void Postfix(GameDataManager __instance) => Plugin.Safe("game", () =>
    { if (__instance.GameDataInitialized && __instance.World.IsCreated) Plugin.Observer?.Tick(__instance.World); });
}
[HarmonyPatch(typeof(ClientBootstrapSystem), nameof(ClientBootstrapSystem.OnDestroy))]
static class Disconnect
{
    static void Prefix() => Plugin.Safe("disconnect", () => Plugin.Observer?.Disconnect());
}
[HarmonyPatch(typeof(InventorySubMenuMapper), nameof(InventorySubMenuMapper.UpdateInner))]
static class InventoryTick
{
    static void Postfix(InventorySubMenuMapper __instance, Unity.Entities.Entity menuEntity, InventorySubMenu menu)
        => Plugin.Safe("inventory_ui", () =>
        {
            if (menu != null && menu.isActiveAndEnabled &&
                __instance.EntityManager.HasComponent<InventorySubMenuMapper.InventoryTarget>(menuEntity))
            {
                var target = __instance.EntityManager.GetComponentData<InventorySubMenuMapper.InventoryTarget>(menuEntity).Target;
                Plugin.Observer?.VisitInventory(__instance.World, target);
            }
        });
}
[HarmonyPatch(typeof(WorkstationSubMenuMapper), nameof(WorkstationSubMenuMapper.OnUpdate))]
static class WorkstationTick
{
    static void Postfix(WorkstationSubMenuMapper __instance) => Plugin.Safe("workstation_ui", () =>
    {
        if (__instance._Menu != null && __instance._Menu.isActiveAndEnabled)
            Plugin.Observer?.VisitWorkstation(__instance.World, __instance.GetTargetWorkstationEntity(), __instance);
    });
}
[HarmonyPatch(typeof(RefinementstationSubMenuMapper), nameof(RefinementstationSubMenuMapper.OnUpdate))]
static class RefinementTick
{
    static void Postfix(RefinementstationSubMenuMapper __instance) => Plugin.Safe("refinement_ui", () =>
    {
        if (__instance._Menu != null && __instance._Menu.isActiveAndEnabled &&
            __instance.EntityManager.Exists(__instance._MenuEntity) &&
            __instance.EntityManager.HasComponent<RefinementstationSubMenuMapper.RefinementstationTarget>(__instance._MenuEntity))
        {
            var target = __instance.EntityManager.GetComponentData<RefinementstationSubMenuMapper.RefinementstationTarget>(__instance._MenuEntity).Target;
            Plugin.Observer?.VisitRefinement(__instance.World, target, __instance);
        }
    });
}
