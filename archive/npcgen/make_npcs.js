// make_npcs.js (CommonJS) — safer I/O, clearer errors, location parsing (City, Country)
// Usage:
//   node make_npcs.js 500 --out out --seed myseed --locations Locations.txt
// Flags:
//   --strict-locations   Fail if locations file missing/empty or all lines invalid
//   --dry-run            Generate 5 sample NPCs to console; don't write files
//
// Notes:
// - Text pools are plain text, one entry per line; blank lines and lines starting with # or // are ignored.
// - Outputs JSONL and TXT in the specified --out folder.

const { generate } = require("npc-generator");
const fs = require("fs");
const path = require("path");

// --------------------- tiny deterministic PRNG ---------------------
function xmur3(str) {
    let h = 1779033703 ^ str.length;
    for (let i = 0; i < str.length; i++) {
        h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
        h = (h << 13) | (h >>> 19);
    }
    return function () {
        h = Math.imul(h ^ (h >>> 16), 2246822507);
        h = Math.imul(h ^ (h >>> 13), 3266489909);
        return (h ^= h >>> 16) >>> 0;
    };
}
function mulberry32(a) {
    return function () {
        let t = (a += 0x6D2B79F5);
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
function makeRng(seed) {
    const seedFn = xmur3(seed || Math.random().toString(36).slice(2));
    return mulberry32(seedFn());
}
function choice(rng, arr) { return arr[Math.floor(rng() * arr.length)]; }
function chooseN(rng, arr, n) {
    if (!arr.length) return [];
    const picks = new Set();
    while (picks.size < Math.min(n, arr.length)) {
        picks.add(arr[Math.floor(rng() * arr.length)]);
    }
    return [...picks];
}
const uniq = (a) => [...new Set(a)];

// --------------------- defaults (used if files missing/empty) ---------------------
const DEFAULTS = {
    hooks: [
        "Lost something precious and begs for help finding it.",
        "Owes money to the wrong people; collectors arrive at dusk.",
        "Spotted a monster near the old mill; needs brave company.",
        "Carries a sealed letter they’re afraid to deliver.",
        "Claims to have a map to a hidden shrine—but only half of it.",
    ],
    backstories: [
        "was raised on the docks and learned to read the tides better than books",
        "studied under a stern mentor who vanished after a cryptic note",
        "once served in a minor lord's retinue before a scandal ousted them",
        "owes their life to a traveling healer and now repays kindness whenever possible",
        "spent a season among nomads and learned forgotten star-names",
    ],
    mannerisms: [
        "taps fingers in groups of three",
        "won’t meet eyes for long",
        "speaks in whispers even when alone",
        "straightens objects on tables",
        "hums a lullaby under their breath",
    ],
    quirks: [
        "collects shiny buttons",
        "is convinced ravens bring messages",
        "never drinks the last sip",
        "names every tool they own",
        "keeps a list of grudges in tiny script",
    ],
    occupations: [
        "blacksmith", "apothecary", "cartographer", "fisher", "innkeeper",
        "scribe", "sailor", "hunter", "stablehand", "town guard",
    ],
    factions: [
        "Local Merchants' Guild",
        "City Watch Auxiliaries",
        "Dockside Union",
        "Circle of Lanterns (informal do-gooders)",
        "Quiet Ledger Society (bookkeepers with secrets)",
    ],
    equipment: [
        "dagger", "shortsword", "quarterstaff", "healer’s kit", "lockpicks",
        "lantern", "rope (50 ft)", "vial of ink and quill", "waterskin", "rations (3 days)",
    ],
    religions: [
        "Old Road Shrine (traveler’s luck)",
        "The Tidemother",
        "The Archivist",
        "The Smith of Embers",
        "The Veiled Star",
    ],
    names: [
        "Alden", "Briala", "Cassian", "Darya", "Eamon",
        "Fenya", "Garran", "Helmi", "Ilan", "Jora",
    ],
};

// --------------------- file helpers ---------------------
function loadLines(filePath) {
    if (!filePath) return [];
    try {
        if (!fs.existsSync(filePath)) return [];
        const raw = fs.readFileSync(filePath, "utf-8");
        return raw.split(/\r?\n/).map(s => s.trim()).filter(s => s.length && !s.startsWith("#") && !s.startsWith("//"));
    } catch (e) {
        console.error(`[error] Failed reading "${filePath}": ${e.message}`);
        return [];
    }
}
function loadPoolsFromFiles(opt) {
    const pools = JSON.parse(JSON.stringify(DEFAULTS));
    const mapping = {
        hooks: opt.hooks,
        backstories: opt.backstories,
        mannerisms: opt.mannerisms,
        quirks: opt.quirks,
        occupations: opt.occupations,
        factions: opt.factions,
        equipment: opt.equipment,
        religions: opt.religions,
        names: opt.names,
    };
    for (const [key, fp] of Object.entries(mapping)) {
        const lines = loadLines(fp);
        if (lines.length) pools[key] = uniq(lines);
    }
    for (const key of Object.keys(pools)) {
        if (!Array.isArray(pools[key]) || pools[key].length === 0) pools[key] = DEFAULTS[key] || [];
    }
    return pools;
}

// --------------------- CLI args ---------------------
const COUNT = Number(process.argv[2] || 100);
const argv = process.argv.slice(3);
const getFlag = (name) => {
    const p = argv.find(a => a.startsWith(`--${name}=`));
    return p ? p.split("=").slice(1).join("=") : null;
};
const hasFlag = (name) => argv.some(a => a === `--${name}`);
const opt = {
    out: getFlag("out") || "output",
    seed: getFlag("seed") || null,
    hooks: getFlag("hooks"),
    backstories: getFlag("backstories") || "backs.txt",
    mannerisms: getFlag("mannerisms") || "mans.txt",
    quirks: getFlag("quirks") || "quirks.txt",
    occupations: getFlag("occupations") || "jobs.txt",
    factions: getFlag("factions") || "factions.txt",
    equipment: getFlag("equipment") || "equipment.txt",
    religions: getFlag("religions") || "religions.txt",
    names: getFlag("names") || "names.txt",
    locations: getFlag("locations") || "Locations.txt",
    strictLocations: hasFlag("strict-locations"),
    dryRun: hasFlag("dry-run"),
};

// --------------------- setup ---------------------
const rng = makeRng(opt.seed || undefined);
const pools = loadPoolsFromFiles(opt);

// Ensure out dir is writable (unless dry-run)
const outDir = path.resolve(opt.out);
if (!opt.dryRun) {
    try {
        fs.mkdirSync(outDir, { recursive: true });
        fs.accessSync(outDir, fs.constants.W_OK);
    } catch (e) {
        console.error(`[fatal] Cannot write to output directory "${outDir}": ${e.message}`);
        process.exit(1);
    }
}

// --------------------- logging helper ---------------------
const log = (...args) => console.log(...args);

// --------------------- localization core ---------------------
const normalize = s => (s || "").toLowerCase().replace(/[^a-z']/g, " ").replace(/\s+/g, " ").trim();

const LOCALE_ALIASES = {
    "waterdeep": "waterdeep", "baldur's gate": "baldurs_gate", "baldurs gate": "baldurs_gate",
    "neverwinter": "neverwinter", "icewind dale": "icewind_dale", "luskan": "luskan",
    "amn": "amn", "tethyr": "tethyr", "cormyr": "cormyr", "dalelands": "dalelands", "sembia": "sembia",
    "moonshae isles": "moonshae", "rashemen": "rashemen", "thay": "thay", "calimshan": "calimshan",
    "chult": "chult", "mulhorand": "mulhorand", "thesk": "thesk", "cormanthor": "cormanthor",
    "underdark": "underdark", "menzoberranzan": "underdark",
    "kara-tur": "kara_tur", "kara tur": "kara_tur", "damara": "damara",
};
const KEY_TO_LABEL = {
    waterdeep: "Waterdeep", baldurs_gate: "Baldur's Gate", neverwinter: "Neverwinter",
    icewind_dale: "Icewind Dale", luskan: "Luskan",
    amn: "Amn", tethyr: "Tethyr", cormyr: "Cormyr", dalelands: "Dalelands", sembia: "Sembia",
    moonshae: "Moonshae Isles", rashemen: "Rashemen", thay: "Thay", calimshan: "Calimshan",
    chult: "Chult", mulhorand: "Mulhorand", thesk: "Thesk", cormanthor: "Cormanthor",
    underdark: "Underdark", kara_tur: "Kara-Tur", damara: "Damara",
    common: "Common (Sword Coast)"
};
function canonicalKey(name) {
    if (!name) return "common";
    const key = normalize(name);
    return LOCALE_ALIASES[key] || key.replace(/\s+/g, "_");
}
const CANON_DEFAULT = "common";

function coin(rng, p = 0.5) { return rng() < p; }
function cap(s) { return s.replace(/\b\w/g, c => c.toUpperCase()); }
function splitFirstLast(name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return { first: parts[0], last: "" };
    return { first: parts[0], last: parts.slice(1).join(" ") };
}
function swapOrderIfNeeded(first, last, doSwap) {
    if (!doSwap) return { first, last };
    return { first: last || first, last: last ? first : "" };
}

const LOCALIZATION_RULES = {
    common({ first, last, rng, place }) {
        let f = first, l = last || choice(rng, ["Merton", "Ashford", "Blenmont", "Carrow", "Trent"]);
        if (coin(rng, 0.25)) l = l.replace(/e?$/, coin(rng) ? "son" : coin(rng) ? "ton" : "ford");
        if (coin(rng, 0.18) && place) l = `${l} of ${place}`;
        return `${f} ${l}`.trim();
    },
    waterdeep(ctx) { return LOCALIZATION_RULES.common(ctx); },
    neverwinter(ctx) { return LOCALIZATION_RULES.common(ctx); },
    dalelands(ctx) { return LOCALIZATION_RULES.common(ctx); },
    sembia({ first, last, rng }) {
        let l = last || choice(rng, ["Ravensworth", "Harrowmont", "Silvertome"]);
        if (coin(rng, 0.4)) l = l + (coin(rng) ? " Coster" : " Ledger");
        if (coin(rng, 0.2)) l = `of Sembia`;
        return `${first} ${l}`;
    },
    amn({ first, last, rng }) {
        let l = last || choice(rng, ["Varas", "del Oro", "Costa"]);
        if (coin(rng, 0.5)) l = (coin(rng, 0.5) ? `de ` : `da `) + l;
        if (coin(rng, 0.5)) l = l.replace(/\b([A-Za-z]{3,})\b/, (m) => m + (coin(rng) ? "ez" : "es"));
        return `${first} ${cap(l)}`;
    },
    tethyr(ctx) { return LOCALIZATION_RULES.amn(ctx); },
    cormyr({ first, last, rng }) {
        let l = last || choice(rng, ["Crownsilver", "Obarskyr", "Hawklin", "Huntsilver"]);
        if (coin(rng, 0.35)) l = "von " + l;
        if (coin(rng, 0.25)) l = l + (coin(rng) ? "-Mont" : "-ard");
        return `${first} ${cap(l)}`;
    },
    icewind_dale({ first, last, rng }) {
        let patronymic = coin(rng) ? `${first}${coin(rng) ? "son" : "dottir"}` : null;
        let l = last || choice(rng, ["Hrafn", "Stig", "Ulf", "Bjorn", "Halvar"]);
        if (coin(rng, 0.5)) l = l + (coin(rng) ? "sson" : "sdottir");
        if (coin(rng, 0.3) && patronymic) l = patronymic;
        return `${first} ${l}`;
    },
    luskan({ first, last, rng }) {
        let base = LOCALIZATION_RULES.icewind_dale({ first, last, rng });
        if (coin(rng, 0.35)) base += ` the ${choice(rng, ["Red", "Salted", "Black", "Weathered"])}`;
        return base;
    },
    calimshan({ first, last, rng, place }) {
        const tweak = (s) => s.replace(/c/gi, coin(rng, 0.5) ? "k" : "q").replace(/v/gi, "w").replace(/y/gi, "i");
        let f = cap(tweak(first));
        let lCore = cap(tweak(last || choice(rng, ["Sahir", "Nadir", "Qassar", "Hakim", "Samir"])));
        if (coin(rng, 0.6)) lCore = lCore.replace(/([a-z])$/i, (_, x) => x + choice(rng, ["ar", "im", "ah"]));
        let l = coin(rng, 0.5) ? `al-${lCore}` : lCore;
        if (coin(rng, 0.25)) l = `${coin(rng) ? "ibn" : "bint"} ${l}`;
        if (coin(rng, 0.15) && place) l += ` of ${place}`;
        return `${f} ${l}`;
    },
    thay({ first, last, rng }) {
        const prefixes = ["Men", "Ram", "Set", "Ak", "An", "Kh"];
        const suffixes = ["hotep", "khet", "kara", "amun", "nefer", "sutekh"];
        let f = first;
        if (coin(rng, 0.6)) f = cap(choice(rng, prefixes)) + f.toLowerCase();
        let l = last || choice(rng, ["Ank", "Hep", "Kara", "Seth"]);
        if (coin(rng, 0.8)) l = l + choice(rng, suffixes);
        return `${f} ${cap(l)}`;
    },
    mulhorand(ctx) { return LOCALIZATION_RULES.thay(ctx); },
    rashemen({ first, last, rng }) {
        let base = (last || choice(rng, ["Vol", "Yev", "Kos", "Drag", "Mik"]));
        let l = coin(rng, 0.5) ? base + (coin(rng) ? "ovich" : "ovna") : base + (coin(rng) ? "sky" : "ska");
        let f = first.replace(/ia$/i, "ya").replace(/e\b/i, "ye");
        return `${cap(f)} ${cap(l)}`;
    },
    damara({ first, last, rng }) {
        let l = (last || choice(rng, ["Karg", "Petro", "Sidor", "Moroz", "Beres"]));
        l += coin(rng, 0.6) ? (coin(rng) ? "ov" : "ova") : (coin(rng) ? "enko" : "ic");
        return `${first} ${cap(l)}`;
    },
    kara_tur({ first, last, rng }) {
        let family = cap(last || choice(rng, ["Li", "Zhao", "Tan", "Wei", "Huang", "Shen", "Lin"]));
        let given = cap(first);
        if (coin(rng, 0.7)) {
            given = given.replace(/([A-Za-z]{2,})/, (m) => {
                const cut = Math.max(2, Math.min(m.length - 1, Math.floor(rng() * (m.length - 1))));
                return m.slice(0, cut) + "-" + m.slice(cut);
            });
        }
        const { first: F, last: L } = swapOrderIfNeeded(given, family, true);
        return `${F} ${L}`.trim();
    },
    chult({ first, last, rng, place }) {
        const expand = (s) => cap(s.toLowerCase().replace(/r(?![aeiou])/g, "ra").replace(/t(?![aeiou])/g, "ta").replace(/k(?![aeiou])/g, "ka"));
        let f = expand(first);
        let l = cap(last || choice(rng, ["Tembe", "Zawadi", "Kendi", "M'Bala", "Ngozi"]));
        if (coin(rng, 0.6)) l = l.replace(/e?$/, "" + choice(rng, ["we", "mba", "ndi"]));
        if (coin(rng, 0.25)) l = `${l} of ${choice(rng, ["Port Nyanzaru", "Mezro", "M'Bala"])}`;
        if (coin(rng, 0.15) && place) l = `${l}, ${place}`;
        return `${f} ${l}`;
    },
    moonshae({ first, last, rng }) {
        let f = first.replace(/i\b/i, "ydd").replace(/e\b/i, "en");
        if (coin(rng, 0.4)) f = "Mac" + cap(f);
        if (coin(rng, 0.3)) f = "O'" + cap(f);
        if (coin(rng, 0.2)) f = "ap " + cap(f);
        let l = last || choice(rng, ["Bryn", "Cadfan", "Darrow", "Pender"]);
        if (coin(rng, 0.6)) l = l + choice(rng, ["wyn", "aidh", "bryn"]);
        return `${cap(f)} ${cap(l)}`;
    },
    cormanthor({ first, last, rng }) {
        const elfify = (s) => cap(s.toLowerCase().replace(/a/g, "ae").replace(/o/g, "oa").replace(/u/g, "ui"));
        let f = elfify(first);
        let l = cap(last || choice(rng, ["Amastacia", "Galanodel", "Holimion", "Iliathor"]));
        if (coin(rng, 0.7)) l = l.replace(/$/, "" + choice(rng, ["ion", "thir", "elor", "ae"]));
        if (coin(rng, 0.2)) l = `${l} of the Green`;
        return `${f} ${l}`;
    },
    underdark({ first, last, rng }) {
        const darken = (s) => cap(s.toLowerCase().replace(/[ae]/g, choice(rng, ["a", "e", "i"])).replace(/s/g, "z").replace(/c/g, "x").replace(/t(?!h)/g, "t'"));
        let f = darken(first);
        let l = darken(last || choice(rng, ["Zau", "Xil", "Veld", "Zin", "Rel"]));
        if (coin(rng, 0.7)) l = l + choice(rng, ["rin", "zt", "dra", "vyr"]);
        return `${f} ${l}`;
    },
    thesk({ first, last, rng }) {
        const rule = coin(rng, 0.5) ? LOCALIZATION_RULES.rashemen : LOCALIZATION_RULES.kara_tur;
        return rule({ first, last, rng });
    },
};

// --------------------- Locations loading (City, Country) ---------------------
function parseLocations(lines, { strict = false } = {}) {
    const out = [];
    let bad = 0;
    for (const raw of lines) {
        const parts = raw.split(",").map(s => s.trim()).filter(Boolean);
        if (parts.length < 2) { bad++; continue; }
        const [city, country] = parts;
        out.push({ city, country });
    }
    if (bad) {
        console.warn(`[warn] Skipped ${bad} invalid location line(s). Expected "City, Country".`);
    }
    if (!out.length) {
        const msg = `[${strict ? "fatal" : "warn"}] No valid locations found.`;
        strict ? console.error(msg) : console.warn(msg);
    }
    return out;
}

function loadLocationsFile(filePath, { strict = false } = {}) {
    const lines = loadLines(filePath);
    if (!lines.length) {
        const msg = `[${strict ? "fatal" : "warn"}] Locations file "${filePath}" missing or empty.`;
        strict ? console.error(msg) : console.warn(msg);
        return [];
    }
    return parseLocations(lines, { strict });
}

function randomLocation(rng, locations) {
    if (!locations.length) return { city: "Unknown City", country: "Unknown Region" };
    return choice(rng, locations);
}

// --------------------- name localization helpers ---------------------
function localizeName(baseName, originKey, rng, placeLabel) {
    const { first, last } = splitFirstLast(baseName);
    const rule = LOCALIZATION_RULES[originKey] || LOCALIZATION_RULES.common;
    const result = rule({ first: cap(first), last: cap(last), rng, place: placeLabel });
    return cap(result.trim());
}
function labelForKey(key) {
    return KEY_TO_LABEL[key] || key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

// --------------------- flavor builder ---------------------
function buildBaseName() {
    const first = choice(rng, pools.names);
    let last = choice(rng, pools.names);
    while (last === first && pools.names.length > 1) {
        last = choice(rng, pools.names);
    }
    return `${first} ${last}`;
}

function buildFlavor(npcBase, origin) {
    const baseName = buildBaseName();
    const originKey = canonicalKey(origin.city) || CANON_DEFAULT;
    const placeLabel = labelForKey(originKey);
    const localized = localizeName(baseName, originKey, rng, placeLabel);

    const occupation = choice(rng, pools.occupations);
    const hook = choice(rng, pools.hooks);
    const mannerism = choice(rng, pools.mannerisms);
    const quirkList = chooseN(rng, pools.quirks, 2);
    const backFrag = choice(rng, pools.backstories);
    const factionTies = chooseN(rng, pools.factions, 1);
    const religion = choice(rng, pools.religions);
    const equipmentPicks = chooseN(rng, pools.equipment, 3);

    const backstory =
        ` ${localized} ${backFrag}. ` +
        `They hail from ${origin.city}, ${origin.country}. ` +
        `These days they work as a ${occupation}. ` +
        (factionTies.length ? `They have ties to ${factionTies.join(", ")}. ` : "") +
        `They ${mannerism}, and ${quirkList.join(" and ")}.`;

    return {
        name: localized,
        _base_name: baseName,
        origin: `${origin.city}, ${origin.country}`,
        occupation,
        hook,
        mannerism,
        quirks: quirkList,
        faction_ties: factionTies,
        religion,
        equipment: equipmentPicks,
        backstory,
    };
}

// --------------------- MAIN ---------------------
(function main() {
    const locationsPool = loadLocationsFile(opt.locations, { strict: opt.strictLocations });
    if (opt.strictLocations && !locationsPool.length) {
        process.exit(1);
    }
    if (!locationsPool.length) {
        console.warn(`[warn] Proceeding with fallback origin "Unknown City, Unknown Region".`);
    }

    // Summary
    log(`▶ Generating ${COUNT} NPCs`);
    log(`   seed: ${opt.seed || "(random)"}`);
    log(`   out:  ${opt.dryRun ? "(dry-run)" : path.resolve(opt.out)}`);
    log(`   locations: ${opt.locations} (${locationsPool.length || "0"} valid)`);
    if (opt.dryRun) log(`   (dry-run) Will print 5 sample NPCs and exit.\n`);

    // Streams (unless dry-run)
    let outJsonl, outTxt, jsonlPath, txtPath;
    if (!opt.dryRun) {
        jsonlPath = path.join(outDir, "npcs.jsonl");
        txtPath = path.join(outDir, "npcs.txt");
        try {
            outJsonl = fs.createWriteStream(jsonlPath, { encoding: "utf-8" });
            outTxt = fs.createWriteStream(txtPath, { encoding: "utf-8" });
        } catch (e) {
            console.error(`[fatal] Failed to open output files: ${e.message}`);
            process.exit(1);
        }
    }

    const emitOne = (i) => {
        const { npc } = generate();
        const origin = randomLocation(rng, locationsPool);
        const flavor = buildFlavor(npc, origin);
        const full = {
            ...npc,
            ...flavor,
            _meta: {
                created_at: new Date().toISOString(),
                seed: opt.seed || "random",
                index: i + 1,
                sources: { flavor_files: { ...opt, locations_file: opt.locations } },
            },
        };

        if (opt.dryRun) {
            console.log(`\n### NPC ${i + 1}: ${full.name}`);
            console.log(`Origin: ${full.origin}`);
            if (full.race) console.log(`Race: ${full.race}`);
            if (full.class) console.log(`Class: ${full.class}`);
            console.log(`Occupation: ${full.occupation}`);
            console.log(`Religion: ${full.religion}`);
            if (full.faction_ties?.length) console.log(`Faction ties: ${full.faction_ties.join(", ")}`);
            if (full.equipment?.length) console.log(`Equipment: ${full.equipment.join(", ")}`);
            console.log(`Hook: ${full.hook}`);
            console.log(`Mannerism: ${full.mannerism}`);
            console.log(`Quirks: ${full.quirks.join(", ")}`);
            console.log(`Backstory:\n${full.backstory}`);
        } else {
            outJsonl.write(JSON.stringify(full) + "\n");

            outTxt.write(`### NPC ${i + 1}: ${full.name}\n`);
            if (full.origin) outTxt.write(`Origin: ${full.origin}\n`);
            if (full.race) outTxt.write(`Race: ${full.race}\n`);
            if (full.class) outTxt.write(`Class: ${full.class}\n`);
            outTxt.write(`Occupation: ${full.occupation}\n`);
            outTxt.write(`Religion: ${full.religion}\n`);
            if (full.faction_ties?.length) outTxt.write(`Faction ties: ${full.faction_ties.join(", ")}\n`);
            if (full.equipment?.length) outTxt.write(`Equipment: ${full.equipment.join(", ")}\n`);
            outTxt.write(`Hook: ${full.hook}\n`);
            outTxt.write(`Mannerism: ${full.mannerism}\n`);
            outTxt.write(`Quirks: ${full.quirks.join(", ")}\n`);
            outTxt.write(`Backstory:\n${full.backstory}\n\n`);
        }
    };

    const sampleCount = opt.dryRun ? Math.min(5, COUNT) : COUNT;
    for (let i = 0; i < sampleCount; i++) {
        emitOne(i);
        if (!opt.dryRun && (i + 1) % 1000 === 0) {
            log(`   ...${i + 1} generated`);
        }
    }

    if (!opt.dryRun) {
        outJsonl.end();
        outTxt.end();
        log(`\n✅ Generated ${COUNT} NPCs ->`);
        log(`   ${jsonlPath}`);
        log(`   ${txtPath}`);
        if (opt.seed) log(`   (seed: ${opt.seed})`);
    } else {
        log(`\n(dry-run) Preview complete.`);
    }
})();
