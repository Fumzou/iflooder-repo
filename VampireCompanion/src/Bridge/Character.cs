using System.Text.Json;

namespace VampireCompanion;

// Views over the character's own state.
//
// The rule that governs this whole file: UnitStats is the final block the game computed,
// and every bonus published beside it is one of the inputs that produced it. They are
// presented next to each other and never summed, because adding a ring's bonus to the
// final block counts that ring twice. explain_stat is the one place the two meet, and it
// reports the remainder instead of pretending the sum is the answer.
public sealed partial class CompanionTools
{
    static string CharacterState(Snapshot s, DateTimeOffset now) => Fresh(s, now) ? "observed_now" : "last_observed";

    static string? StatCollected(Snapshot s) =>
        s.Capabilities.TryGetValue("stats", out var state) ? state : null;

    // Stats carrying a value come first so a short page is the useful one, but nothing is
    // dropped: a stat really sitting at zero is an observation, not a gap.
    static IEnumerable<StatValue> SortedStats(Snapshot s, string query) =>
        (s.Stats?.Values ?? new List<StatValue>())
            .Where(v => Match(v.Field, query) || (v.Label != null && Match(v.Label, query)))
            .OrderByDescending(v => v.Value != 0f)
            .ThenBy(v => v.Label ?? ("zzz" + v.Field), StringComparer.OrdinalIgnoreCase);

    static object BloodView(Snapshot s) => s.Blood == null ? new {
        available = false,
        reason = "Le sang n'a pas été lu. Vérifie l'état 'blood' dans get_status."
    } : (object)new {
        available = true,
        type = s.Blood.TypeName, typeGuid = s.Blood.TypeGuid,
        qualityPercent = s.Blood.Quality, amount = s.Blood.Amount, maxAmount = s.Blood.MaxAmount,
        amountPercent = s.Blood.MaxAmount is > 0 && s.Blood.Amount.HasValue
            ? Math.Round(100.0 * s.Blood.Amount.Value / s.Blood.MaxAmount.Value, 1) : (double?)null,
        note = s.Blood.MaxAmount == null
            ? "Le client n'expose pas de réserve maximale ; aucun pourcentage de réserve n'est déduit."
            : null,
        bonusesNote = "Les bonus du sang sont appliqués par des buffs : ils apparaissent dans get_buffs et sont déjà inclus dans les statistiques finales."
    };

    static object CharacterView(Snapshot s, string query, int limit, int offset, DateTimeOffset now)
    {
        var all = SortedStats(s, query).ToList();
        return new {
            state = CharacterState(s, now),
            s.Player,
            blood = BloodView(s),
            statsCollected = StatCollected(s),
            stats = Page(all.Select(v => new { v.Field, v.Label, v.Value }), limit, offset),
            unreadableStatFields = s.Stats?.Unreadable ?? new List<string>(),
            equipment = new {
                slots = s.Equipment.Count,
                filled = s.Equipment.Count(p => p.Guid != 0),
                bonusesUnavailable = s.Equipment.Count(p => p.BonusSource == "unavailable"),
                legendaries = s.Equipment.Count(p => p.LegendaryTier.HasValue) },
            buffs = new {
                active = s.Buffs.Count,
                temporary = s.Buffs.Count(b => !b.Permanent),
                withStatBonus = s.Buffs.Count(b => b.Bonuses.Count > 0) },
            spells = s.Spells.Select(sp => new { sp.Index, sp.GroupName, jewels = sp.ModsReadable ? sp.Mods.Count : (int?)null }),
            reading = "Ces statistiques sont le bloc final calculé par le jeu : les bonus de l'équipement, du sang et des buffs y sont déjà inclus. Ne jamais les additionner une seconde fois. Utilise explain_stat pour voir l'origine d'une statistique."
        };
    }

