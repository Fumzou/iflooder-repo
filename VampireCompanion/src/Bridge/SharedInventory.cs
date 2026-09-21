namespace VampireCompanion;

public sealed partial class CompanionTools
{
    // Membership of individual chests is not reliably replicated. Never add their
    // quantities to an aggregate that might already contain them. Keep raw locations
    // available for searches, but exclude all non-player containers from calculations.
    static IEnumerable<Stock> CountedStocks(Snapshot s)
    {
        if (s.SharedInventory is not { } shared) return s.Inventories;
        var aggregate = new Stock("shared:" + shared.ManagerId, shared.ManagerId,
            "Inventaire partagé du château", "shared_castle", shared.ObservedAt,
            shared.Accessible, shared.Items);
        return s.Inventories.Where(i => i.Kind == "player").Append(aggregate);
    }

    static object Accounting(Snapshot s) => new {
        mode = s.SharedInventory == null ? "observed_containers" : "player_plus_shared",
        excludedContainers = s.SharedInventory == null ? 0 : s.Inventories.Count(i => i.Kind != "player"),
        reason = s.SharedInventory == null ? null :
            "Pour éviter les doubles comptes, les calculs utilisent le sac et l'inventaire partagé. Tous les autres contenants, même les machines, sont exclus des totaux ; leur détail reste consultable."
    };

    static object SharedView(Snapshot s, string query, int limit, int offset, DateTimeOffset now)
    {
        var shared = s.SharedInventory;
        return new {
            status = s.SharedInventoryStatus,
            availableNow = shared != null && Live(s, shared.Accessible, shared.ObservedAt, now),
            state = shared == null ? "unknown" : State(s, shared.Accessible, shared.ObservedAt, now),
            managerId = shared?.ManagerId, observedAt = shared?.ObservedAt,
            instanceCount = shared?.InstanceCount,
            items = Page((shared?.Items ?? new List<Item>()).Where(i => Match(i.Name, query) || i.Guid.ToString() == query), limit, offset),
            accounting = Accounting(s),
            coverage = "Inventaire partagé transmis au personnage local, sans détail par coffre. Si indisponible, entrer sur le territoire et ouvrir le menu construction ; consulter le statut de collecte."
        };
    }
}
