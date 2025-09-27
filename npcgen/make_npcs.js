// make_npcs_from_files.js (CommonJS)
// Usage examples:
//   node make_npcs_from_files.js 500 --out out --seed myseed `
//     --hooks hooks.txt --backstories backs.txt --mannerisms mans.txt --quirks quirks.txt `
//     --occupations jobs.txt --factions factions.txt --equipment equipment.txt --religions religions.txt
//
// Notes:
// - Each file is plain text, one entry per line; blank lines and lines starting with # or // are ignored.
// - Script falls back to defaults if a file is missing or empty.
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
    "blacksmith","apothecary","cartographer","fisher","innkeeper",
    "scribe","sailor","hunter","stablehand","town guard",
  ],
  factions: [
    "Local Merchants' Guild",
    "City Watch Auxiliaries",
    "Dockside Union",
    "Circle of Lanterns (informal do-gooders)",
    "Quiet Ledger Society (bookkeepers with secrets)",
  ],
  equipment: [
    "dagger","shortsword","quarterstaff","healer’s kit","lockpicks",
    "lantern","rope (50 ft)","vial of ink and quill","waterskin","rations (3 days)",
  ],
  religions: [
    "Old Road Shrine (traveler’s luck)",
    "The Tidemother",
    "The Archivist",
    "The Smith of Embers",
    "The Veiled Star",
  ],
  names: [
    "Alden","Briala","Cassian","Darya","Eamon",
    "Fenya","Garran","Helmi","Ilan","Jora",
  ],
};

// --------------------- file helpers ---------------------
function loadLines(filePath) {
  if (!filePath) return [];
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return raw
      .split(/\r?\n/)
      .map(s => s.trim())
      .filter(s => s.length && !s.startsWith("#") && !s.startsWith("//"));
  } catch {
    return [];
  }
}

function loadPoolsFromFiles(opt) {
  const pools = JSON.parse(JSON.stringify(DEFAULTS)); // clone defaults
  const mapping = {
    hooks: opt.hooks,
    backstories: opt.backstories,
    mannerisms: opt.mannerisms,
    quirks: opt.quirks,
    occupations: opt.occupations,
    factions: opt.factions,
    equipment: opt.equipment,
    religions: opt.religions,
  };
  for (const [key, filepath] of Object.entries(mapping)) {
    const lines = loadLines(filepath);
    if (lines.length) pools[key] = uniq(lines);
  }
  // sanity check
  for (const key of Object.keys(pools)) {
    if (!Array.isArray(pools[key]) || pools[key].length === 0) {
      pools[key] = DEFAULTS[key] || [];
    }
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
const opt = {
  out: getFlag("out") || "output",
  seed: getFlag("seed") || null,
  hooks: getFlag("hooks"),
  backstories: getFlag("backstories"),
  mannerisms: getFlag("mannerisms"),
  quirks: getFlag("quirks"),
  occupations: getFlag("occupations"),
  factions: getFlag("factions"),
  equipment: getFlag("equipment"),
  religions: getFlag("religions"),
   names: getFlag("names"),
};

// --------------------- setup ---------------------
const rng = makeRng(opt.seed || undefined);
const pools = loadPoolsFromFiles(opt);

const outDir = path.resolve(opt.out);
fs.mkdirSync(outDir, { recursive: true });
const jsonlPath = path.join(outDir, "npcs.jsonl");
const txtPath = path.join(outDir, "npcs.txt");
const outJsonl = fs.createWriteStream(jsonlPath, { encoding: "utf-8" });
const outTxt = fs.createWriteStream(txtPath, { encoding: "utf-8" });

// --------------------- flavor builder ---------------------
function buildName() {
  const first = choice(rng, pools.names);
  let last = choice(rng, pools.names);
  while (last === first && pools.names.length > 1) {
    last = choice(rng, pools.names);
  }
  return `${first} ${last}`;
}

function buildFlavor(npcBase) {
  const nameOut = buildName();
  const occupation = choice(rng, pools.occupations);
  const hook = choice(rng, pools.hooks);
  const mannerism = choice(rng, pools.mannerisms);
  const quirkList = chooseN(rng, pools.quirks, 2);
  const backFrag = choice(rng, pools.backstories);
  const factionTies = chooseN(rng, pools.factions, 1);
  const religion = choice(rng, pools.religions);
  const equipmentPicks = chooseN(rng, pools.equipment, 3);

  const backstory =
    `Once ${nameOut} ${backFrag}. ` +
    `These days they work as a ${occupation}. ` +
    (factionTies.length ? `They have ties to ${factionTies.join(", ")}. ` : "") +
    `They ${mannerism}, and ${quirkList.join(" and ")}.`;

  return {
    name: nameOut,
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

// --------------------- main loop ---------------------
for (let i = 0; i < COUNT; i++) {
  const { npc } = generate(); // base object from npc-generator
  const flavor = buildFlavor(npc);

  const full = {
    ...npc,
    ...flavor,
    _meta: {
      created_at: new Date().toISOString(),
      seed: opt.seed || "random",
      index: i + 1,
      sources: { flavor_files: { ...opt } },
    },
  };

  // JSONL
  outJsonl.write(JSON.stringify(full) + "\n");

  // Pretty TXT
  outTxt.write(`### NPC ${i + 1}: ${full.name}\n`);
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

outJsonl.end();
outTxt.end();

console.log(`✅ Generated ${COUNT} NPCs ->`);
console.log(`   ${jsonlPath}`);
console.log(`   ${txtPath}`);
if (opt.seed) console.log(`   (seed: ${opt.seed})`);