    static object EquipmentView(Snapshot s, string query, int limit, int offset, DateTimeOffset now) => new {
        state = CharacterState(s, now),
        slots = Page(s.Equipment
            .Where(p => Match(p.Slot, query) || Match(p.Name, query) || p.Guid.ToString() == query)
            .Select(p => new {
                p.Slot, p.Guid, item = p.Name, equipped = p.Guid != 0,
                p.Durability, p.MaxDurability,
                durabilityPercent = p.MaxDurability is > 0 && p.Durability.HasValue
                    ? Math.Round(100.0 * p.Durability.Value / p.MaxDurability.Value, 1) : (double?)null,
                legendaryTier = p.LegendaryTier, infusion = p.InfusionName,
                bonusSource = p.BonusSource,
                bonusesReliable = p.BonusSource == "item_instance",
                bonuses = p.Bonuses.Select(b => new { b.Stat, b.Label, b.Value, b.Modification }),
                statMods = p.StatMods.Select(m => new { m.Name, m.Power }),
                note = p.BonusSource switch {
                    "item_prefab" => "Bonus lus sur le modèle de l'objet : ils ignorent ce que cet exemplaire a gagné (qualité d'artisanat, mods).",
                    "unavailable" => "Bonus non exposés pour cet objet.",
                    "empty_slot" => "Emplacement vide.",
                    _ => null } }), limit, offset),
        spells = s.Spells.Select(sp => new {
            sp.Index, spell = sp.GroupName, sp.GroupGuid,
            jewelsReadable = sp.ModsReadable,
            jewels = sp.Mods.Select(m => new { m.Name, m.Power }),
            note = sp.ModsReadable ? null : "Les modificateurs de ce sort ne sont pas exposés : inconnu, et non « aucun joyau »." }),
        warning = "Ces bonus sont les apports déclarés par chaque pièce. Ils sont déjà compris dans les statistiques finales de get_character et ne doivent pas leur être ajoutés."
    };

    static object BuffView(Snapshot s, string query, int limit, int offset, DateTimeOffset now) => new {
        state = CharacterState(s, now),
        collected = s.Capabilities.TryGetValue("buffs", out var status) ? status : null,
        buffs = Page(s.Buffs
            .Where(b => Match(b.Name, query) || b.Guid.ToString() == query)
            .OrderBy(b => b.Permanent).ThenBy(b => b.RemainingSeconds ?? float.MaxValue)
            .Select(b => new {
                b.Guid, name = b.Name, b.Permanent,
                totalSeconds = b.TotalSeconds, remainingSeconds = b.RemainingSeconds,
                bonuses = b.Bonuses.Select(x => new { x.Stat, x.Label, x.Value, x.Modification }) }), limit, offset),
        warning = "Le temps restant est calculé à l'instant de la lecture ; il continue de s'écouler. Les bonus listés sont déjà inclus dans les statistiques finales."
    };

