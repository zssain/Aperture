/* global process */
const secretName = /(secret|password|private[_-]?key|api[_-]?key|access[_-]?token)/i;
const exposed = Object.entries(process.env).filter(([key, value]) => key.startsWith("VITE_") && secretName.test(key) && Boolean(value));
if (exposed.length) {
  process.stderr.write(`Secret-like VITE variables are forbidden: ${exposed.map(([key]) => key).join(", ")}\n`);
  process.exit(1);
}

const fs = await import("node:fs");
if (fs.existsSync("dist")) {
  const files = fs.readdirSync("dist/assets").filter((name) => name.endsWith(".js"));
  const suspicious = /(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})/;
  for (const file of files) {
    if (suspicious.test(fs.readFileSync(`dist/assets/${file}`, "utf8"))) {
      process.stderr.write(`Secret-like value found in frontend bundle: ${file}\n`);
      process.exit(1);
    }
  }
}
