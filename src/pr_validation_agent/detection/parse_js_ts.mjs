import fs from "node:fs";

const [filePath, relativePath] = process.argv.slice(2);
const source = fs.readFileSync(filePath, "utf8");

let parser;
try {
  parser = await import("@babel/parser");
} catch {
  process.stderr.write("@babel/parser is required for JavaScript/TypeScript detection\n");
  process.exit(2);
}

const ast = parser.parse(source, {
  sourceType: "unambiguous",
  plugins: ["typescript", "jsx", "classProperties", "decorators-legacy"],
  errorRecovery: true,
});

const symbols = [];

function location(node) {
  return {
    start_line: node.loc?.start?.line ?? 1,
    end_line: node.loc?.end?.line ?? node.loc?.start?.line ?? 1,
  };
}

function namedId(node) {
  if (!node) return null;
  if (node.type === "Identifier") return node.name;
  if (node.type === "PrivateName") return `#${node.id?.name ?? "private"}`;
  if (node.type === "StringLiteral") return node.value;
  return null;
}

function addSymbol(name, qualifiedName, node, kind = "function") {
  if (!name || !node.loc) return;
  const loc = location(node);
  symbols.push({
    name,
    qualified_name: qualifiedName,
    kind,
    signature: `${kind} ${qualifiedName}`,
    ...loc,
  });
}

function visit(node, parents = []) {
  if (!node || typeof node !== "object") return;

  switch (node.type) {
    case "FunctionDeclaration": {
      const name = namedId(node.id);
      addSymbol(name, [...parents, name].filter(Boolean).join("."), node);
      break;
    }
    case "VariableDeclarator": {
      const name = namedId(node.id);
      if (
        name &&
        node.init &&
        ["ArrowFunctionExpression", "FunctionExpression"].includes(node.init.type)
      ) {
        addSymbol(name, [...parents, name].join("."), node.init);
      }
      break;
    }
    case "ClassDeclaration": {
      const className = namedId(node.id) ?? "AnonymousClass";
      for (const member of node.body?.body ?? []) {
        visit(member, [...parents, className]);
      }
      return;
    }
    case "ClassMethod":
    case "ClassPrivateMethod":
    case "ObjectMethod": {
      const name = namedId(node.key);
      addSymbol(name, [...parents, name].filter(Boolean).join("."), node, "method");
      break;
    }
    case "ObjectProperty": {
      const name = namedId(node.key);
      if (
        name &&
        node.value &&
        ["ArrowFunctionExpression", "FunctionExpression"].includes(node.value.type)
      ) {
        addSymbol(name, [...parents, name].filter(Boolean).join("."), node.value);
      }
      break;
    }
  }

  for (const [key, value] of Object.entries(node)) {
    if (key === "loc" || key === "start" || key === "end") continue;
    if (Array.isArray(value)) {
      for (const child of value) visit(child, parents);
    } else if (value && typeof value === "object") {
      visit(value, parents);
    }
  }
}

visit(ast.program);
process.stdout.write(JSON.stringify(symbols));