    // Puts one stat's final value next to every contribution observed for it, and states
    // the remainder rather than claiming the parts explain the whole.
    static object ExplainStat(Snapshot s, string query)
    {
        if (string.IsNullOrWhiteSpace(query))
            throw new ArgumentException("query doit nommer une statistique, par exemple PhysicalPower ou « puissance physique ».");
        var gear = s.Equipment.SelectMany(p => p.Bonuses.Select(b => new { piece = p, bonus = b })).ToList();
        var buffs = s.Buffs.SelectMany(b => b.Bonuses.Select(x => new { buff = b, bonus = x })).ToList();
        var names = gear.Select(x => x.bonus.Stat).Concat(buffs.Select(x => x.bonus.Stat)).Distinct().ToList();
        var canonical = names.FirstOrDefault(n => string.Equals(n, query, StringComparison.OrdinalIgnoreCase))
            ?? names.FirstOrDefault(n => Match(n, query) || Match(Labels.Stat(n) ?? "", query));
        var final = (s.Stats?.Values ?? new List<StatValue>())
            .FirstOrDefault(v => string.Equals(v.Field, canonical ?? query, StringComparison.OrdinalIgnoreCase))
            ?? SortedStats(s, query).FirstOrDefault();
        canonical ??= final?.Field ?? query;
        var contributions = gear.Where(x => string.Equals(x.bonus.Stat, canonical, StringComparison.OrdinalIgnoreCase))
            .Select(x => new { source = "équipement", origin = x.piece.Slot, name = x.piece.Name,
                x.bonus.Value, x.bonus.Modification, reliable = x.piece.BonusSource == "item_instance" })
            .Concat(buffs.Where(x => string.Equals(x.bonus.Stat, canonical, StringComparison.OrdinalIgnoreCase))
                .Select(x => new { source = "buff", origin = x.buff.Permanent ? "permanent" : "temporaire",
                    name = x.buff.Name, x.bonus.Value, x.bonus.Modification, reliable = true }))
            .ToList();
        var additive = contributions.All(c => c.Modification == "AddToBase") && contributions.Count > 0;
        double? sum = additive ? contributions.Sum(c => (double)c.Value) : null;
        var linked = final != null && string.Equals(final.Field, canonical, StringComparison.OrdinalIgnoreCase);
        return new {
            stat = canonical, label = Labels.Stat(canonical) ?? final?.Label,
            finalValue = linked ? final!.Value : (float?)null,
            finalValueField = final?.Field,
            contributions, contributionCount = contributions.Count,
            additiveOnly = additive, sumOfContributions = sum,
            unexplainedRemainder = linked && sum.HasValue ? Math.Round(final!.Value - sum.Value, 3) : (double?)null,
            notes = new[] {
                !linked ? "Aucun champ du bloc final ne porte ce nom. Plusieurs champs sont obfusqués dans les assemblies du jeu : le lien avec ces apports n'est pas confirmé." : null,
                !additive && contributions.Count > 0 ? "Les apports ne sont pas tous additifs : aucune somme n'est calculée, car mélanger additif et multiplicatif donnerait un faux total." : null,
                contributions.Count == 0 ? "Aucun apport observé pour cette statistique. La valeur finale peut venir de la base du personnage, d'un set ou d'une source non exposée." : null,
                linked && sum.HasValue ? "Le reste correspond à la base du personnage et à toute source non exposée ; ce n'est pas une erreur de lecture." : null,
                s.Equipment.Any(p => p.BonusSource == "item_prefab") ? "Certains apports viennent du modèle de l'objet et non de l'exemplaire équipé." : null
            }.Where(x => x != null)
        };
    }

    // Damage the client cannot compute on its own. The power, crit chance and crit damage
    // are read from the game; the ability coefficient and the cast interval are not exposed
    // to the client, so a number is produced only for the ones the caller supplies, and the
    // result is always labelled an estimate. Target mitigation is deliberately absent: the
    // formula is not exposed, and guessing it would turn an estimate into a fiction.
    static object Damage(Snapshot s, JsonElement args)
    {
        var kind = Text(args, "kind").ToLowerInvariant();
        if (kind != "physical" && kind != "spell")
            throw new ArgumentException("kind doit valoir 'physical' ou 'spell'.");
        var values = s.Stats?.Values ?? new List<StatValue>();
        if (values.Count == 0)
            throw new InvalidOperationException("Aucune statistique lue. Vérifie l'état 'stats' dans get_status.");
        float? Stat(string name) => values.FirstOrDefault(v =>
            string.Equals(v.Field, name, StringComparison.OrdinalIgnoreCase))?.Value;
        var powerField = kind == "physical" ? "PhysicalPower" : "SpellPower";
        var chanceField = kind == "physical" ? "PhysicalCriticalStrikeChance" : "SpellCriticalStrikeChance";
        var damageField = kind == "physical" ? "PhysicalCriticalStrikeDamage" : "SpellCriticalStrikeDamage";
        var power = Stat(powerField);
        var chance = Stat(chanceField);
        var critDamage = Stat(damageField);
        var assumptions = new List<string>();
        var missing = new List<string>();
        if (power == null) missing.Add(powerField + " : non exposé sous ce nom (champ possiblement obfusqué).");
        if (chance == null) missing.Add(chanceField + " : non exposé sous ce nom.");
        if (critDamage == null) missing.Add(damageField + " : non exposé sous ce nom.");

