// Production build without Vite: esbuild bundles the TypeScript/React code, Tailwind's compiler
// generates the CSS from the class names used in src/. Output goes to frontend/dist.
//
//   node scripts/build.mjs            (uses packages from frontend/node_modules)
//
// Package resolution order: frontend/node_modules, then NODE_PATH entries (used in the build sandbox).
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const extraPaths = (process.env.NODE_PATH || "").split(path.delimiter).filter(Boolean);
const searchPaths = [path.join(root, "node_modules"), ...extraPaths];
const req = createRequire(path.join(root, "package.json"));

function resolvePkg(name) {
  for (const base of searchPaths) {
    const p = path.join(base, name);
    if (fs.existsSync(p)) return p;
  }
  try {
    return path.dirname(req.resolve(`${name}/package.json`));
  } catch {
    throw new Error(`Package "${name}" not found. Run "npm install" in frontend/.`);
  }
}

const esbuild = await import(pathToFileURL(path.join(resolvePkg("esbuild"), "lib", "main.js")).href);
const twDir = resolvePkg("tailwindcss");
const { compile } = await import(pathToFileURL(path.join(twDir, "dist", "lib.mjs")).href);

const dist = path.join(root, "dist");
fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(path.join(dist, "assets"), { recursive: true });

// 1. JavaScript
const result = await esbuild.build({
  entryPoints: [path.join(root, "src", "main.tsx")],
  bundle: true,
  outfile: path.join(dist, "assets", "app.js"),
  jsx: "automatic",
  minify: true,
  sourcemap: false,
  target: "es2020",
  nodePaths: searchPaths,
  logLevel: "warning",
  metafile: true,
  define: { "process.env.NODE_ENV": '"production"' },
});

// 2. CSS: collect every token that could be a Tailwind class from the source files.
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? walk(path.join(dir, d.name)) : /\.(tsx?|html)$/.test(d.name) ? [path.join(dir, d.name)] : [],
  );
}
const candidates = new Set();
for (const file of [...walk(path.join(root, "src")), path.join(root, "index.html")]) {
  for (const tok of fs.readFileSync(file, "utf8").split(/[\s"'`{}();,<>]+/)) {
    if (tok && tok.length < 120 && /^[!a-z0-9@\-[\]:/.#%_()=,&>+*]+$/i.test(tok)) candidates.add(tok.replace(/^[=:]+/, ""));
  }
}
const inputCss = fs.readFileSync(path.join(root, "src", "styles.css"), "utf8");
const compiler = await compile(inputCss, {
  base: path.join(root, "src"),
  loadStylesheet: async (id, base) => {
    const p = id === "tailwindcss" ? path.join(twDir, "index.css") : path.resolve(base, id);
    return { path: p, base: path.dirname(p), content: fs.readFileSync(p, "utf8") };
  },
});
fs.writeFileSync(path.join(dist, "assets", "app.css"), compiler.build([...candidates]));

// 3. Static files + index.html
fs.cpSync(path.join(root, "public"), dist, { recursive: true });
const html = fs
  .readFileSync(path.join(root, "index.html"), "utf8")
  .replace("<!-- styles -->", '<link rel="stylesheet" href="/assets/app.css" />')
  .replace("<!-- script -->", '<script src="/assets/app.js"></script>');
fs.writeFileSync(path.join(dist, "index.html"), html);

const kb = (f) => (fs.statSync(path.join(dist, "assets", f)).size / 1024).toFixed(0);
console.log(`built dist/: app.js ${kb("app.js")} KB, app.css ${kb("app.css")} KB${result.warnings.length ? `, ${result.warnings.length} warnings` : ""}`);
