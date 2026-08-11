#!/usr/bin/env npx ts-node
/**
 * Task management CLI — reads/writes `.tmp/tasks/{feature}/` per skill spec.
 */
import * as fs from "node:fs";
import * as path from "node:path";

const TASKS_DIR = ".tmp/tasks";
const STATUSES = new Set([
  "pending",
  "in_progress",
  "completed",
  "blocked",
]);

type TaskJson = {
  id: string;
  name?: string;
  status?: string;
  objective?: string;
  context_files?: string[];
  reference_files?: string[];
  exit_criteria?: string[];
  subtask_count?: number;
  completed_count?: number;
  created_at?: string;
  completed_at?: string | null;
  contracts?: unknown[];
  /** optional migration marker */
  _schema_version?: number;
};

type SubtaskJson = {
  id: string;
  seq: string;
  title?: string;
  status: string;
  depends_on?: string[];
  parallel?: boolean;
  suggested_agent?: string;
  context_files?: string[];
  reference_files?: string[];
  acceptance_criteria?: string[];
  deliverables?: string[];
  started_at?: string | null;
  completed_at?: string | null;
  completion_summary?: string | null;
  line_range?: Record<string, { start?: number; end?: number }>;
};

function argvAfterScript(): string[] {
  const i = process.argv.findIndex((a) => /task-cli\.ts$/.test(a));
  if (i >= 0) return process.argv.slice(i + 1);
  return process.argv.slice(2);
}

function tasksRoot(): string {
  return path.join(process.cwd(), TASKS_DIR);
}

function featureDir(slug: string): string {
  return path.join(tasksRoot(), slug);
}

function readJson<T>(fp: string): T {
  return JSON.parse(fs.readFileSync(fp, "utf8")) as T;
}