        double? rate = chance;
        if (rate > 1) { rate /= 100.0; assumptions.Add("Chance critique lue au-dessus de 1 : interprétée comme un pourcentage."); }
        if (rate < 0) rate = null;
        double? multiplier = null, alternative = null;
        if (critDamage is float cd && float.IsFinite(cd))
        {
            multiplier = cd >= 1 ? cd : 1 + cd;
            alternative = cd >= 1 ? 1 + cd : cd;
            assumptions.Add(cd >= 1
                ? "Dégâts critiques lus comme un multiplicateur direct (1,5 = 150 %). L'autre lecture possible est donnée dans critMultiplier.alternative."
                : "Dégâts critiques lus comme un bonus au-dessus d'un coup normal (0,5 = +50 %). L'autre lecture possible est donnée dans critMultiplier.alternative.");
        }
        var includeCrit = !args.TryGetProperty("includeCrit", out var ic) || ic.ValueKind != JsonValueKind.False;
        double? expected = includeCrit && rate.HasValue && multiplier.HasValue
            ? 1 + Math.Clamp(rate.Value, 0, 1) * (multiplier.Value - 1) : null;
        if (!includeCrit) assumptions.Add("Coups critiques exclus à la demande : les dégâts donnés sont ceux d'un coup normal.");

        double? coefficient = Number(args, "coefficient");
        double? interval = Number(args, "intervalSeconds");
        if (coefficient is <= 0) throw new ArgumentException("coefficient doit être strictement positif.");
        if (interval is <= 0) throw new ArgumentException("intervalSeconds doit être strictement positif.");
        if (coefficient == null) missing.Add("coefficient : le client n'expose pas le coefficient de dégâts des capacités. Sans lui, aucun dégât par coup n'est calculé.");
        if (interval == null) missing.Add("intervalSeconds : sans intervalle entre les coups, aucun DPS n'est calculé.");

        double? perHit = power.HasValue && coefficient.HasValue ? power.Value * coefficient.Value : null;
        double? averaged = perHit.HasValue && expected.HasValue ? perHit.Value * expected.Value : null;
        double? dps = averaged.HasValue && interval.HasValue ? averaged.Value / interval.Value : null;
        return new {
            kind, certain = false,
            observed = new { power, powerField, criticalChance = chance, chanceField,
                criticalDamage = critDamage, damageField },
            critMultiplier = new { value = multiplier, alternative, expectedPerHitMultiplier = expected },
            supplied = new { coefficient, intervalSeconds = interval, includeCrit },
            estimate = new {
                hitWithoutCrit = perHit.HasValue ? Math.Round(perHit.Value, 2) : (double?)null,
                averageHitWithCrit = averaged.HasValue ? Math.Round(averaged.Value, 2) : (double?)null,
                damagePerSecond = dps.HasValue ? Math.Round(dps.Value, 2) : (double?)null },
            missingInputs = missing, assumptions,
            warning = "Estimation, jamais une valeur du jeu. La puissance et les critiques sont lus sur le personnage ; le coefficient et l'intervalle viennent de toi. La cible n'est pas prise en compte : réductions, armure, résistances, immunités, dégâts sur la durée, effets de set et bonus conditionnels ne sont pas modélisés. Compare en jeu avant de conclure."
        };
    }

    static double? Number(JsonElement a, string key)
    {
        if (!a.TryGetProperty(key, out var v) || v.ValueKind == JsonValueKind.Null) return null;
        if (v.ValueKind != JsonValueKind.Number || !v.TryGetDouble(out var d) || !double.IsFinite(d))
            throw new ArgumentException(key + " doit être un nombre fini.");
        return d;
    }
}