function writeJson(fp: string, data: unknown): void {
  fs.writeFileSync(fp, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

function listFeatureSlugs(activeOnly = false): string[] {
  const root = tasksRoot();
  if (!fs.existsSync(root)) return [];
  const dirs = fs
    .readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory() && d.name !== "completed")
    .map((d) => d.name);
  if (!activeOnly) return dirs.sort();
  return dirs.filter((slug) => {
    const t = path.join(root, slug, "task.json");
    if (!fs.existsSync(t)) return false;
    try {
      const j = readJson<TaskJson>(t);
      return (j.status ?? "active") !== "completed";
    } catch {
      return false;
    }
  }).sort();
}

function listSubtaskFiles(slug: string): string[] {
  const dir = featureDir(slug);
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((n) => /^subtask_\d+\.json$/.test(n))
    .sort();
}

function normalizeSeq(seq: string): string {
  const n = seq.replace(/^0+/, "") || "0";
  return n.padStart(2, "0");
}

function loadSubtasks(slug: string): Map<string, SubtaskJson> {
  const map = new Map<string, SubtaskJson>();
  for (const file of listSubtaskFiles(slug)) {
    const fp = path.join(featureDir(slug), file);
    const st = readJson<SubtaskJson>(fp);
    map.set(normalizeSeq(st.seq), st);
  }
  return map;
}

function depsSatisfied(st: SubtaskJson, bySeq: Map<string, SubtaskJson>): boolean {
  const deps = st.depends_on ?? [];
  for (const raw of deps) {
    const s = normalizeSeq(String(raw));
    const d = bySeq.get(s);
    if (!d || d.status !== "completed") return false;
  }
  return true;
}

function detectCycle(bySeq: Map<string, SubtaskJson>): string | null {
  const state = new Map<string, 0 | 1 | 2>();
  for (const k of bySeq.keys()) state.set(k, 0);

  function dfs(seq: string): string | null {
    const s = state.get(seq);
    if (s === 2) return null;
    if (s === 1) return `cycle detected (node ${seq} re-entered)`;
    state.set(seq, 1);
    const deps = (bySeq.get(seq)?.depends_on ?? []).map((x) =>
      normalizeSeq(String(x)),
    );
    for (const dn of deps) {
      if (!bySeq.has(dn)) continue;
      const c = dfs(dn);
      if (c) return c;
    }
    state.set(seq, 2);
    return null;
  }

  for (const k of bySeq.keys()) {
    if (state.get(k) !== 0) continue;
    const c = dfs(k);
    if (c) return c;
  }
  return null;
}

function printTaskHeader(task: TaskJson, slug: string, bySeq: Map<string, SubtaskJson>): void {
  const total = bySeq.size;
  let done = 0;
  let pending = 0;
  let inp = 0;
  let blocked = 0;
  for (const st of bySeq.values()) {
    if (st.status === "completed") done++;
    else if (st.status === "blocked") blocked++;
    else if (st.status === "in_progress") inp++;
    else pending++;
  }
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  const name = task.name ?? slug;
  console.log(`\n[${slug}] ${name}`);
  console.log(
    `  Status: ${task.status ?? "active"} | Progress: ${pct}% (${done}/${total})`,
  );
  console.log(
    `  Pending: ${pending} | In Progress: ${inp} | Completed: ${done} | Blocked: ${blocked}`,
  );
}

function cmdStatus(args: string[]): void {
  const filter = args[0];
  const slugs = filter
    ? listFeatureSlugs(false).filter((s) => s === filter)
    : listFeatureSlugs(false);
  if (slugs.length === 0) {
    console.log("No tasks found under .tmp/tasks/ (create some with TaskManager).");
    return;
  }
  for (const slug of slugs) {
    const tf = path.join(featureDir(slug), "task.json");
    if (!fs.existsSync(tf)) {
      console.log(`\n[${slug}] (missing task.json)`);
      continue;
    }
    const task = readJson<TaskJson>(tf);
    const bySeq = loadSubtasks(slug);
    printTaskHeader(task, slug, bySeq);
  }
}

function cmdNext(args: string[]): void {
  const filter = args[0];
  const slugs = filter
    ? listFeatureSlugs(true).filter((s) => s === filter)
    : listFeatureSlugs(true);

  console.log("\n=== Ready Tasks (deps satisfied) ===\n");
  let any = false;
  for (const slug of slugs) {
    const bySeq = loadSubtasks(slug);
    const ready: SubtaskJson[] = [];
    for (const st of bySeq.values()) {
      if (st.status === "blocked") continue;
      if (st.status !== "pending" && st.status !== "in_progress") continue;
      if (!depsSatisfied(st, bySeq)) continue;
      ready.push(st);
    }
    if (ready.length === 0) continue;
    any = true;
    console.log(`[${slug}]`);
    for (const st of ready.sort((a, b) => a.seq.localeCompare(b.seq))) {
      const par = st.parallel ? "parallel" : "sequential";
      console.log(`  ${st.seq} - ${st.title ?? st.id} [${par}]`);
    }
    console.log("");
  }
  if (!any)
    console.log("(none — all deps blocked, complete, or no tasks)\n");
}

function cmdParallel(args: string[]): void {
  const filter = args[0];
  const slugs = filter
    ? listFeatureSlugs(true).filter((s) => s === filter)
    : listFeatureSlugs(true);

  console.log("\n=== Parallelizable & ready ===\n");
  let any = false;
  for (const slug of slugs) {
    const bySeq = loadSubtasks(slug);
    const ready: SubtaskJson[] = [];
    for (const st of bySeq.values()) {
      if (!st.parallel) continue;
      if (st.status === "blocked") continue;
      if (st.status !== "pending" && st.status !== "in_progress") continue;
      if (!depsSatisfied(st, bySeq)) continue;
      ready.push(st);
    }
    if (ready.length === 0) continue;
    any = true;
    console.log(`[${slug}]`);
    for (const st of ready.sort((a, b) => a.seq.localeCompare(b.seq))) {
      console.log(`  ${st.seq} - ${st.title ?? st.id}`);
    }
    console.log("");
  }
  if (!any) console.log("(none)\n");
}

function printDepTree(
  slug: string,
  seq: string,
  bySeq: Map<string, SubtaskJson>,
  depth: number,
  chain: Set<string>,
): void {
  const s = normalizeSeq(seq);
  if (chain.has(s)) {
    console.log(`${"  ".repeat(depth)}(circular ref to ${s})`);
    return;
  }
  chain.add(s);
  const st = bySeq.get(s);
  const label = st
    ? `${st.seq} - ${st.title ?? st.id} [${st.status}]`
    : `${s} (missing subtask)`;
  console.log(`${"  ".repeat(depth)}${depth === 0 ? "═══ " : "├── "}${label}`);
  const deps = (st?.depends_on ?? []).map((x) => normalizeSeq(String(x)));
  for (const d of deps) {
    printDepTree(slug, d, bySeq, depth + 1, new Set(chain));
  }
}

function cmdDeps(args: string[]): void {
  const [feat, rawSeq] = args;
  if (!feat || !rawSeq) {
    console.error("Usage: deps <feature> <seq>");
    process.exit(1);
  }
  const seq = normalizeSeq(rawSeq);
  const bySeq = loadSubtasks(feat);
  console.log(`\n=== Dependency Tree: ${feat}/${seq} ===\n`);
  printDepTree(feat, seq, bySeq, 0, new Set());
  console.log("");
}

function cmdBlocked(args: string[]): void {
  const filter = args[0];
  const slugs = filter
    ? listFeatureSlugs(false).filter((s) => s === filter)
    : listFeatureSlugs(false);

  console.log("\n=== Blocked or waiting on deps ===\n");
  for (const slug of slugs) {
    const bySeq = loadSubtasks(slug);
    const blocked: SubtaskJson[] = [];
    const waiting: SubtaskJson[] = [];
    for (const st of bySeq.values()) {
      if (st.status === "blocked") blocked.push(st);
      else if (
        st.status === "pending" ||
        st.status === "in_progress"
      ) {
        if (!depsSatisfied(st, bySeq)) waiting.push(st);
      }
    }
    if (blocked.length === 0 && waiting.length === 0) continue;
    console.log(`[${slug}]`);
    for (const st of blocked) {
      console.log(`  🔴 blocked  ${st.seq} - ${st.title ?? st.id}`);
    }
    for (const st of waiting.sort((a, b) => a.seq.localeCompare(b.seq))) {
      const missing = (st.depends_on ?? [])
        .map((x) => normalizeSeq(String(x)))
        .filter((ds) => {
          const n = bySeq.get(ds);
          return !n || n.status !== "completed";
        });
      console.log(
        `  ⏳ waiting  ${st.seq} - ${st.title ?? st.id} (needs done: ${missing.join(", ") || "—"})`,
      );
    }
    console.log("");
  }
}

function cmdComplete(args: string[]): void {
  const feat = args[0];
  const rawSeq = args[1];
  const summary = args.slice(2).join(" ").trim();
  if (!feat || !rawSeq) {
    console.error('Usage: complete <feature> <seq> "summary"');
    process.exit(1);
  }
  if (!summary) {
    console.error("Summary required (provide after seq).");
    process.exit(1);
  }

  const seq = normalizeSeq(rawSeq);
  const dir = featureDir(feat);
  const fp = path.join(dir, `subtask_${seq}.json`);
  if (!fs.existsSync(fp)) {
    console.error(`Subtask file not found: ${fp}`);
    process.exit(1);
  }

  const st = readJson<SubtaskJson>(fp);
  st.status = "completed";
  st.completion_summary = summary;
  st.completed_at = new Date().toISOString();
  if (!st.started_at) st.started_at = st.completed_at;
  writeJson(fp, st);

  const tf = path.join(dir, "task.json");
  let completedCount = 0;
  const bySeq = loadSubtasks(feat);
  for (const x of bySeq.values()) if (x.status === "completed") completedCount++;

  if (fs.existsSync(tf)) {
    const task = readJson<TaskJson>(tf);
    task.completed_count = completedCount;
    const total = bySeq.size || task.subtask_count || 0;
    const allDone =
      total > 0 &&
      [...bySeq.values()].every((x) => x.status === "completed");
    if (allDone) {
      task.status = "completed";
      task.completed_at = new Date().toISOString();
    }
    task.subtask_count = bySeq.size;
    writeJson(tf, task);
  }

  console.log(`\n✓ Marked ${feat}/${seq} as completed`);
  console.log(`  Summary: ${summary}`);
  console.log(`  Progress: ${completedCount}/${bySeq.size}\n`);
}

function validateFeature(slug: string): string[] {
  const errs: string[] = [];
  const dir = featureDir(slug);
  const tf = path.join(dir, "task.json");
  if (!fs.existsSync(tf)) {
    errs.push(`[${slug}] missing task.json`);
    return errs;
  }

  let task: TaskJson;
  try {
    task = readJson<TaskJson>(tf);
  } catch (e) {
    errs.push(`[${slug}] task.json: invalid JSON (${String(e)})`);
    return errs;
  }
  if (task.id !== slug)
    errs.push(`[${slug}] task.id "${task.id}" should match slug "${slug}"`);

  const files = listSubtaskFiles(slug);
  const bySeq = new Map<string, SubtaskJson>();
  for (const file of files) {
    const fp = path.join(dir, file);
    let st: SubtaskJson;
    try {
      st = readJson<SubtaskJson>(fp);
    } catch (e) {
      errs.push(`[${slug}/${file}] invalid JSON (${String(e)})`);
      continue;
    }
    const seq = normalizeSeq(st.seq);
    if (bySeq.has(seq)) errs.push(`[${slug}] duplicate seq "${seq}"`);
    bySeq.set(seq, st);

    const expected = new RegExp(
      `^${slug.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}-\\d{2}$`,
    );
    if (!expected.test(st.id))
      errs.push(
        `[${slug}/${file}] id "${st.id}" should match pattern "${slug}-NN"`,
      );
    if (!STATUSES.has(st.status))
      errs.push(
        `[${slug}/${file}] invalid status "${st.status}" (${[...STATUSES].join("|")})`,
      );
    if (!Array.isArray(st.acceptance_criteria) || st.acceptance_criteria.length === 0)
      errs.push(`[${slug}/${file}] acceptance_criteria should be non-empty`);
    if (!Array.isArray(st.deliverables) || st.deliverables.length === 0)
      errs.push(`[${slug}/${file}] deliverables should be non-empty`);

    for (const d of st.depends_on ?? []) {
      const dn = normalizeSeq(String(d));
      const match = files.some((f) => f === `subtask_${dn}.json`);
      if (!match)
        errs.push(
          `[${slug}/${file}] depends_on references missing subtask_${dn}.json`,
        );
    }
    const selfSeq = normalizeSeq(st.seq);
    if (
      (st.depends_on ?? []).some(
        (x) => normalizeSeq(String(x)) === selfSeq,
      )
    )
      errs.push(`[${slug}/${file}] depends_on includes self`);
  }

  const cyc = detectCycle(bySeq);
  if (cyc) errs.push(`[${slug}] ${cyc}`);

  if (
    typeof task.subtask_count === "number" &&
    task.subtask_count !== bySeq.size
  ) {
    errs.push(
      `[${slug}] task.subtask_count (${task.subtask_count}) ≠ files (${bySeq.size})`,
    );
  }

  return errs;
}

function cmdValidate(args: string[]): number {
  const filter = args[0];
  const slugs = filter
    ? listFeatureSlugs(false).filter((s) => s === filter)
    : listFeatureSlugs(false);
  if (slugs.length === 0) {
    console.log("No tasks to validate.");
    return 0;
  }

  console.log("\n=== Validation Results ===\n");
  let failed = false;
  for (const slug of slugs) {
    const errs = validateFeature(slug);
    if (errs.length === 0) console.log(`[${slug}]  ✓ All checks passed`);
    else {
      failed = true;
      console.log(`[${slug}]  ✗ issues:`);
      for (const e of errs) console.log(`    - ${e}`);
    }
  }
  console.log("");
  return failed ? 1 : 0;
}

function cmdContext(args: string[]): void {
  const feat = args[0];
  if (!feat) {
    console.error("Usage: context <feature>");
    process.exit(1);
  }
  const tf = path.join(featureDir(feat), "task.json");
  if (!fs.existsSync(tf)) {
    console.error(`No task for "${feat}".`);
    process.exit(1);
  }
  const task = readJson<TaskJson>(tf);
  const bySeq = loadSubtasks(feat);
  const ctx = new Set<string>();
  const ref = new Set<string>();
  for (const x of task.context_files ?? []) ctx.add(x);
  for (const x of task.reference_files ?? []) ref.add(x);
  for (const st of bySeq.values()) {
    for (const x of st.context_files ?? []) ctx.add(x);
    for (const x of st.reference_files ?? []) ref.add(x);
  }
  console.log(`\n=== Context (${feat}) ===\n`);
  console.log("Context files:");
  if (ctx.size === 0) console.log("  (none)");
  else [...ctx].sort().forEach((p) => console.log(`  - ${p}`));
  console.log("\nReference files:");
  if (ref.size === 0) console.log("  (none)");
  else [...ref].sort().forEach((p) => console.log(`  - ${p}`));
  console.log("");
}

function cmdContracts(args: string[]): void {
  const feat = args[0];
  if (!feat) {
    console.error("Usage: contracts <feature>");
    process.exit(1);
  }
  const tf = path.join(featureDir(feat), "task.json");
  if (!fs.existsSync(tf)) {
    console.error(`No task for "${feat}".`);
    process.exit(1);
  }
  const task = readJson<TaskJson>(tf);
  console.log(`\n=== Contracts (${feat}) ===\n`);
  if (!task.contracts || !Array.isArray(task.contracts) || task.contracts.length === 0) {
    console.log("No contracts field or empty — nothing to show.\n");
    return;
  }
  console.log(JSON.stringify(task.contracts, null, 2));
  console.log("");
}

function printCliHelp(): void {
  console.log(`
Usage: router.sh <command> [args]

Commands:
  status [feature]
  next [feature]
  parallel [feature]
  deps <feature> <seq>
  blocked [feature]
  complete <feature> <seq> <summary message>
  validate [feature]
  context <feature>
  contracts <feature>
`);
}

function main(): void {
  const args = argvAfterScript();
  const cmd = args[0];
  const tail = args.slice(1);

  if (!cmd || cmd === "help" || cmd === "-h" || cmd === "--help") {
    printCliHelp();
    process.exit(0);
  }

  switch (cmd) {
    case "status":
      cmdStatus(tail);
      break;
    case "next":
      cmdNext(tail);
      break;
    case "parallel":
      cmdParallel(tail);
      break;
    case "deps":
      cmdDeps(tail);
      break;
    case "blocked":
      cmdBlocked(tail);
      break;
    case "complete":
      cmdComplete(tail);
      break;
    case "validate": {
      const code = cmdValidate(tail);
      process.exit(code);
    }
    case "context":
      cmdContext(tail);
      break;
    case "contracts":
      cmdContracts(tail);
      break;
    default:
      console.error(`Unknown command: ${cmd}`);
      printCliHelp();
      process.exit(1);
  }
}

main();
